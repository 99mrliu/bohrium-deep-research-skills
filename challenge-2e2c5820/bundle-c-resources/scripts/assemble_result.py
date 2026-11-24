#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 汇总各核验产物为 result.json。

用法:
  python3 assemble_result.py --case case.json --artifacts <dir> --out result.json \
      --status complete|partial|failed --note "说明"

保证:
  - case_id + case.json output_contract 声明的全部字段 + status + sources +
    uncertainty + change_record 一定存在；
  - output_contract 字段能由产物填充则填充，不能则为 null 并记入 uncertainty；
  - 若 --out 已存在: 非 null 的既有值绝不被覆盖，change_record 追加一条。

版本级结论逻辑（确定性，冲突表驱动）:
  关键(gating)项 不具备/无法核验、货期 赶不上、预订 冲突、样本 不满足/不具备
  → 不可行（或需改方案），理由逐条列出；
  否则存在 需采购/可外协 项或伦理确认项 → 有条件可行 + 条件清单
  （写明下单日/货期/外协单位/预订或伦理动作）；
  否则 → 可行。

退出码: 0 正常; 2 用法错误; 3 输入不可读。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERROR: 无法读取 {}: {}".format(p, e), file=sys.stderr)
        sys.exit(3)


def collect(adir):
    match, booking, samples = {}, {}, {}
    for f in sorted(Path(adir).glob("match_*.json")):
        match[f.stem.split("_", 1)[1]] = load_json(f)
    for f in sorted(adir.glob("booking_*.json")):
        booking[f.stem.split("_", 1)[1]] = load_json(f)
    for f in sorted(adir.glob("samples_*.json")):
        samples[f.stem.split("_", 1)[1]] = load_json(f)
    return match, booking, samples


def build(case, match, booking, samples):
    feasibility, blocking, conditions = {}, [], []
    four_state, conflicts_all, sample_all, uncertainty = {}, [], [], []
    versions = sorted(set(match) | set(booking) | set(samples))
    for v in versions:
        reasons, conds = [], []
        m, b, s = match.get(v), booking.get(v), samples.get(v)
        if m:
            four_state[v] = m.get("summary", {})
            for note in m.get("notes", []):
                uncertainty.append("[{}] {}".format(v, note))
            for it in m.get("items", []):
                st = it.get("state")
                if st in ("不具备", "无法核验"):
                    blocking.append({"version": v, "type": st, "item": it.get("name"),
                                     "gating": it.get("gating"),
                                     "detail": it.get("reason")})
                    if it.get("gating"):
                        reasons.append("关键项{}: {}".format(st, it.get("name")))
                elif st == "需采购" and it.get("matched_row"):
                    r = it["matched_row"]
                    conds.append("采购 {}: 供应商 {}，单价 {} {}/{}，货期 {} 天，下单日 {}".format(
                        it.get("name"), r.get("vendor"), r.get("unit_price"),
                        r.get("currency", ""), r.get("unit", ""),
                        r.get("lead_time_days"), r.get("order_by")))
                elif st == "可外协" and it.get("matched_row"):
                    r = it["matched_row"]
                    conds.append("外协 {}: 单位 {}，货期 {} 天，单价 {} {}/{}".format(
                        it.get("name"), r.get("vendor"), r.get("lead_time_days"),
                        r.get("unit_price"), r.get("currency", ""), r.get("unit", "")))
        if b:
            for note in b.get("notes", []):
                uncertainty.append("[{}] {}".format(v, note))
            for w in b.get("booking_windows", []):
                if w.get("verdict") == "无法核验":
                    uncertainty.append("[{}] 预订窗口无法核验: {}（{}）".format(
                        v, w.get("resource"), w.get("reason")))
                for c in w.get("conflicts") or []:
                    conflicts_all.append({
                        "version": v, "resource": w.get("resource"),
                        "plan_window": w.get("plan_window"),
                        "existing_booking": c.get("existing_booking"),
                        "overlap_days": c.get("overlap_days"),
                        "overlap_hours": c.get("overlap_hours")})
                    blocking.append({
                        "version": v, "type": "预订冲突", "item": w.get("resource"),
                        "gating": w.get("gating"),
                        "detail": "窗口 {} 与 {} 的既有预订重叠 {} 小时".format(
                            w.get("plan_window"),
                            (c.get("existing_booking") or {}).get("booked_by"),
                            c.get("overlap_hours"))})
                    reasons.append("预订冲突: {}（重叠 {} 小时）".format(
                        w.get("resource"), c.get("overlap_hours")))
            for lt in b.get("lead_times", []):
                if lt.get("verdict") == "赶不上":
                    blocking.append({
                        "version": v, "type": "货期赶不上", "item": lt.get("material"),
                        "gating": lt.get("gating"),
                        "detail": "到货 {} 晚于需要 {}，缺口 {} 天".format(
                            lt.get("arrival"), lt.get("needed_by"), -lt.get("slack_days", 0))})
                    reasons.append("货期赶不上: {}（slack_days={}）".format(
                        lt.get("material"), lt.get("slack_days")))
                elif lt.get("verdict") == "无法核验":
                    uncertainty.append("[{}] 货期无法核验: {}（{}）".format(
                        v, lt.get("material"), lt.get("reason")))
        if s:
            for note in s.get("notes", []):
                uncertainty.append("[{}] {}".format(v, note))
            for vd in s.get("verdicts", []):
                sample_all.append({
                    "version": v, "id": vd.get("id"), "name": vd.get("name"),
                    "verdict": vd.get("verdict"), "issues": vd.get("issues"),
                    "checks": vd.get("checks")})
                if vd.get("verdict") in ("不满足", "不具备", "无法核验"):
                    blocking.append({
                        "version": v, "type": "样本" + vd["verdict"],
                        "item": vd.get("name"), "gating": vd.get("gating"),
                        "detail": "；".join(vd.get("issues") or
                                          (vd.get("issues_unknown") or []) or ["无法核验"])})
                    reasons.append("样本{}: {}".format(vd["verdict"], vd.get("name")))
            for ci in s.get("confirmation_items", []):
                blocking.append({"version": v, "type": "伦理待确认",
                                 "item": ci.get("sample"), "detail": ci.get("action")})
                conds.append("伦理确认: {}（当前状态 {}，取得批件后方可使用）".format(
                    ci.get("sample"), ci.get("ethics_status")))
        if reasons:
            feasibility[v] = {"verdict": "不可行（或需改方案）", "reasons": reasons}
        elif conds:
            feasibility[v] = {"verdict": "有条件可行", "conditions": conds}
        else:
            feasibility[v] = {"verdict": "可行", "conditions": []}
        conditions.extend({"version": v, "action": c} for c in conds)
    return {
        "feasibility_by_version": feasibility,
        "blocking_items": blocking,
        "conditions_list": conditions,
        "four_state_summary": four_state,
        "booking_conflicts": conflicts_all,
        "sample_verdicts": sample_all,
    }, uncertainty


