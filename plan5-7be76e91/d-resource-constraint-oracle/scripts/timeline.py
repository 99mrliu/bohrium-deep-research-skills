#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""timeline.py — 最早可启动排期（资源日历驱动的确定性调度）。

基于资源日历做串行阶段排期：采购等待 → 准备 → 执行 → 表征排队。
  - 设备档期：占用区间（契约 booked_windows + 已排方案对本设备的占用，按 facts 中方案顺序逐个排入）；
  - 耗材：无现货则到货日 = 基准日 + 货期天数，构成启动约束；
  - 审批：pending 且有 expected_date 的审批构成启动约束；
  - 人员：执行/表征区间必须被某位技能全覆盖人员的可用窗口完整覆盖。
资源冲突时顺延；冲突顺延上限 365 天，超出判定 schedule_infeasible。

输出 timeline_report.json + gantt.md（Markdown 表 + ASCII 甘特条）。
每方案：earliest_start / first_execution_start / earliest_finish / critical_waits / past_deadline。

若提供 --constraints（constraints.py 的报告），verdict=infeasible 的方案直接跳过
（标记 skipped_infeasible，不参与排期）。

退出码：0 = 至少一个方案排出时间线；2 = 输入/用法错误；3 = 无任何方案可排（产物仍写出）。
仅标准库；日期全部 ISO 字符串；确定性，双跑字节一致。

