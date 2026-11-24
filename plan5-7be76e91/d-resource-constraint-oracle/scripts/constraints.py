#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""constraints.py — 资源约束满足裁决（设备/耗材/参数窗口/技能/审批）。

输入 facts JSON（模型从契约/方案/材料中抽取并挂来源的资源供需事实）与 case JSON，
对每份候选方案逐项检查：
  1. 设备存在、可用、能力窗口覆盖需求、档期空闲区间与需求窗口相交；
  2. 耗材可得（现货或可订）且到货日 <= 需求截止日；方案耗材总价 <= 预算（若 case 给预算）；
  3. 参数窗口：方案要求窗口 ⊆ 设备极限 ∩ 契约给定域（冲突时写清具体冲突区间）；
  4. 技能要求 ⊆ 人员技能集；安全/场地审批状态。
输出 constraints_report.json / constraints_report.md，每方案 verdict：
  feasible_now / feasible_after(日期) / infeasible(原因)。
全部方案 infeasible 时输出 relax_hints（解除每个 blocking 的条件）并以退出码 3 拦截。

退出码：0 = 至少一个方案可行（now 或 after）；2 = 输入/用法错误；3 = 全部方案不可行。
仅使用 Python 标准库；同一输入双跑产物逐字节一致（无 wall-clock / 随机数）。

