#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""match_resources.py — 需求 vs 库存/合同 的四状态分类器。

用法: python3 match_resources.py <requirements.json> <case.json> <out.json>

对每条设备/物料需求按序尝试（规则详见 references/four_state_rules.md）:
  1. 库存清单: 名称归一匹配 + 规格兼容（数值能力比较: 默认 库存能力 ≥ 需求;
     min_temperature/precision 等反向指标为 库存值 ≤ 需求）→ 已具备
  2. 外协合同（供应商服务）→ 可外协（记录供应商/单价/货期）
  3. 采购合同（报价）→ 需采购（记录价格 + lead_time_days + order_by）
  4. 都不命中 → 不具备
库存命中但规格不可比较（字段缺失/非数值不可比）→ 无法核验，绝不自动通过；
案例整段缺失库存清单且合同无匹配 → 无法核验。
多份合同命中时: 单价最低优先，其次货期最短。
每条结论都带 matched_row（所匹配的库存/合同原始行）与 reason。

退出码: 0 正常; 2 用法错误; 3 输入不可读。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_entities import load_alias_index, normalize_name, clean_name

LOWER_IS_BETTER = {
    "min_temperature_c", "min_temp_c", "precision", "tolerance",
    "resolution", "detection_limit", "error", "uncertainty",
}
NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def parse_number(v):
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float)):
        return float(v), True
    m = NUM_RE.match(str(v))
    return (float(m.group(1)), True) if m else (None, False)


def compare_spec(key, required, have):
    """返回 (ok: True/False/None, 说明)。None 表示无法核验。"""
    if required is None:
        return True, "需求未给出 {}（null），按未指定跳过，不代表已核验".format(key)
    if have is None:
        return None, "库存记录缺少规格字段 {}，无法核验".format(key)
    rn, rok = parse_number(required)
    hn, hok = parse_number(have)
    if rok and hok:
        if key.casefold() in LOWER_IS_BETTER:
            ok = hn <= rn
            rule = "库存值须 ≤ 需求值"
        else:
            ok = hn >= rn
            rule = "库存能力须 ≥ 需求值"
        return ok, "{}: 需求={} 库存={}（规则: {}）→ {}".format(
            key, required, have, rule, "满足" if ok else "不满足")
    if str(have).strip().casefold() == str(required).strip().casefold():
        return True, "{}: 非数值规格字符串一致".format(key)
    return None, "{}: 非数值规格不一致或不可比较（需求={} 库存={}），无法核验".format(
        key, required, have)


def get_inventory(case):
    """返回 (库存条目列表, 案例是否提供了库存段)。兼容 dict/list 两种形态。"""
    if not isinstance(case, dict):
        return [], False
    for k in ("inventory", "库存", "inventory_list", "resources_inventory"):
        if k in case:
            inv = case[k]
            items = []
            if isinstance(inv, dict):
                for v in inv.values():
                    if isinstance(v, list):
                        items.extend(v)
            elif isinstance(inv, list):
                items = list(inv)
            return items, True
    return [], False


def get_contracts(case):
    """返回 (外协合同列表, 采购合同列表)。"""
    outsource, purchase = [], []
    c = case.get("contracts") if isinstance(case, dict) else None
    if isinstance(c, dict):
        for k, v in c.items():
            if not isinstance(v, list):
                continue
            kl = str(k).casefold()
            if any(p in kl for p in ("outsource", "外协", "service", "服务", "supplier")):
                outsource.extend(v)
            else:
                purchase.extend(v)
    elif isinstance(c, list):
        for row in c:
            t = str(row.get("type", "")).casefold() if isinstance(row, dict) else ""
            (outsource if any(p in t for p in ("outsource", "外协", "service"))
             else purchase).append(row)
    return outsource, purchase


def row_name(row, keys):
    for k in keys:
        if isinstance(row, dict) and row.get(k) is not None:
            return str(row[k])
    return ""


def pick_contract(cands):
    """多份合同命中: 单价最低优先，其次货期最短。"""
    def key(c):
        p, _ = parse_number(c.get("unit_price"))
        l, _ = parse_number(c.get("lead_time_days"))
        return (p if p is not None else float("inf"),
                l if l is not None else float("inf"))
    return sorted(cands, key=key)[0]


