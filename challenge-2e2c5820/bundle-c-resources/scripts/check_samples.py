#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_samples.py — 样本需求 vs 样本台账核验。

用法: python3 check_samples.py <requirements.json> <case.json> <out.json>

对每条样本需求核验（规则详见 references/four_state_rules.md）:
  1. 来源匹配（需求给出 source 时与台账比对，归一后相等）
  2. 数量充足: 台账可用量 - 需求量 = 余量，余量 >= 0（减法显式写出）
  3. 存储兼容: 台账存储温度须 ≤ 需求存储温度（如台账 -20°C vs 需求 -80°C → 失败）
  4. 伦理状态: ethics_status ∈ {approved, pending, none};
     pending / none / 未知值 → 阻断性确认项（confirmation_items），绝不视为已批准。
台账无此样本 → 不具备; 案例未提供台账 → 无法核验。
结论: 满足 / 不满足 / 待确认 / 不具备 / 无法核验。

退出码: 0 正常; 2 用法错误; 3 输入不可读。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_entities import load_alias_index, normalize_name, clean_name
from match_resources import parse_number

TEMP_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*[cCＣ]")


def parse_temp(s):
    m = TEMP_RE.search(str(s))
    return float(m.group(1)) if m else None


def get_registry(case):
    if isinstance(case, dict):
        for k, v in case.items():
            kl = str(k).casefold()
            if isinstance(v, list) and any(
                    p in kl for p in ("sample", "specimen", "样本", "样品")):
                return v, True
    return [], False


def check_sample(need, registry, reg_present, idx):
    res = {
        "id": need.get("id"), "name": need.get("name"),
        "gating": bool(need.get("gating")), "locator": need.get("locator"),
        "checks": {}, "issues": [], "confirmation_items": [], "matched_row": None,
        "verdict": None,
    }
    if not reg_present:
        res["verdict"] = "无法核验"
        res["issues_unknown"] = ["案例未提供样本台账"]
        return res
    nkey = clean_name(normalize_name(str(need.get("name", "")), idx)[0])
    cands = [r for r in registry if isinstance(r, dict)
             and clean_name(normalize_name(str(r.get("name", "")), idx)[0]) == nkey]
    if not cands:
        res["verdict"] = "不具备"
        res["issues"].append("样本台账中无此样本")
        return res
    reg = cands[0]
    res["matched_row"] = reg
    # 1. 来源
    if need.get("source"):
        ok = clean_name(need["source"]) == clean_name(reg.get("source", ""))
        res["checks"]["source"] = {
            "required": need["source"], "registry": reg.get("source"), "ok": ok}
        if not ok:
            res["issues"].append("来源不一致: 需求 {} vs 台账 {}".format(
                need["source"], reg.get("source")))
    # 2. 数量（显式减法）
    if need.get("quantity") is not None:
        qn, qok = parse_number(need.get("quantity"))
        hq, hok = parse_number(reg.get("quantity"))
        unit = need.get("unit") or reg.get("unit") or ""
        if qok and hok:
            ok = hq >= qn
            res["checks"]["quantity"] = {
                "demand": qn, "available": hq, "remaining": hq - qn, "unit": unit,
                "ok": ok,
                "detail": "可用 {} - 需求 {} = 余量 {} {}".format(hq, qn, hq - qn, unit)}
            if not ok:
                res["issues"].append("数量不足: 可用 {}{} < 需求 {}{}".format(
                    hq, unit, qn, unit))
        else:
            res["checks"]["quantity"] = {
                "demand": need.get("quantity"), "registry": reg.get("quantity"),
                "ok": None, "detail": "数量不可比较，无法核验"}
    # 3. 存储温度
    if need.get("storage"):
        rt = parse_temp(need.get("storage"))
        gt = parse_temp(reg.get("storage", ""))
        if rt is None or gt is None:
            res["checks"]["storage"] = {
                "required": need.get("storage"), "registry": reg.get("storage"),
                "ok": None, "detail": "存储温度不可解析，无法核验"}
        else:
            ok = gt <= rt
            res["checks"]["storage"] = {
                "required": need.get("storage"), "registry": reg.get("storage"),
                "required_c": rt, "registry_c": gt, "ok": ok,
                "detail": "台账 {}°C {} 需求 {}°C（规则: 台账温度须 ≤ 需求温度）".format(
                    gt, "≤" if ok else ">", rt)}
            if not ok:
                res["issues"].append(
                    "存储温度不满足: 台账 {}（{}°C）高于需求 {}（{}°C）".format(
                        reg.get("storage"), gt, need.get("storage"), rt))
    # 4. 伦理状态
    eth_raw = reg.get("ethics_status") if isinstance(reg, dict) else None
    eth = str(eth_raw).strip().casefold() if eth_raw is not None else ""
    if need.get("needs_ethics") or "ethics_status" in reg:
        res["checks"]["ethics"] = {"registry": eth_raw}
        if eth == "approved":
            res["checks"]["ethics"]["ok"] = True
        elif eth in ("pending", "none", ""):
            res["checks"]["ethics"]["ok"] = False
            res["confirmation_items"].append({
                "sample": need.get("name"),
                "ethics_status": eth_raw if eth_raw is not None else "none",
                "action": "伦理状态为 {}，属阻断性确认项: 须取得批件/完成确认后方可使用，"
                          "绝不视为已批准".format(eth_raw if eth_raw is not None else "none")})
        else:
            res["checks"]["ethics"]["ok"] = None
            res["confirmation_items"].append({
                "sample": need.get("name"),
                "ethics_status": eth_raw,
                "action": "伦理状态值未知（{}），按待确认处理，绝不视为已批准".format(eth_raw)})
    # 结论
    unknown = any(isinstance(c, dict) and c.get("ok") is None
                  for c in res["checks"].values())
    if res["issues"]:
        res["verdict"] = "不满足"
    elif unknown:
        res["verdict"] = "无法核验"
    elif res["confirmation_items"]:
        res["verdict"] = "待确认"
    else:
        res["verdict"] = "满足"
    return res


def main(argv):
    if len(argv) != 4:
        print("用法: python3 check_samples.py <requirements.json> <case.json> <out.json>",
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
    registry, reg_present = get_registry(case)
    notes = []
    if not reg_present and (req.get("samples") or []):
        notes.append("案例未提供样本台账，样本项均为 无法核验")
    verdicts = [check_sample(s, registry, reg_present, idx)
                for s in req.get("samples") or []]
    confirmation_items = []
    for v in verdicts:
        confirmation_items.extend(v["confirmation_items"])
    out = {
        "case_id": req.get("case_id") or (case.get("case_id") if isinstance(case, dict) else None),
        "plan_version": req.get("plan_version"),
        "verdicts": verdicts,
        "confirmation_items": confirmation_items,
        "ethics_rule": "ethics_status ∈ {approved, pending, none}; pending/none/未知 → "
                       "阻断性确认项，绝不视为已批准",
        "notes": notes,
    }
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print("check_samples [{}]: 结论 {}，确认项 {} 条".format(
        req.get("plan_version"), counts, len(confirmation_items)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