日期约定：所有区间均为半开区间 [start, end)。如设备档期 {"start":"2026-01-05","end":"2026-01-31"}
表示 2026-01-05 至 2026-01-30（含）被占用，2026-01-31 起空闲。
"""
import argparse
import json
import sys
from datetime import date, timedelta


# ---------- 基础工具 ----------

def parse_date(s, ctx=""):
    if not isinstance(s, str):
        raise ValueError("日期必须是 ISO 字符串%s，得到: %r" % (("（" + ctx + "）") if ctx else "", s))
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ValueError("非法 ISO 日期%s: %r" % (("（" + ctx + "）") if ctx else "", s))


def fmt_num(x):
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def fmt_win(w):
    if w is None:
        return "(-∞, +∞)"
    lo = "-∞" if w.get("min") is None else fmt_num(w["min"])
    hi = "+∞" if w.get("max") is None else fmt_num(w["max"])
    return "[%s, %s]" % (lo, hi)


def win_intersect(a, b):
    """两个窗口求交；窗口缺省端视为无界。返回 {'min':..,'max':..}，空集返回 None。"""
    los = [w.get("min") for w in (a, b) if w is not None and w.get("min") is not None]
    his = [w.get("max") for w in (a, b) if w is not None and w.get("max") is not None]
    lo = max(los) if los else None
    hi = min(his) if his else None
    if lo is not None and hi is not None and lo > hi:
        return None
    return {"min": lo, "max": hi}


def win_contains(outer, inner):
    """outer ⊇ inner ?（None 端视为无界）"""
    if outer is None:
        return False
    if outer.get("min") is not None and inner.get("min") is not None and inner["min"] < outer["min"]:
        return False
    if outer.get("min") is not None and inner.get("min") is None:
        return False
    if outer.get("max") is not None and inner.get("max") is not None and inner["max"] > outer["max"]:
        return False
    if outer.get("max") is not None and inner.get("max") is None:
        return False
    return True


def free_intervals(lo, hi, bookings):
    """[lo, hi) 内扣除 bookings（半开区间列表）后的空闲区间，按起点升序。"""
    occ = []
    for b in bookings:
        s = max(parse_date(b["start"], "booked_windows.start"), lo)
        e = min(parse_date(b["end"], "booked_windows.end"), hi)
        if s < e:
            occ.append((s, e))
    occ.sort()
    free = []
    cur = lo
    for s, e in occ:
        if cur < s:
            free.append((cur, s))
        cur = max(cur, e)
    if cur < hi:
        free.append((cur, hi))
    return free


def first_free_start(lo, hi, bookings, duration_days):
    for s, e in free_intervals(lo, hi, bookings):
        if (e - s).days >= duration_days:
            return s
    return None


def violation(vtype, detail, blocking, data=None):
    v = {"type": vtype, "detail": detail, "blocking": bool(blocking)}
    if data:
        v["data"] = data
    return v


# ---------- 逐方案检查 ----------

def check_plan(plan, resources, case):
    ref = parse_date(case["reference_date"], "case.reference_date")
    violations = []
    notes = []
    start_bound = ref  # 所有"可启动条件"的最大者；> ref 则 feasible_after

    equip_by_id = {e["id"]: e for e in resources.get("equipment", [])}
    cons_by_id = {c["id"]: c for c in resources.get("consumables", [])}
    appr_by_id = {a["id"]: a for a in resources.get("approvals", [])}
    domain = case.get("contract_domain", {}) or {}

    # --- 1. 设备 ---
    for need in plan.get("equipment_needs", []):
        eid = need.get("equipment_id")
        stage = need.get("stage", "execute")
        dur = int(need.get("duration_days", 1))
        eq = equip_by_id.get(eid)
        if eq is None:
            violations.append(violation(
                "equipment_missing",
                "方案 %s 需要设备 %s（阶段 %s），但资源清单中不存在该设备。" % (plan["plan_id"], eid, stage),
                True, {"equipment_id": eid, "stage": stage}))
            continue
        if not eq.get("available", True):
            violations.append(violation(
                "equipment_unavailable",
                "设备 %s（%s）当前状态为不可用（如停用/大修）。"
                % (eid, eq.get("name", "")), True, {"equipment_id": eid}))
            continue
        for cap, req in (need.get("required_capabilities") or {}).items():
            caps = eq.get("capabilities", {})
            if cap not in caps:
                violations.append(violation(
                    "equipment_capability_missing",
                    "设备 %s 未声明能力项 %s，方案要求窗口 %s 无从核对。"
                    % (eid, cap, fmt_win(req)), True,
                    {"equipment_id": eid, "capability": cap, "required": req}))
                continue
            ew = caps[cap]
            if not win_contains(ew, req):
                violations.append(violation(
                    "equipment_capability_insufficient",
                    "设备 %s 能力 %s 窗口 %s 不能覆盖方案要求 %s。"
                    % (eid, cap, fmt_win(ew), fmt_win(req)), True,
                    {"equipment_id": eid, "capability": cap,
                     "equipment_window": ew, "required": req}))
        lo = parse_date(need["earliest_use"], "equipment_needs.earliest_use")
        hi = parse_date(need["latest_use"], "equipment_needs.latest_use")
        if lo >= hi:
            violations.append(violation(
                "equipment_window_malformed",
                "设备 %s 需求窗口 [earliest_use, latest_use) = [%s, %s) 为空。"
                % (eid, need["earliest_use"], need["latest_use"]), True,
                {"equipment_id": eid}))
            continue
        ff = first_free_start(lo, hi, eq.get("booked_windows", []), dur)
        if ff is None:
            violations.append(violation(
                "equipment_booking_conflict",
                "设备 %s 在需求窗口 [%s, %s) 内没有 >= %d 天的连续空档（档期表：%s）。"
                % (eid, need["earliest_use"], need["latest_use"], dur,
                   json.dumps(eq.get("booked_windows", []), ensure_ascii=False)),
                True, {"equipment_id": eid, "stage": stage,
                       "window": [need["earliest_use"], need["latest_use"]],
                       "duration_days": dur}))
        else:
            if ff > start_bound:
                start_bound = ff
            if ff > ref:
                notes.append("设备 %s（阶段 %s）首个 >= %d 天空档自 %s 起，构成启动约束。"
                             % (eid, stage, dur, ff.isoformat()))

    # --- 2. 耗材 ---
    total_cost = 0.0
    cost_known = True
    for cn in plan.get("consumable_needs", []):
        cid = cn.get("consumable_id")
        c = cons_by_id.get(cid)
        if c is None:
            violations.append(violation(
                "consumable_missing",
                "方案 %s 需要耗材 %s，但资源清单中不存在。" % (plan["plan_id"], cid),
                True, {"consumable_id": cid}))
            continue
        qty = cn.get("quantity", 1)
        if c.get("unit_cost") is not None:
            total_cost += float(c["unit_cost"]) * qty
        else:
            cost_known = False
        if c.get("in_stock", False):
            notes.append("耗材 %s（%s）现货，立即可用。" % (cid, c.get("name", "")))
            continue
        if not c.get("orderable", True):
            violations.append(violation(
                "consumable_not_obtainable",
                "耗材 %s（%s）无现货且不可订购。" % (cid, c.get("name", "")),
                True, {"consumable_id": cid}))
            continue
        lead = int(c.get("lead_time_days", 0))
        arrival = ref + timedelta(days=lead)
        needed_by = parse_date(cn["needed_by"], "consumable_needs.needed_by")
        if arrival > needed_by:
            violations.append(violation(
                "consumable_lead_time_exceeded",
                "耗材 %s（%s）货期 %d 天，预计 %s 到货，晚于需求截止 %s。"
                % (cid, c.get("name", ""), lead, arrival.isoformat(), cn["needed_by"]),
                True, {"consumable_id": cid, "lead_time_days": lead,
                       "arrival": arrival.isoformat(), "needed_by": cn["needed_by"]}))
        else:
            if arrival > start_bound:
                start_bound = arrival
            if arrival > ref:
                notes.append("耗材 %s 预计 %s 到货（货期 %d 天），构成启动约束。"
                             % (cid, arrival.isoformat(), lead))
    budget = case.get("budget_cny")
    if budget is not None and cost_known and total_cost > float(budget):
        violations.append(violation(
            "budget_exceeded",
            "方案 %s 耗材总价 %.2f 元超出预算 %.2f 元。" % (plan["plan_id"], total_cost, float(budget)),
            True, {"plan_cost": total_cost, "budget": float(budget)}))

    # --- 3. 参数窗口：方案 ⊆ 设备极限 ∩ 契约域 ---
    for pw in plan.get("parameter_windows", []):
        param = pw.get("parameter")
        req = pw.get("required")
        if req is None:
            continue
        dev_win = None
        for need in plan.get("equipment_needs", []):
            eq = equip_by_id.get(need.get("equipment_id"))
            if eq and param in (eq.get("capabilities") or {}):
                dev_win = eq["capabilities"][param] if dev_win is None else win_intersect(dev_win, eq["capabilities"][param])
        dom_win = domain.get(param)
        allowed = dev_win
        if allowed is not None and dom_win is not None:
            allowed = win_intersect(allowed, dom_win)
        elif allowed is None:
            allowed = dom_win
        if allowed is None:
            notes.append("参数 %s 无设备极限与契约域约束，视为无界。" % param)
            continue
        inter = win_intersect(allowed, req)
        if inter is None:
            violations.append(violation(
                "parameter_window_conflict",
                "参数 %s 空交集：方案要求 %s ∩ (设备极限 %s ∩ 契约域 %s = 允许 %s) = ∅。"
                % (param, fmt_win(req), fmt_win(dev_win), fmt_win(dom_win), fmt_win(allowed)),
                True, {"parameter": param, "required": req,
                       "device_window": dev_win, "domain_window": dom_win,
                       "allowed": allowed, "empty_intersection": True}))
        elif not win_contains(allowed, req):
            violations.append(violation(
                "parameter_window_conflict",
                "参数 %s 方案要求 %s 未完全被允许区间 %s（设备 %s ∩ 契约域 %s）覆盖。"
                % (param, fmt_win(req), fmt_win(allowed), fmt_win(dev_win), fmt_win(dom_win)),
                True, {"parameter": param, "required": req,
                       "device_window": dev_win, "domain_window": dom_win,
                       "allowed": allowed, "empty_intersection": False}))

    # --- 4. 技能 ---
    all_skills = set()
    for p in resources.get("personnel", []):
        all_skills.update(p.get("skills", []))
    missing_skills = sorted(set(plan.get("skill_needs", [])) - all_skills)
    if missing_skills:
        violations.append(violation(
            "skill_missing",
            "方案 %s 需要技能 %s，人员技能集 %s 不覆盖。"
            % (plan["plan_id"], "、".join(missing_skills), "、".join(sorted(all_skills)) or "（空）"),
            True, {"missing_skills": missing_skills}))

    # --- 5. 审批 ---
    for aid in plan.get("approval_needs", []):
        ap = appr_by_id.get(aid)
        if ap is None:
            violations.append(violation(
                "approval_missing",
                "方案 %s 需要审批 %s，资源清单中无记录。" % (plan["plan_id"], aid),
                True, {"approval_id": aid}))
            continue
        st = ap.get("status", "unknown")
        if st == "granted":
            notes.append("审批 %s（%s）已获批。" % (aid, ap.get("name", "")))
        elif st == "pending":
            exp = ap.get("expected_date")
            if exp:
                ed = parse_date(exp, "approvals.expected_date")
                if ed > start_bound:
                    start_bound = ed
                notes.append("审批 %s（%s）在途，预计 %s 获批，构成启动约束。"
                             % (aid, ap.get("name", ""), exp))
            else:
                notes.append("审批 %s（%s）在途，无预计日期——列为确认项。"
                             % (aid, ap.get("name", "")))
        else:
            violations.append(violation(
                "approval_blocked",
                "审批 %s（%s）状态为 %s，未获批。" % (aid, ap.get("name", ""), st),
                True, {"approval_id": aid, "status": st}))

    # --- verdict ---
    blocking = [v for v in violations if v["blocking"]]
    if blocking:
        verdict = "infeasible"
        feasible_after = None
    elif start_bound <= ref:
        verdict = "feasible_now"
        feasible_after = None
    else:
        verdict = "feasible_after"
        feasible_after = start_bound.isoformat()

    return {
        "plan_id": plan["plan_id"],
        "verdict": verdict,
        "feasible_after": feasible_after,
        "start_bound": start_bound.isoformat(),
        "violations": violations,
        "notes": notes,
    }


# ---------- relax_hints ----------

def build_relax_hint(v):
    d = v.get("data", {})
    t = v["type"]
    if t == "equipment_missing":
        return ("解除条件：购置/租用/外协一台具备需求能力的设备（%s），或修改方案改用现有设备。"
                % d.get("equipment_id", "?"))
    if t == "equipment_unavailable":
        return "解除条件：等待设备 %s 恢复可用，或改用同能力替代设备/外协。" % d.get("equipment_id", "?")
    if t == "equipment_capability_missing":
        return ("解除条件：补充核验设备 %s 的能力项 %s（查设备手册/计量证书），若确实不具备则更换设备。"
                % (d.get("equipment_id", "?"), d.get("capability", "?")))
    if t == "equipment_capability_insufficient":
        return ("解除条件：将方案 %s 窗口收缩进设备能力 %s，或更换能力覆盖的设备。"
                % (d.get("capability", "?"), fmt_win(d.get("equipment_window"))))
    if t == "equipment_booking_conflict":
        w = d.get("window", ["?", "?"])
        return ("解除条件：与设备 %s 的档期持有方协商让出 >= %d 天连续空档；或将需求窗口 [%s, %s) 顺延/放宽"
                "（需契约方批准）；或改用同能力替代设备。"
                % (d.get("equipment_id", "?"), d.get("duration_days", "?"), w[0], w[1]))
    if t == "consumable_missing":
        return "解除条件：补充耗材 %s 的供货渠道信息，或改用清单内替代耗材。" % d.get("consumable_id", "?")
    if t == "consumable_not_obtainable":
        return "解除条件：为耗材 %s 找到可订购渠道或替代料。" % d.get("consumable_id", "?")
    if t == "consumable_lead_time_exceeded":
        return ("解除条件：为耗材 %s 找到现货/更短货期供应商（货期 <= 需求截止 %s），"
                "或将需求截止顺延至 %s 之后（需契约方批准）。"
                % (d.get("consumable_id", "?"), d.get("needed_by", "?"), d.get("arrival", "?")))
    if t == "budget_exceeded":
        return ("解除条件：将预算提高到 >= %.2f 元，或议价/减量/换用更便宜替代耗材。"
                % d.get("plan_cost", 0.0))
    if t == "parameter_window_conflict":
        return ("解除条件：把方案参数 %s 的要求窗口 %s 收缩/平移到允许区间 %s（设备极限 ∩ 契约域）之内；"
                "若契约域可协商，则向契约方申请放宽参数域。"
                % (d.get("parameter", "?"), fmt_win(d.get("required")), fmt_win(d.get("allowed"))))
    if t == "skill_missing":
        return "解除条件：培训现有人员或外聘具备技能 %s 的人员。" % "、".join(d.get("missing_skills", []))
    if t == "approval_missing":
        return "解除条件：补办审批 %s 的申报流程并等待获批。" % d.get("approval_id", "?")
    if t == "approval_blocked":
        return "解除条件：重新申报审批 %s（当前状态 %s）并获批。" % (d.get("approval_id", "?"), d.get("status", "?"))
    if t == "equipment_window_malformed":
        return "解除条件：修正方案中设备 %s 的需求窗口（earliest_use 必须早于 latest_use）。" % d.get("equipment_id", "?")
    return "解除条件：人工复核违例 %s。" % t


# ---------- 报告输出 ----------

def write_reports(report, out_dir):
    import os
    jpath = os.path.join(out_dir, "constraints_report.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    lines = []
    if report.get("note"):
        lines.append("> %s" % report["note"])
        lines.append("")
    lines.append("# 资源约束裁决报告（constraints_report）")
    lines.append("")
    lines.append("- case_id: %s" % report["case_id"])
    lines.append("- 基准日 reference_date: %s" % report["reference_date"])
    if report.get("deadline"):
        lines.append("- 截止 deadline: %s" % report["deadline"])
    lines.append("")
    lines.append("| 方案 | verdict | feasible_after | blocking 数 | warning 数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for p in report["plans"]:
        nb = sum(1 for v in p["violations"] if v["blocking"])
        nw = sum(1 for v in p["violations"] if not v["blocking"])
        lines.append("| %s | %s | %s | %d | %d |" % (
            p["plan_id"], p["verdict"], p["feasible_after"] or "-", nb, nw))
    lines.append("")
    for p in report["plans"]:
        lines.append("## %s — %s" % (p["plan_id"], p["verdict"]))
        if p["feasible_after"]:
            lines.append("- 最早可启动（所有启动约束的最大者）：**%s**" % p["feasible_after"])
        for v in p["violations"]:
            lines.append("- [%s] %s：%s" % ("BLOCKING" if v["blocking"] else "warning", v["type"], v["detail"]))
        for n in p["notes"]:
            lines.append("- 注记：%s" % n)
        lines.append("")
    if report["all_infeasible"]:
        lines.append("## 全部方案不可行 — relax_hints（解除条件）")
        lines.append("")
        for pid, hints in report["relax_hints"].items():
            lines.append("### %s" % pid)
            for h in hints:
                lines.append("- %s" % h)
            lines.append("")
    mpath = os.path.join(out_dir, "constraints_report.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return jpath, mpath


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="资源约束满足裁决：对 facts JSON 中每份方案逐项检查设备/耗材/参数窗口/技能/审批，"
                    "输出 feasible_now / feasible_after / infeasible  verdict。")
    ap.add_argument("--facts", required=True, help="facts JSON（resources_available + plan_requirements）")
    ap.add_argument("--case", required=True, help="case JSON（case_id/reference_date/deadline/budget_cny/contract_domain）")
    ap.add_argument("--out-dir", required=True, help="输出目录（constraints_report.json/.md）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 报告顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args(argv)

    import os
    try:
        with open(args.facts, "r", encoding="utf-8") as f:
            facts = json.load(f)
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("输入错误：%s" % e, file=sys.stderr)
        return 2

    resources = facts.get("resources_available", {})
    plans = facts.get("plan_requirements", [])
    if not plans:
        print("输入错误：facts 中 plan_requirements 为空。", file=sys.stderr)
        return 2

    try:
        results = [check_plan(p, resources, case) for p in plans]
    except (ValueError, KeyError) as e:
        print("输入错误：%s" % e, file=sys.stderr)
        return 2

    all_infeasible = all(r["verdict"] == "infeasible" for r in results)
    relax_hints = {}
    if all_infeasible:
        for r in results:
            relax_hints[r["plan_id"]] = [build_relax_hint(v) for v in r["violations"] if v["blocking"]]

    report = {
        "case_id": case.get("case_id", "UNKNOWN"),
        "reference_date": case.get("reference_date"),
        "deadline": case.get("deadline"),
        "plans": results,
        "summary": {
            "feasible_now": [r["plan_id"] for r in results if r["verdict"] == "feasible_now"],
            "feasible_after": [r["plan_id"] for r in results if r["verdict"] == "feasible_after"],
            "infeasible": [r["plan_id"] for r in results if r["verdict"] == "infeasible"],
        },
        "all_infeasible": all_infeasible,
        "relax_hints": relax_hints,
    }
    if args.note:
        report["note"] = args.note

    os.makedirs(args.out_dir, exist_ok=True)
    jpath, mpath = write_reports(report, args.out_dir)
    print("已写出: %s" % jpath)
    print("已写出: %s" % mpath)
    for r in results:
        print("方案 %s: %s%s" % (r["plan_id"], r["verdict"],
                                 "(%s)" % r["feasible_after"] if r["feasible_after"] else ""))
    if all_infeasible:
        print("质量门拦截：全部方案 infeasible。relax_hints：")
        for pid, hints in relax_hints.items():
            for h in hints:
                print("  [%s] %s" % (pid, h))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