def match_one(req, kind, inv_items, inv_present, outsource, purchase, idx):
    name = str(req.get("name", ""))
    norm, _ = normalize_name(name, idx)
    nkey = clean_name(norm)
    res = {
        "id": req.get("id"), "kind": kind, "name": name,
        "normalized_name": norm, "gating": bool(req.get("gating")),
        "needed_by": req.get("needed_by"), "needed_window": req.get("needed_window"),
        "locator": req.get("locator"),
        "state": None, "matched_row": None, "spec_checks": [], "reason": "",
    }
    inv_note = None
    inv_candidates = []
    if not inv_present:
        inv_note = "案例未提供库存清单"
    else:
        inv_candidates = [
            it for it in inv_items
            if clean_name(normalize_name(row_name(it, ("name", "item")), idx)[0]) == nkey
        ]
    if inv_candidates:
        row = inv_candidates[0]
        res["matched_row"] = row
        checks, all_ok, any_unknown = [], True, False
        have_specs = row.get("specs") or {}
        for sk, rv in (req.get("specs") or {}).items():
            ok, detail = compare_spec(sk, rv, have_specs.get(sk))
            checks.append({"spec": sk, "required": rv,
                           "inventory": have_specs.get(sk), "ok": ok, "detail": detail})
            if ok is False:
                all_ok = False
            elif ok is None:
                any_unknown = True
        if kind == "material" and req.get("quantity") is not None:
            qn, qok = parse_number(req.get("quantity"))
            hq, hok = parse_number(row.get("quantity"))
            unit = req.get("unit") or row.get("unit") or ""
            if qok and hok:
                ok = hq >= qn
                checks.append({
                    "spec": "quantity", "required": req.get("quantity"),
                    "inventory": row.get("quantity"), "ok": ok,
                    "detail": "quantity: 需求 {}{} vs 库存 {}{}，余量 {}{}".format(
                        qn, unit, hq, row.get("unit", unit), hq - qn, unit)})
                if not ok:
                    all_ok = False
            else:
                checks.append({"spec": "quantity", "required": req.get("quantity"),
                               "inventory": row.get("quantity"), "ok": None,
                               "detail": "quantity: 数量不可比较，无法核验"})
                any_unknown = True
        res["spec_checks"] = checks
        if all_ok and not any_unknown:
            res["state"] = "已具备"
            res["reason"] = "库存命中（{}），全部规格兼容".format(row_name(row, ("name", "id")))
            return res
        if any_unknown and all_ok:
            res["state"] = "无法核验"
            res["reason"] = "库存命中但存在不可比较的规格: " + "；".join(
                c["detail"] for c in checks if c["ok"] is None)
            return res
        inv_note = "库存命中但规格不兼容: " + "；".join(
            c["detail"] for c in checks if c["ok"] is False)
    oc = [c for c in outsource
          if clean_name(normalize_name(row_name(c, ("service", "name", "item")), idx)[0]) == nkey]
    if oc:
        row = pick_contract(oc)
        res["matched_row"] = row
        res["state"] = "可外协"
        res["reason"] = (inv_note + "；" if inv_note else "") + \
            "外协合同命中: {}（供应商 {}，单价 {} {}/{}，货期 {} 天；多份合同时取单价最低、其次货期最短）".format(
                row_name(row, ("service", "name", "item")), row.get("vendor"),
                row.get("unit_price"), row.get("currency", ""), row.get("unit", ""),
                row.get("lead_time_days"))
        return res
    pc = [c for c in purchase
          if clean_name(normalize_name(row_name(c, ("item", "name")), idx)[0]) == nkey]
    if pc:
        row = pick_contract(pc)
        res["matched_row"] = row
        res["state"] = "需采购"
        res["reason"] = (inv_note + "；" if inv_note else "") + \
            "采购合同命中: {}（供应商 {}，单价 {} {}/{}，货期 {} 天，下单日 {}；多份合同时取单价最低、其次货期最短）".format(
                row_name(row, ("item", "name")), row.get("vendor"),
                row.get("unit_price"), row.get("currency", ""), row.get("unit", ""),
                row.get("lead_time_days"), row.get("order_by"))
        return res
    if inv_note == "案例未提供库存清单":
        res["state"] = "无法核验"
        res["reason"] = "案例未提供库存清单，且无外协/采购合同匹配，无法核验（绝不自动通过）"
    elif inv_note:
        res["state"] = "不具备"
        res["reason"] = inv_note + "；且无外协/采购合同覆盖"
    else:
        res["state"] = "不具备"
        res["reason"] = "库存清单中无此{}，且无外协/采购合同覆盖".format(
            "设备" if kind == "equipment" else "物料")
    return res


def main(argv):
    if len(argv) != 4:
        print("用法: python3 match_resources.py <requirements.json> <case.json> <out.json>",
              file=sys.stderr)
        return 2
    req_p, case_p, out_p = (Path(a) for a in argv[1:4])
    try:
        req = json.loads(req_p.read_text(encoding="utf-8"))
        case = json.loads(case_p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERROR: 无法读取输入: {}".format(e), file=sys.stderr)
        return 3
    idx = load_alias_index()
    inv_items, inv_present = get_inventory(case)
    outsource, purchase = get_contracts(case)
    items = []
    for e in req.get("equipment") or []:
        items.append(match_one(e, "equipment", inv_items, inv_present,
                               outsource, purchase, idx))
    for m in req.get("materials") or []:
        items.append(match_one(m, "material", inv_items, inv_present,
                               outsource, purchase, idx))
    summary = {"已具备": 0, "可外协": 0, "需采购": 0, "不具备": 0, "无法核验": 0}
    for it in items:
        summary[it["state"]] = summary.get(it["state"], 0) + 1
    gating_failures = [
        {"id": it["id"], "name": it["name"], "state": it["state"], "reason": it["reason"]}
        for it in items if it["gating"] and it["state"] in ("不具备", "无法核验")
    ]
    notes = []
    if not inv_present:
        notes.append("案例未提供库存清单，所有无合同覆盖的条目均为 无法核验")
    out = {
        "case_id": req.get("case_id") or (case.get("case_id") if isinstance(case, dict) else None),
        "plan_version": req.get("plan_version"),
        "items": items,
        "summary": summary,
        "gating_failures": gating_failures,
        "gating_rule": "关键(gating)条目为 不具备/无法核验 ⇒ 该版本不可行（或需改方案）",
        "notes": notes,
    }
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("match_resources [{}]: {}".format(req.get("plan_version"), summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
