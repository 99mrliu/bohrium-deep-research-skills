#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schedule_forge.py — 排期与预约可行性工程：把 est_days 拍脑袋变成机时核算。

子命令：
  throughput  逐设备核算预约吞吐（slots_per_week × slot_hours × window 周数），
              对 case.candidate_plans 与可选 plan.json 计算机时需求 vs 可用机时，
              输出瓶颈设备、所需周数、超期天数（带算式）。
  schedule    输入步骤表 JSON，按周/按 slot 贪心排程，输出 schedule.json、
              gantt.md、cashflow.md；检测依赖冲突、slot 溢出、deadline 超期、双订。
  repair      超期时输出修复选项表（提高并行批次 / 合并表征批次 / 削减重复 /
              改用可替代设备），每项给出节省天数与代价。

仅 Python 3 标准库；确定性；缺键不崩（exit 0 输出 partial 报告）；--help 可用。
"""

import argparse
import datetime
import json
import math
import os
import re
import sys

DEFAULT_START = "2026-01-05"  # 确定性默认开工日（周一），可用 --start 覆盖


# ---------------------------------------------------------------- 通用工具

def eprint(*a):
    print(*a, file=sys.stderr)


def load_json(path):
    """读取 JSON 文件；失败返回 None（不抛异常）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        eprint(f"[warn] 无法读取 {path}: {exc}")
        return None


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def num(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def ceil_div(a, b):
    if b <= 0:
        return None
    return int(math.ceil(a / b - 1e-12))


# ---------------------------------------------------------------- 设备合同解析

def extract_embedded_equipment(note_text):
    """从 equipment_domain_note 文本中提取内嵌的 JSON 设备片段（含 "id" 字段）。
    返回 (设备 dict 列表, 提取到的原始片段数)。"""
    found = []
    if not isinstance(note_text, str) or not note_text.strip():
        return found, 0
    n = len(note_text)
    i, snippets = 0, 0
    while i < n:
        if note_text[i] == "{":
            depth = 0
            j = i
            while j < n:
                c = note_text[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth == 0:
                snippet = note_text[i:j + 1]
                snippets += 1
                try:
                    obj = json.loads(snippet)
                    if isinstance(obj, dict) and obj.get("id"):
                        found.append(obj)
                except Exception:  # noqa: BLE001
                    pass  # 非 JSON 大括号文本，跳过
                i = j + 1
                continue
        i += 1
    return found, snippets


def build_equipment_table(case):
    """合并 case.resource_contract.equipment 与 equipment_domain_note 内嵌设备。
    返回 {eq_id: {..., weekly_hours, window_hours, source}} 与合并说明列表。"""
    table = {}
    notes = []
    rc = (case or {}).get("resource_contract") or {}
    for eq in rc.get("equipment") or []:
        if not isinstance(eq, dict) or not eq.get("id"):
            continue
        table[eq["id"]] = dict(eq, source="resource_contract.equipment")
    embedded, _snip = extract_embedded_equipment(case.get("equipment_domain_note"))
    for eq in embedded:
        eid = eq.get("id")
        if eid in table:
            notes.append(f"equipment_domain_note 内嵌设备 {eid} 与 equipment 列表重复，"
                         f"以 equipment 列表为准。")
        else:
            table[eid] = dict(eq, source="equipment_domain_note(内嵌JSON片段)")
            notes.append(f"从 equipment_domain_note 解析出补充设备 {eid}"
                         f"（{eq.get('name', '未命名')}），已并入设备表。")
    for eid, eq in table.items():
        bk = eq.get("booking") or {}
        spw = num(bk.get("slots_per_week"), 0)
        sh = num(bk.get("slot_hours"), 0)
        wd = num(bk.get("window_days"), 0)
        weekly = spw * sh
        weeks = int(math.floor(wd / 7.0)) if wd else 0  # 保守：只计完整周
        eq["weekly_hours"] = weekly
        eq["window_weeks"] = weeks
        eq["window_hours"] = weekly * weeks
    return table, notes


# ---------------------------------------------------------------- 方案需求解析

def demand_from_cost_items(plan, equip_table):
    """候选方案无步骤表：用 cost_items 反推各设备机时。
    匹配规则：item 显式带 equipment 字段优先；否则按 unit_price == price_per_hour
    匹配设备（quantity 视为机时小时数，属假设，结果标注 assumption）。"""
    demand = {}       # eq_id -> hours
    assumptions = []
    unmatched = []
    by_price = {}
    for eid, eq in equip_table.items():
        by_price.setdefault(num(eq.get("price_per_hour"), -1), []).append(eid)
    for item in plan.get("cost_items") or []:
        if not isinstance(item, dict):
            continue
        qty = num(item.get("quantity"), 0)
        eid = item.get("equipment")
        if eid and eid in equip_table:
            demand[eid] = demand.get(eid, 0) + qty
            continue
        price = num(item.get("unit_price"), None)
        if price is not None and price in by_price and len(by_price[price]) == 1:
            eid = by_price[price][0]
            demand[eid] = demand.get(eid, 0) + qty
            assumptions.append(
                f"cost_item「{item.get('item', '?')}」按 unit_price={price} 匹配到设备 "
                f"{eid}，quantity={qty} 视为机时小时数（假设）。")
        else:
            unmatched.append(item.get("item", str(item)[:40]))
    return demand, assumptions, unmatched


def normalize_steps(steps_raw):
    """规范化步骤表，返回 (steps, errors)。"""
    steps, errors = [], []
    if not isinstance(steps_raw, list):
        return steps, ["steps 不是列表"]
    for idx, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            errors.append(f"steps[{idx}] 不是对象，跳过")
            continue
        sid = s.get("id") or f"S{idx + 1}"
        deps = s.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        steps.append({
            "id": sid,
            "name": s.get("name") or sid,
            "equipment": s.get("equipment"),
            "equip_hours": num(s.get("equip_hours"), 0),
            "samples": int(num(s.get("samples"), 1)),
            "depends_on": list(deps),
            "parallel": bool(s.get("parallel", False)),
            "per_sample_hours": s.get("per_sample_hours"),
            "batch_capacity": s.get("batch_capacity"),
            "replicates": int(num(s.get("replicates"), 1)),
            "batch_group": s.get("batch_group"),
            "alt_equipment": s.get("alt_equipment") or [],
            "reagents": s.get("reagents") or [],
            "prep_days": int(num(s.get("prep_days"), 0)),
        })
    return steps, errors


def demand_from_steps(steps):
    demand = {}
    for s in steps:
        eq = s.get("equipment")
        if eq:
            demand[eq] = demand.get(eq, 0) + num(s.get("equip_hours"), 0)
    return demand


def check_arithmetic(plan):
    """核对 cost_items 小计与 total_cost，返回问题列表（带算式）。"""
    problems = []
    items = plan.get("cost_items") or []
    sum_sub = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        up, qty, sub = num(it.get("unit_price")), num(it.get("quantity")), num(it.get("subtotal"))
        calc = up * qty
        sum_sub += sub
        if abs(calc - sub) > 0.01:
            problems.append(
                f"「{it.get('item', '?')}」subtotal 算术错误：{up}×{qty}={calc} ≠ 声明 {sub}")
    total = num(plan.get("total_cost"), 0)
    if items and abs(sum_sub - total) > 0.01:
        problems.append(f"total_cost 算术错误：Σsubtotal={sum_sub} ≠ 声明 total_cost={total}")
    return problems


# ---------------------------------------------------------------- throughput

def feasibility_for_demand(demand, equip_table, deadline_days):
    """对每个设备需求核算周数/天数，返回逐设备明细与整体瓶颈。"""
    rows = []
    bottleneck = None
    for eid, hours in sorted(demand.items()):
        eq = equip_table.get(eid)
        if eq is None:
            rows.append({"equipment": eid, "demand_hours": hours, "known": False,
                         "issue": "设备不在 resource_contract.equipment，"
                                  "也不在 equipment_domain_note 内嵌片段中：无法核算吞吐"})
            continue
        weekly = eq["weekly_hours"]
        if weekly <= 0:
            rows.append({"equipment": eid, "demand_hours": hours, "known": True,
                         "weekly_hours": 0, "issue": "booking 信息缺失或为 0，无法核算"})
            continue
        weeks = ceil_div(hours, weekly)
        days = weeks * 7
        window_ok = hours <= eq["window_hours"] + 1e-9
        formula = (f"需求 {hours}h ÷ 每周 {weekly}h"
                   f"（{int(num((eq.get('booking') or {}).get('slots_per_week')))} slots/周"
                   f" × {num((eq.get('booking') or {}).get('slot_hours'))}h/slot）"
                   f" = {weeks} 周 = {days} 天")
        row = {"equipment": eid, "name": eq.get("name"), "known": True,
               "demand_hours": hours, "weekly_hours": weekly,
               "window_days": num((eq.get("booking") or {}).get("window_days")),
               "window_hours": eq["window_hours"],
               "weeks_needed": weeks, "days_needed": days,
               "fits_window": window_ok, "formula": formula,
               "source": eq.get("source")}
        rows.append(row)
        if bottleneck is None or days > bottleneck["days_needed"]:
            bottleneck = row
    overrun = 0
    if bottleneck is not None and deadline_days:
        overrun = max(0, bottleneck["days_needed"] - deadline_days)
    return rows, bottleneck, overrun


def cmd_throughput(args):
    case = load_json(args.case) or {}
    equip_table, merge_notes = build_equipment_table(case)
    rc = case.get("resource_contract") or {}
    deadline = num(rc.get("deadline_days"), 0)

    capacity_rows = []
    for eid, eq in sorted(equip_table.items()):
        bk = eq.get("booking") or {}
        capacity_rows.append({
            "equipment": eid, "name": eq.get("name"),
            "price_per_hour": eq.get("price_per_hour"),
            "slots_per_week": bk.get("slots_per_week"),
            "slot_hours": bk.get("slot_hours"),
            "window_days": bk.get("window_days"),
            "weekly_hours": eq["weekly_hours"],
            "window_weeks": eq["window_weeks"],
            "window_hours": eq["window_hours"],
            "source": eq.get("source"),
            "formula": f"{bk.get('slots_per_week')} slots/周 × {bk.get('slot_hours')} h"
                       f" = {eq['weekly_hours']} h/周；window {bk.get('window_days')} 天"
                       f" = {eq['window_weeks']} 完整周 → {eq['window_hours']} h",
        })

    plans_report = []
    seen = set()
    for plan in case.get("candidate_plans") or []:
        ver = plan.get("version", f"candidate#{len(plans_report) + 1}")
        seen.add(ver)
        demand, assumptions, unmatched = demand_from_cost_items(plan, equip_table)
        rows, bottleneck, overrun = feasibility_for_demand(demand, equip_table, deadline)
        est = num(plan.get("est_days"), 0)
        bdays = bottleneck["days_needed"] if bottleneck else 0
        est_verdict = ("est_days 低于瓶颈机时所需天数，不可信" if est < bdays
                       else ("est_days 超过 deadline" if est > deadline
                             else "est_days 不低于瓶颈下界且未超 deadline"
                                  "（但仍需 schedule 做全资源联检）"))
        plans_report.append({
            "version": ver, "author": plan.get("author"),
            "est_days": plan.get("est_days"),
            "demand_hours_by_equipment": demand,
            "equipment_rows": rows,
            "bottleneck": bottleneck,
            "deadline_days": deadline, "overrun_days": overrun,
            "feasible_by_throughput": bool(bottleneck) and overrun == 0
            and all(r.get("known") for r in rows),
            "est_days_verdict": est_verdict,
            "arithmetic_problems": check_arithmetic(plan),
            "assumptions": assumptions, "unmatched_cost_items": unmatched,
        })

    extra = None
    if args.plan:
        pj = load_json(args.plan)
        if pj:
            steps, errs = normalize_steps(pj.get("steps"))
            demand = demand_from_steps(steps)
            rows, bottleneck, overrun = feasibility_for_demand(demand, equip_table, deadline)
            extra = {"version": pj.get("version", "user-plan"),
                     "source_file": args.plan,
                     "demand_hours_by_equipment": demand,
                     "equipment_rows": rows, "bottleneck": bottleneck,
                     "deadline_days": deadline, "overrun_days": overrun,
                     "feasible_by_throughput": bool(bottleneck) and overrun == 0,
                     "step_errors": errs}

    status = "complete" if case else "partial"
    report = {
        "status": status,
        "case_id": case.get("case_id"),
        "deadline_days": deadline,
        "budget_cap": rc.get("budget_cap"),
        "contract_disclaimer": rc.get("disclaimer"),
        "merge_notes": merge_notes,
        "capacity_table": capacity_rows,
        "candidate_assessments": plans_report,
        "user_plan_assessment": extra,
        "method_note": "吞吐核算只按各设备独立判断（机时需求 ÷ 每周可用机时），"
                       "是必要非充分条件；先后/并行关系的充分判定见 schedule 子命令。",
    }

    lines = ["# throughput 体检报告",
             f"case_id: {report['case_id']}    deadline: {deadline} 天",
             f"合同声明: {rc.get('disclaimer', '（无）')}", ""]
    for n in merge_notes:
        lines.append(f"- 合并说明: {n}")
    lines.append("\n## 设备吞吐表")
    for c in capacity_rows:
        lines.append(f"- {c['equipment']} {c.get('name') or ''}: {c['formula']}"
                     f"（来源: {c['source']}）")
    for pr in plans_report:
        lines.append(f"\n## 候选 {pr['version']}（est_days={pr['est_days']}）")
        for r in pr["equipment_rows"]:
            if r.get("known") and r.get("weekly_hours"):
                lines.append(f"- {r['equipment']}: {r['formula']}"
                             f"{'  ✅ window 内可容纳' if r['fits_window'] else '  ❌ 超出 window 总机时'}")
            else:
                lines.append(f"- {r['equipment']}: {r.get('issue', '未知问题')}")
        b = pr.get("bottleneck")
        if b:
            lines.append(f"- 瓶颈设备: {b['equipment']}（{b['days_needed']} 天）；"
                         f"deadline {deadline} 天 → "
                         f"{'超期 ' + str(pr['overrun_days']) + ' 天' if pr['overrun_days'] else '未超期'}")
        lines.append(f"- est_days 判定: {pr['est_days_verdict']}")
        for p in pr["arithmetic_problems"]:
            lines.append(f"- 算术问题: {p}")
        for a in pr["assumptions"]:
            lines.append(f"- 假设: {a}")
    if extra:
        b = extra.get("bottleneck")
        lines.append(f"\n## 用户方案 {extra['version']}（{extra['source_file']}）")
        for r in extra["equipment_rows"]:
            if r.get("known") and r.get("weekly_hours"):
                lines.append(f"- {r['equipment']}: {r['formula']}")
            else:
                lines.append(f"- {r['equipment']}: {r.get('issue', '未知问题')}")
        if b:
            lines.append(f"- 瓶颈: {b['equipment']} {b['days_needed']} 天，"
                         f"超期 {extra['overrun_days']} 天")
    report_md = "\n".join(lines) + "\n"

    outdir = args.outdir or "."
    write_json(os.path.join(outdir, "throughput.json"), report)
    write_text(os.path.join(outdir, "throughput.md"), report_md)
    print(report_md)
    print(f"[ok] 已写出 {os.path.join(outdir, 'throughput.json')} 与 throughput.md",
          file=sys.stderr)
    return 0


# ---------------------------------------------------------------- schedule

def week_dates(start_date, week_idx):
    """第 week_idx 周（0 起）的周一/周日日期。"""
    mon = start_date + datetime.timedelta(days=7 * week_idx)
    sun = mon + datetime.timedelta(days=6)
    return mon.isoformat(), sun.isoformat()


def detect_dep_problems(steps):
    """检测依赖问题：未知依赖、环。返回 (errors, order 或 None)。"""
    ids = {s["id"] for s in steps}
    errors = []
    for s in steps:
        for d in s["depends_on"]:
            if d not in ids:
                errors.append(f"步骤 {s['id']} 依赖未知步骤 {d}")
    # 拓扑排序（Kahn），检测环
    indeg = {s["id"]: 0 for s in steps}
    adj = {s["id"]: [] for s in steps}
    for s in steps:
        for d in s["depends_on"]:
            if d in ids:
                indeg[s["id"]] += 1
                adj[d].append(s["id"])
    queue = [i for i in indeg if indeg[i] == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(order) < len(steps):
        cyc = [i for i in indeg if indeg[i] > 0]
        errors.append(f"检测到依赖环，涉及步骤: {', '.join(sorted(cyc))}")
        return errors, None
    return errors, order


def cmd_schedule(args):
    case = load_json(args.case) or {}
    plan = load_json(args.steps) or {}
    equip_table, merge_notes = build_equipment_table(case)
    rc = case.get("resource_contract") or {}
    deadline_days = int(num(rc.get("deadline_days"), 0))
    start_date = args.start or DEFAULT_START
    try:
        d0 = datetime.date.fromisoformat(start_date)
    except ValueError:
        d0 = datetime.date.fromisoformat(DEFAULT_START)
        eprint(f"[warn] --start {start_date} 非法，改用 {DEFAULT_START}")

    steps, norm_errors = normalize_steps(plan.get("steps"))
    dep_errors, topo = detect_dep_problems(steps)
    warnings = list(norm_errors)

    # slot 池：eq_id -> 每周 slots_per_week 个 slot，每 slot slot_hours
    # 状态：occupied[eq][week] = 已占用 slot 数；step_end_slot[step_id] = (week, slot_index)
    occupied = {}
    step_finish = {}   # step_id -> (week_idx, slot_idx_after)  该步骤占到的最后位置
    schedule_rows = []
    double_booking = []
    unknown_eq = []

    def slots_of(eid):
        eq = equip_table.get(eid)
        if not eq:
            return 0, 0
        bk = eq.get("booking") or {}
        return int(num(bk.get("slots_per_week"))), num(bk.get("slot_hours"))

    if topo:
        for sid in topo:
            s = next(x for x in steps if x["id"] == sid)
            eid = s["equipment"]
            hours = num(s["equip_hours"])
            if eid not in equip_table:
                unknown_eq.append(f"步骤 {sid} 使用未知设备 {eid}，无法排程")
                step_finish[sid] = (0, 0)
                continue
            spw, sh = slots_of(eid)
            if spw <= 0 or sh <= 0:
                warnings.append(f"设备 {eid} booking 信息缺失，步骤 {sid} 无法排程")
                step_finish[sid] = (0, 0)
                continue
            need_slots = ceil_div(hours, sh)
            # 依赖：必须排在所有依赖完成位置之后
            w_start, slot_start = 0, 0
            for dep in s["depends_on"]:
                fw, fs = step_finish.get(dep, (0, 0))
                if (fw, fs) > (w_start, slot_start):
                    w_start, slot_start = fw, fs
            if s.get("prep_days"):
                extra_weeks = int(math.ceil(s["prep_days"] / 7.0))
                w_start += extra_weeks
            remaining = need_slots
            if remaining == 0:  # 零机时步骤（如纯记录）：不占 slot，跟随依赖位置
                step_finish[sid] = (w_start, slot_start)
                continue
            w, sl = w_start, slot_start
            first_week, first_slot = None, None
            while remaining > 0:
                occ = occupied.setdefault(eid, {})
                used = occ.get(w, 0)
                avail_from = max(used, sl if w == w_start else 0)
                free = spw - avail_from
                if free <= 0:
                    w += 1
                    sl = 0
                    continue
                take = min(free, remaining)
                occ[w] = avail_from + take
                if occ[w] > spw:  # 双订自检（贪心不应触发，作为不变量校验）
                    double_booking.append(
                        f"设备 {eid} 第 {w + 1} 周占用 {occ[w]} slot 超过上限 {spw}")
                if first_week is None:
                    first_week, first_slot = w, avail_from
                remaining -= take
                sl = 0
                last_week, last_slot = w, avail_from + take
                w += 1
            step_finish[sid] = (last_week, last_slot)
            mon0, sun0 = week_dates(d0, first_week)
            mon1, sun1 = week_dates(d0, last_week)
            schedule_rows.append({
                "step_id": sid, "name": s["name"], "equipment": eid,
                "slots_needed": need_slots,
                "start_week": first_week + 1, "end_week": last_week + 1,
                "start_date": mon0, "end_date": sun1,
                "week_span": f"{mon0} ~ {sun1}",
                "depends_on": s["depends_on"],
            })

    # 汇总：逐周 slot 占用
    weekly_usage = {}
    for eid, occ in occupied.items():
        spw, sh = slots_of(eid)
        for w, u in sorted(occ.items()):
            weekly_usage.setdefault(w, {})[eid] = {"used_slots": u, "cap_slots": spw}

    last_week_idx = 0
    for eid, occ in occupied.items():
        if occ:
            last_week_idx = max(last_week_idx, max(occ))
    total_days = (last_week_idx + 1) * 7 if schedule_rows else 0
    overrun_days = max(0, total_days - deadline_days) if deadline_days else 0

    # window 溢出检查：某设备被排到其 window_days 之外
    window_overflow = []
    for eid, occ in occupied.items():
        eq = equip_table[eid]
        wdays = int(num((eq.get("booking") or {}).get("window_days")))
        if wdays and occ:
            wmax = max(occ)
            if (wmax + 1) * 7 > wdays:
                window_overflow.append(
                    f"设备 {eid} 被排至第 {wmax + 1} 周（{(wmax + 1) * 7} 天），"
                    f"超出其预约窗口 {wdays} 天")

    # ---------------- 成本与现金流
    reagents = {r.get("id"): r for r in rc.get("reagents") or []
                if isinstance(r, dict) and r.get("id")}
    lead_weeks = int(num(args.reagent_lead_weeks, 1))
    weekly_cost = {}
    cost_notes = []
    for row in schedule_rows:
        eq = equip_table.get(row["equipment"]) or {}
        price = num(eq.get("price_per_hour"))
        sh = num((eq.get("booking") or {}).get("slot_hours"))
        cost = row["slots_needed"] * sh * price
        row["equipment_cost"] = round(cost, 2)
        weekly_cost[row["end_week"] - 1] = weekly_cost.get(row["end_week"] - 1, 0) + cost
    for s in steps:
        for ru in s["reagents"]:
            rid = ru.get("id") if isinstance(ru, dict) else ru
            qty = num(ru.get("quantity"), 0) if isinstance(ru, dict) else 0
            rg = reagents.get(rid)
            if not rg:
                cost_notes.append(f"步骤 {s['id']} 的试剂 {rid} 不在合同 reagents 中")
                continue
            pack = num(rg.get("pack_size"), 1) or 1
            packs = ceil_div(qty, pack) or 0
            cost = packs * num(rg.get("unit_price"))
            use_week = (step_finish.get(s["id"], (0, 0))[0])
            buy_week = max(0, use_week - lead_weeks)
            weekly_cost[buy_week] = weekly_cost.get(buy_week, 0) + cost
            cost_notes.append(
                f"试剂 {rid}: 需求 {qty}{rg.get('unit', '')} ÷ 包装 {pack} = {packs} 包"
                f" × {num(rg.get('unit_price'))} 元 = {cost} 元，第 {buy_week + 1} 周采购"
                f"（前置 {lead_weeks} 周）")

    budget_cap = num(rc.get("budget_cap"), 0)
    cum = 0.0
    cash_rows = []
    for w in range(last_week_idx + 1):
        c = round(weekly_cost.get(w, 0.0), 2)
        cum = round(cum + c, 2)
        mon, sun = week_dates(d0, w)
        cash_rows.append({"week": w + 1, "date_range": f"{mon} ~ {sun}",
                          "cost": c, "cumulative": cum,
                          "over_budget": bool(budget_cap) and cum > budget_cap})

    # ---------------- 输出
    outdir = args.outdir or "."
    header = ("合成示例输出，非正式测评结果\n" if args.synthetic else "")
    sched = {
        "status": "complete" if not dep_errors else "partial",
        "start_date": d0.isoformat(), "deadline_days": deadline_days,
        "total_days": total_days, "overrun_days": overrun_days,
        "schedule": schedule_rows, "weekly_usage": {
            str(w + 1): v for w, v in sorted(weekly_usage.items())},
        "detections": {
            "dependency_conflicts": dep_errors,
            "slot_overflow": window_overflow,
            "deadline_overrun_days": overrun_days,
            "double_booking": double_booking,
            "unknown_equipment": unknown_eq,
        },
        "merge_notes": merge_notes, "warnings": warnings,
    }
    write_json(os.path.join(outdir, "schedule.json"), sched)

    # 甘特图
    step_names = {}
    for s in steps:
        step_names[s["id"]] = s["name"]
    g = [header + "# 甘特图（逐周，每格=1周）",
         f"开工 {d0.isoformat()}，deadline {deadline_days} 天，"
         f"总工期 {total_days} 天，超期 {overrun_days} 天\n"]
    ncol = max(last_week_idx + 1, int(math.ceil(deadline_days / 7.0)) if deadline_days else 1)
    hdr = "步骤".ljust(22) + "设备".ljust(10) + "".join(
        f"W{w + 1:<4}" for w in range(ncol))
    g.append(hdr)
    for row in schedule_rows:
        cells = []
        for w in range(ncol):
            if row["start_week"] - 1 <= w <= row["end_week"] - 1:
                cells.append("██   " if w + 1 <= ncol else "██")
            else:
                cells.append("··   ")
        line = (row["step_id"] + " " + (step_names.get(row["step_id"], "") or ""))[:20].ljust(22)
        line += row["equipment"].ljust(10) + "".join(cells)
        g.append(line)
    if deadline_days:
        dw = int(math.ceil(deadline_days / 7.0))
        g.append("".ljust(22) + "".ljust(10)
                 + "".join(("|DL  " if w == dw - 1 else "     ") for w in range(ncol))
                 + f"  ← deadline 第 {deadline_days} 天")
    if dep_errors or window_overflow or double_booking or unknown_eq:
        g.append("\n## 检测到的问题")
        for lst, tag in [(dep_errors, "依赖冲突"), (window_overflow, "window 溢出"),
                         (double_booking, "设备双订"), (unknown_eq, "未知设备")]:
            for e in lst:
                g.append(f"- [{tag}] {e}")
    write_text(os.path.join(outdir, "gantt.md"), "\n".join(g) + "\n")

    # 现金流
    c = [header + "# 按周累计现金流（设备机时 + 试剂采购前置）",
         f"预算上限 budget_cap = {budget_cap} 元（前瞻合同价，非实际报价）\n",
         "| 周 | 日期区间 | 当周支出(元) | 累计(元) | 超预算 |",
         "|---|---|---|---|---|"]
    for r in cash_rows:
        c.append(f"| W{r['week']} | {r['date_range']} | {r['cost']:.2f} "
                 f"| {r['cumulative']:.2f} | {'❌' if r['over_budget'] else ''} |")
    c.append("\n## 成本计算说明")
    for n in cost_notes:
        c.append(f"- {n}")
    write_text(os.path.join(outdir, "cashflow.md"), "\n".join(c) + "\n")

    print(f"[ok] 总工期 {total_days} 天 / deadline {deadline_days} 天，"
          f"超期 {overrun_days} 天；问题: 依赖冲突 {len(dep_errors)}，"
          f"window 溢出 {len(window_overflow)}，双订 {len(double_booking)}",
          file=sys.stderr)
    print(f"[ok] 已写出 schedule.json / gantt.md / cashflow.md 到 {outdir}",
          file=sys.stderr)
    return 0


# ---------------------------------------------------------------- repair

def cmd_repair(args):
    case = load_json(args.case) or {}
    plan = load_json(args.steps) or {}
    equip_table, _notes = build_equipment_table(case)
    rc = case.get("resource_contract") or {}
    deadline_days = int(num(rc.get("deadline_days"), 0))

    steps, norm_errors = normalize_steps(plan.get("steps"))
    demand = demand_from_steps(steps)
    rows, bottleneck, overrun = feasibility_for_demand(demand, equip_table, deadline_days)

    options = []

    # A. 提高并行批次
    for s in steps:
        psh = num(s.get("per_sample_hours"), 0)
        bc = int(num(s.get("batch_capacity"), 0))
        if s["samples"] > 1 and not s["parallel"] and psh > 0 and bc > 1:
            old = s["samples"] * psh
            new = (ceil_div(s["samples"], bc) or 0) * psh
            saved_h = old - new
            eq = equip_table.get(s["equipment"]) or {}
            weekly = eq.get("weekly_hours", 0)
            saved_d = int(math.floor(saved_h / weekly * 7)) if weekly else 0
            options.append({
                "type": "提高并行批次", "target": s["id"],
                "detail": f"步骤 {s['id']}（{s['samples']} 样本，batch_capacity={bc}）"
                          f"由逐样串行 {old}h 改为批处理 {new}h",
                "saved_hours": saved_h, "saved_days_on_device": saved_d,
                "formula": f"{s['samples']}×{psh}h − ceil({s['samples']}/{bc})×{psh}h"
                           f" = {saved_h}h；÷ {weekly}h/周 × 7 ≈ {saved_d} 天",
                "cost": "批内均一性风险上升；需确认设备批量夹具/载台可用（confirmation_items）",
            })

    # B. 合并表征批次
    groups = {}
    for s in steps:
        if s.get("batch_group") and s.get("equipment") in equip_table:
            groups.setdefault((s["equipment"], s["batch_group"]), []).append(s)
    for (eid, grp), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        sh = num((equip_table[eid].get("booking") or {}).get("slot_hours")) or 1
        weekly = equip_table[eid]["weekly_hours"] or 1
        separate = sum(ceil_div(num(m["equip_hours"]), sh) or 0 for m in members)
        merged = ceil_div(sum(num(m["equip_hours"]) for m in members), sh) or 0
        saved_h = (separate - merged) * sh
        saved_d = int(math.floor(saved_h / weekly * 7))
        options.append({
            "type": "合并表征批次", "target": f"{eid}/{grp}",
            "detail": f"{len(members)} 个同设备步骤（{', '.join(m['id'] for m in members)}）"
                      f"合并为一次上机：{separate} slot → {merged} slot",
            "saved_hours": saved_h, "saved_days_on_device": saved_d,
            "formula": f"(单独 {separate} slot − 合并 {merged} slot) × {sh}h"
                       f" = {saved_h}h；÷ {weekly}h/周 × 7 ≈ {saved_d} 天",
            "cost": "样本需等同批齐样，表征时效性下降；跨条件同炉/同批需防交叉污染",
        })

    # C. 削减重复次数
    for s in steps:
        if s["replicates"] > 1 and num(s["equip_hours"]) > 0:
            per = num(s["equip_hours"]) / s["replicates"]
            saved_h = per  # 减 1 次重复
            eq = equip_table.get(s["equipment"]) or {}
            weekly = eq.get("weekly_hours", 0)
            saved_d = int(math.floor(saved_h / weekly * 7)) if weekly else 0
            options.append({
                "type": "削减重复次数", "target": s["id"],
                "detail": f"步骤 {s['id']} 重复 {s['replicates']} 次 → {s['replicates'] - 1} 次",
                "saved_hours": round(saved_h, 2), "saved_days_on_device": saved_d,
                "formula": f"{s['equip_hours']}h ÷ {s['replicates']} = {saved_h:.1f}h/次；"
                           f"÷ {weekly}h/周 × 7 ≈ {saved_d} 天",
                "cost": "统计功效下降：n=2 无法稳健估计方差，建议保留 n≥3 或改用分批重复",
            })

    # D. 改用可替代设备
    for s in steps:
        for alt in s.get("alt_equipment") or []:
            cur = equip_table.get(s["equipment"]) or {}
            aeq = equip_table.get(alt)
            if not aeq:
                options.append({
                    "type": "改用可替代设备", "target": s["id"],
                    "detail": f"步骤 {s['id']} 的替代设备 {alt} 不在合同设备表中，不可用",
                    "saved_hours": 0, "saved_days_on_device": 0, "formula": "—",
                    "cost": "替代设备无合同依据", "unavailable": True})
                continue
            weekly_cur = cur.get("weekly_hours", 0)
            saved_d = (int(math.floor(num(s["equip_hours"]) / weekly_cur * 7))
                       if weekly_cur else 0)
            price_d = num(aeq.get("price_per_hour")) - num(cur.get("price_per_hour"))
            options.append({
                "type": "改用可替代设备", "target": s["id"],
                "detail": f"步骤 {s['id']} 从 {s['equipment']} 移至 {alt}"
                          f"（{aeq.get('name')}，每周 {aeq['weekly_hours']}h）",
                "saved_hours": num(s["equip_hours"]),
                "saved_days_on_device": saved_d,
                "formula": f"瓶颈设备释放 {s['equip_hours']}h ÷ {weekly_cur}h/周 × 7"
                           f" ≈ {saved_d} 天（需替代设备当周有空闲 slot 才生效）",
                "cost": f"机时单价差 {price_d:+.0f} 元/h；结果口径可能与原设备有系统差异，"
                        f"需在方案中注明",
            })

    # 排序：节省天数降序
    options.sort(key=lambda o: -o.get("saved_days_on_device", 0))
    bname = bottleneck["equipment"] if bottleneck else "未知"
    report = {
        "status": "complete" if steps else "partial",
        "bottleneck_equipment": bname,
        "bottleneck_days": bottleneck["days_needed"] if bottleneck else 0,
        "deadline_days": deadline_days, "overrun_days": overrun,
        "options": options,
        "step_errors": norm_errors,
        "note": "saved_days_on_device 是该设备上释放的折算天数；"
                "只有作用于瓶颈设备且不在并行掩蔽下的选项才等额缩短总工期，"
                "采纳后必须用 schedule 重排验证。",
    }
    outdir = args.outdir or "."
    write_json(os.path.join(outdir, "repair.json"), report)
    md = [("# 合成示例输出，非正式测评结果\n" if args.synthetic else "")
          + "# repair 修复选项表",
          f"瓶颈设备 {bname}，瓶颈工期 {report['bottleneck_days']} 天，"
          f"deadline {deadline_days} 天，超期 {overrun} 天\n",
          "| # | 策略 | 对象 | 内容 | 节省(设备天) | 算式 | 代价 |",
          "|---|---|---|---|---|---|---|"]
    for i, o in enumerate(options, 1):
        md.append(f"| {i} | {o['type']} | {o['target']} | {o['detail']} "
                  f"| {o['saved_days_on_device']} | {o['formula']} | {o['cost']} |")
    md.append(f"\n> {report['note']}")
    write_text(os.path.join(outdir, "repair.md"), "\n".join(md) + "\n")
    print("\n".join(md), file=sys.stderr)
    print(f"[ok] 已写出 repair.json / repair.md 到 {outdir}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="schedule_forge.py",
        description="排期与预约可行性工程：throughput / schedule / repair 三子命令")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--case", required=True, help="case.json 路径")
        sp.add_argument("--outdir", default=".", help="输出目录")
        sp.add_argument("--synthetic", action="store_true",
                        help="输出文件头部标注『合成示例输出，非正式测评结果』")

    s1 = sub.add_parser("throughput", help="设备吞吐体检：机时需求 vs 可用机时")
    common(s1)
    s1.add_argument("--plan", help="可选：用户修订方案 plan.json（含 steps）")
    s1.set_defaults(func=cmd_throughput)

    s2 = sub.add_parser("schedule", help="按周/slot 排程，产出日程+甘特图+现金流")
    common(s2)
    s2.add_argument("--steps", required=True, help="步骤表 JSON（含 steps 列表）")
    s2.add_argument("--start", help=f"开工日期 YYYY-MM-DD（默认 {DEFAULT_START}）")
    s2.add_argument("--reagent-lead-weeks", type=int, default=1,
                    help="试剂采购前置周数（默认 1）")
    s2.set_defaults(func=cmd_schedule)

    s3 = sub.add_parser("repair", help="超期修复选项表（节省天数 + 代价）")
    common(s3)
    s3.add_argument("--steps", required=True, help="步骤表 JSON（含 steps 列表）")
    s3.set_defaults(func=cmd_repair)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001  —— 缺键不崩：输出 partial 报告并 exit 0
        outdir = getattr(args, "outdir", None) or "."
        err = {"status": "partial", "error": f"{type(exc).__name__}: {exc}",
               "hint": "输入缺少关键字段或格式不符；脚本已止损，请修正后重跑"}
        write_json(os.path.join(outdir, "error_report.json"), err)
        eprint(f"[partial] {err['error']}（详见 {outdir}/error_report.json）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