日期约定：半开区间 [start, end)；earliest_finish 为最后阶段结束的次日（半开右端）。
"""
import argparse
import json
import sys
from datetime import date, timedelta

SLIP_CAP_DAYS = 365
STAGE_RANK = {"procure": 0, "prepare": 1, "execute": 2, "characterize": 3}


def parse_date(s, ctx=""):
    if not isinstance(s, str):
        raise ValueError("日期必须是 ISO 字符串%s，得到: %r" % (("（" + ctx + "）") if ctx else "", s))
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ValueError("非法 ISO 日期%s: %r" % (("（" + ctx + "）") if ctx else "", s))


def free_intervals(lo, hi, occupied):
    occ = []
    for s, e in occupied:
        s2, e2 = max(s, lo), min(e, hi)
        if s2 < e2:
            occ.append((s2, e2))
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


def person_covers(person, skills_needed, s, e):
    if not set(skills_needed) <= set(person.get("skills", [])):
        return False
    windows = person.get("available_windows")
    if not windows:
        return True  # 未声明可用窗口 → 视为全时段可用
    for w in windows:
        ws = parse_date(w["start"], "available_windows.start")
        we = parse_date(w["end"], "available_windows.end")
        if ws <= s and e <= we:
            return True
    return False


def find_slot(lo, hi, occupied, dur, personnel, skills_needed):
    """在 [lo, hi) 内找最早起点 s：设备 [s, s+dur) 空闲且有合格人员窗口覆盖。"""
    for fs, fe in free_intervals(lo, hi, occupied):
        s = fs
        while s + timedelta(days=dur) <= fe:
            e = s + timedelta(days=dur)
            if any(person_covers(p, skills_needed, s, e) for p in personnel):
                return s
            s = s + timedelta(days=1)
    return None


def schedule_plan(plan, resources, case, calendars):
    """返回 (record, occupations)。record['schedulable'] 为 False 时 occupations 为空。"""
    ref = parse_date(case["reference_date"], "case.reference_date")
    deadline = case.get("deadline")
    cap_end = ref + timedelta(days=SLIP_CAP_DAYS)
    cons_by_id = {c["id"]: c for c in resources.get("consumables", [])}
    appr_by_id = {a["id"]: a for a in resources.get("approvals", [])}
    personnel = resources.get("personnel", [])
    skills = plan.get("skill_needs", [])

    waits = []
    ready = ref

    # 阶段 0：采购等待
    for cn in plan.get("consumable_needs", []):
        c = cons_by_id.get(cn.get("consumable_id"))
        if c is None or c.get("in_stock", False):
            continue
        lead = int(c.get("lead_time_days", 0))
        arrival = ref + timedelta(days=lead)
        if arrival > ready:
            ready = arrival
        waits.append({"kind": "consumable_lead_time",
                      "item": cn.get("consumable_id"),
                      "wait_until": arrival.isoformat(),
                      "reason": "耗材 %s（%s）货期 %d 天，%s 到货"
                                % (cn.get("consumable_id"), c.get("name", ""), lead, arrival.isoformat())})
    # 审批等待
    for aid in plan.get("approval_needs", []):
        ap = appr_by_id.get(aid)
        if ap and ap.get("status") == "pending" and ap.get("expected_date"):
            ed = parse_date(ap["expected_date"], "approvals.expected_date")
            if ed > ready:
                ready = ed
            waits.append({"kind": "approval_pending", "item": aid,
                          "wait_until": ed.isoformat(),
                          "reason": "审批 %s（%s）预计 %s 获批" % (aid, ap.get("name", ""), ed.isoformat())})

    # 阶段 1：准备
    prep_days = int(plan.get("prep_days", 0))
    prep_start = ready
    prep_end = ready + timedelta(days=prep_days)
    stages = []
    if prep_days > 0:
        stages.append({"stage": "prepare", "resource": "-",
                       "start": prep_start.isoformat(), "end": prep_end.isoformat()})

    # 阶段 2/3：执行 → 表征（按 STAGE_RANK 排序，稳定）
    needs = sorted(enumerate(plan.get("equipment_needs", [])),
                   key=lambda t: (STAGE_RANK.get(t[1].get("stage", "execute"), 2), t[0]))
    cursor = prep_end
    occupations = []  # (equipment_id, start, end)
    first_execution_start = None
    for _, need in needs:
        eid = need.get("equipment_id")
        stage = need.get("stage", "execute")
        dur = int(need.get("duration_days", 1))
        lo = parse_date(need["earliest_use"], "equipment_needs.earliest_use")
        hi = parse_date(need["latest_use"], "equipment_needs.latest_use") \
            if need.get("latest_use") else cap_end
        hi = min(hi, cap_end)
        lo = max(lo, cursor)
        if lo >= hi:
            return {"plan_id": plan["plan_id"], "schedulable": False,
                    "reason": "设备 %s（阶段 %s）需求窗口与上游阶段结束时间无交集，或超出 %d 天顺延上限。"
                              % (eid, stage, SLIP_CAP_DAYS)}, []
        s = find_slot(lo, hi, calendars.get(eid, []), dur, personnel, skills)
        if s is None:
            return {"plan_id": plan["plan_id"], "schedulable": False,
                    "reason": "设备 %s（阶段 %s）在 [%s, %s) 内（含 %d 天顺延上限）找不到 >= %d 天且人员覆盖的空档。"
                              % (eid, stage, lo.isoformat(), hi.isoformat(), SLIP_CAP_DAYS, dur)}, []
        e = s + timedelta(days=dur)
        if s > cursor:
            waits.append({"kind": "equipment_booking", "item": eid,
                          "wait_until": s.isoformat(),
                          "reason": "设备 %s（阶段 %s）档期冲突，顺延至 %s" % (eid, stage, s.isoformat())})
        stages.append({"stage": stage, "resource": eid,
                       "start": s.isoformat(), "end": e.isoformat()})
        if stage == "execute" and first_execution_start is None:
            first_execution_start = s
        cursor = e
        occupations.append((eid, s, e))

    finish = cursor
    past_deadline = bool(deadline) and finish > parse_date(deadline, "case.deadline")
    record = {
        "plan_id": plan["plan_id"],
        "schedulable": True,
        "earliest_start": ready.isoformat(),
        "first_execution_start": first_execution_start.isoformat() if first_execution_start else None,
        "earliest_finish": finish.isoformat(),
        "past_deadline": past_deadline,
        "critical_waits": [w for w in waits if w["wait_until"] > ref.isoformat()],
        "stages": stages,
    }
    return record, occupations


def build_gantt(case, records, deadline, note=None):
    lines = []
    if note:
        lines.append("> %s" % note)
        lines.append("")
    lines.append("# 排期甘特表（gantt）")
    lines.append("")
    lines.append("- case_id: %s；基准日 %s；deadline %s；1 格 = 1 天；半开区间 [start, end)。"
                 % (case.get("case_id", "UNKNOWN"), case.get("reference_date"), deadline or "（未给）"))
    lines.append("")
    lines.append("| 方案 | 阶段 | 资源 | 开始 | 结束 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in records:
        if not r.get("schedulable"):
            lines.append("| %s | %s | - | - | - |" % (r["plan_id"], r.get("status", "schedule_infeasible")))
            continue
        for st in r["stages"]:
            lines.append("| %s | %s | %s | %s | %s |" % (
                r["plan_id"], st["stage"], st["resource"], st["start"], st["end"]))
    lines.append("")

    sched = [r for r in records if r.get("schedulable") and r["stages"]]
    if not sched:
        lines.append("（无可绘制的时间线）")
        lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"

    t0 = min(parse_date(r["earliest_start"]) for r in sched)
    t1 = max(parse_date(r["earliest_finish"]) for r in sched)
    span = (t1 - t0).days
    width = span
    dl = parse_date(deadline, "case.deadline") if deadline else None
    dl_col = (dl - t0).days if dl and t0 <= dl <= t1 else None

    tens = []
    units = []
    base = []
    for i in range(width):
        tens.append(str((i // 10) % 10) if i % 10 == 0 else " ")
        units.append(str(i % 10))
        base.append("|" if dl_col is not None and i == dl_col else "-")
    lines.append("```")
    lines.append("t0 = %s（行首字符对应日期 t0+列偏移天）；'|' 列 = deadline %s"
                 % (t0.isoformat(), dl.isoformat() if dl_col is not None else "（超出图幅或未给）"))
    lines.append("列偏移(十位): " + "".join(tens))
    lines.append("列偏移(个位): " + "".join(units))
    lines.append("基准线       : " + "".join(base))
    for r in sched:
        for st in r["stages"]:
            s = parse_date(st["start"])
            e = parse_date(st["end"])
            bar = [" "] * width
            for i in range((s - t0).days, min((e - t0).days, width)):
                bar[i] = "#"
            label = "%s %-12s" % (r["plan_id"], st["stage"])
            lines.append("%-14s: %s" % (label, "".join(bar).rstrip()))
    lines.append("```")
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="最早可启动排期：采购等待→准备→执行→表征排队，资源冲突顺延（上限 365 天），"
                    "输出 timeline_report.json 与 gantt.md。")
    ap.add_argument("--facts", required=True, help="facts JSON（resources_available + plan_requirements）")
    ap.add_argument("--case", required=True, help="case JSON（reference_date/deadline 等）")
    ap.add_argument("--out-dir", required=True, help="输出目录（timeline_report.json, gantt.md）")
    ap.add_argument("--constraints", default=None,
                    help="可选：constraints_report.json；verdict=infeasible 的方案跳过排期")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/甘特表顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args(argv)

    import os
    try:
        with open(args.facts, "r", encoding="utf-8") as f:
            facts = json.load(f)
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        infeasible = set()
        if args.constraints:
            with open(args.constraints, "r", encoding="utf-8") as f:
                creport = json.load(f)
            infeasible = {p["plan_id"] for p in creport.get("plans", [])
                          if p.get("verdict") == "infeasible"}
    except (OSError, json.JSONDecodeError) as e:
        print("输入错误：%s" % e, file=sys.stderr)
        return 2

    resources = facts.get("resources_available", {})
    plans = facts.get("plan_requirements", [])
    if not plans:
        print("输入错误：facts 中 plan_requirements 为空。", file=sys.stderr)
        return 2

    calendars = {}
    for eq in resources.get("equipment", []):
        ivs = []
        for b in eq.get("booked_windows", []):
            ivs.append((parse_date(b["start"], "booked_windows.start"),
                        parse_date(b["end"], "booked_windows.end")))
        calendars[eq["id"]] = ivs

    records = []
    try:
        for plan in plans:
            pid = plan["plan_id"]
            if pid in infeasible:
                records.append({"plan_id": pid, "schedulable": False,
                                "status": "skipped_infeasible",
                                "reason": "constraints.py 裁决 infeasible，跳过排期。"})
                continue
            rec, occ = schedule_plan(plan, resources, case, calendars)
            if rec.get("schedulable"):
                rec["status"] = "scheduled"
                for eid, s, e in occ:
                    calendars.setdefault(eid, []).append((s, e))
            else:
                rec["status"] = "schedule_infeasible"
            records.append(rec)
    except ValueError as e:
        print("输入错误：%s" % e, file=sys.stderr)
        return 2

    n_sched = sum(1 for r in records if r.get("schedulable"))
    report = {
        "case_id": case.get("case_id", "UNKNOWN"),
        "reference_date": case.get("reference_date"),
        "deadline": case.get("deadline"),
        "slip_cap_days": SLIP_CAP_DAYS,
        "plans": records,
        "n_scheduled": n_sched,
        "n_unschedulable": len(records) - n_sched,
    }
    if args.note:
        report["note"] = args.note
    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "timeline_report.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    gpath = os.path.join(args.out_dir, "gantt.md")
    with open(gpath, "w", encoding="utf-8") as f:
        f.write(build_gantt(case, records, case.get("deadline"), note=args.note))
    print("已写出: %s" % jpath)
    print("已写出: %s" % gpath)
    for r in records:
        if r.get("schedulable"):
            print("方案 %s: earliest_start=%s first_execution=%s earliest_finish=%s past_deadline=%s"
                  % (r["plan_id"], r["earliest_start"], r.get("first_execution_start"),
                     r["earliest_finish"], r["past_deadline"]))
        else:
            print("方案 %s: %s — %s" % (r["plan_id"], r.get("status"), r.get("reason", "")))
    if n_sched == 0:
        print("质量门拦截：无任何方案可在资源日历内排出时间线。")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