def main(argv):
    ap = argparse.ArgumentParser(description="汇总核验产物为 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True,
                    choices=["complete", "partial", "failed"])
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv[1:])

    case = load_json(a.case)
    match, booking, samples = collect(Path(a.artifacts))
    computed, uncertainty = build(case, match, booking, samples)

    out_path = Path(a.out)
    result = {}
    if out_path.is_file():
        try:
            result = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            result = {}
    if not isinstance(result, dict):
        result = {}

    def setfill(k, v):
        # 绝不覆盖非 null 的既有值
        if result.get(k) is None:
            result[k] = v

    setfill("case_id", case.get("case_id") if isinstance(case, dict) else None)
    setfill("status", a.status)

    oc = case.get("output_contract") if isinstance(case, dict) else None
    fields = list(oc) if isinstance(oc, dict) else (oc if isinstance(oc, list) else [])
    for f in fields:
        if f in computed:
            setfill(f, computed[f])
        elif result.get(f) is None:
            result[f] = None
            uncertainty.append(
                "output_contract 字段 {} 未由本技能产物填充，需人工或其他流程补充".format(f))
    # 常用字段即使未在 output_contract 声明也补齐
    for k, v in computed.items():
        setfill(k, v)

    sources = list(dict.fromkeys(
        (result.get("sources") or []) + [str(Path(a.case).resolve())] +
        [str(p.resolve()) for p in sorted(Path(a.artifacts).glob("*.json"))]
    ))
    result["sources"] = sources
    merged_unc = list(dict.fromkeys((result.get("uncertainty") or []) + uncertainty))
    result["uncertainty"] = merged_unc
    cr = result.get("change_record")
    if not isinstance(cr, list):
        cr = []
    cr.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": a.status,
        "note": a.note,
    })
    result["change_record"] = cr

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    verdicts = {v: f["verdict"] for v, f in
                computed["feasibility_by_version"].items()}
    print("assemble_result: 写入 {} (case_id={}, 版本结论={})".format(
        out_path, result.get("case_id"), verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
