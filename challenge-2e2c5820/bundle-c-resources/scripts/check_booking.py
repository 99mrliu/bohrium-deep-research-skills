#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_booking.py — 预订窗口重叠 + 采购货期核验（stdlib datetime 区间算术）。

用法: python3 check_booking.py <requirements.json> <case.json> <out.json>

两部分:
  1. 区间重叠: requirements.booking_needs 的占用窗口（ISO 日期，或
     start_day/end_day 相对天数 + 案例 start_date 基准）与案例预订日历中同资源
     的既有预订做区间算术，输出 (资源, 窗口A, 窗口B, overlap_days, overlap_hours)。
     半开区间 [start, end): overlap_days = (min(endA,endB) - max(startA,startB)).days，
     > 0 即冲突，overlap_hours = overlap_days * 24。
  2. 货期核验: materials 中命中采购合同的条目，计算
     到货日 arrival = order_by + lead_time_days，
     slack_days = (needed_by - arrival).days，
     slack_days >= 0 → 赶得上; < 0 → 赶不上。任一日期缺失 → 无法核验并记 notes。

退出码: 0 正常; 2 用法错误; 3 输入不可读。
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_entities import load_alias_index, normalize_name, clean_name
from match_resources import get_contracts, row_name, pick_contract


def parse_day(s):
    return date.fromisoformat(str(s).strip().split("T")[0])


def get_calendar(case):
    if isinstance(case, dict):
        for k, v in case.items():
            kl = str(k).casefold()
            if isinstance(v, list) and any(
                    p in kl for p in ("booking", "calendar", "schedule", "预订", "预约", "排期")):
                return v, True
    return [], False


def need_window(need, case):
    """返回 (start, end, err)。优先绝对 ISO 日期，其次相对天数 + 基准日。"""
    if need.get("start") and need.get("end"):
        try:
            return parse_day(need["start"]), parse_day(need["end"]), None
        except ValueError as e:
            return None, None, "日期解析失败: {}".format(e)
    if need.get("start_day") is not None and need.get("end_day") is not None:
        base = case.get("start_date") or case.get("plan_start_date") \
            if isinstance(case, dict) else None
        if base:
            try:
                b = parse_day(base)
                return b + timedelta(days=int(need["start_day"])), \
                    b + timedelta(days=int(need["end_day"])), None
            except (ValueError, TypeError) as e:
                return None, None, "基准日期解析失败: {}".format(e)
        return None, None, "仅有相对天数且案例未提供基准日期，无法换算绝对窗口"
    return None, None, "缺少 start/end（或 start_day/end_day）"


def check_overlaps(req, case, idx, notes):
    calendar, cal_present = get_calendar(case)
    if not cal_present:
        notes.append("案例未提供预订日历，排期重叠无法核验")
    windows = []
    for need in req.get("booking_needs") or []:
        entry = {
            "need_id": need.get("id"), "resource": need.get("resource"),
            "gating": bool(need.get("gating")), "locator": need.get("locator"),
        }
        if not cal_present:
            entry["verdict"] = "无法核验"
            entry["reason"] = "案例未提供预订日历"
            windows.append(entry)
            continue
        s, e, err = need_window(need, case)
        if err:
            entry["verdict"] = "无法核验"
            entry["reason"] = err
            windows.append(entry)
            continue
        nkey = clean_name(normalize_name(str(need.get("resource", "")), idx)[0])
        conflicts = []
        for bk in calendar:
            if not isinstance(bk, dict):
                continue
            bkey = clean_name(normalize_name(str(bk.get("resource", "")), idx)[0])
            if bkey != nkey:
                continue
            try:
                bs, be = parse_day(bk["start"]), parse_day(bk["end"])
            except (KeyError, ValueError):
                notes.append("预订日历行缺少可解析的 start/end: {}".format(bk))
                continue
            ov_days = (min(e, be) - max(s, bs)).days
            if ov_days > 0:
                conflicts.append({
                    "existing_booking": bk,
                    "overlap_days": ov_days,
                    "overlap_hours": ov_days * 24,
                })
        entry["plan_window"] = [s.isoformat(), e.isoformat()]
        entry["conflicts"] = conflicts
        entry["verdict"] = "冲突" if conflicts else "无冲突"
        windows.append(entry)
    return windows


def check_lead_times(req, case, idx, notes):
    _, purchase = get_contracts(case)
    results = []
    for m in req.get("materials") or []:
        if not isinstance(m, dict):
            continue
        nkey = clean_name(normalize_name(str(m.get("name", "")), idx)[0])
        pc = [c for c in purchase
              if clean_name(normalize_name(row_name(c, ("item", "name")), idx)[0]) == nkey]
        if not pc:
            continue  # 非采购项（已具备/可外协/不具备）不做货期核验
        row = pick_contract(pc)
        entry = {
            "material": m.get("name"), "gating": bool(m.get("gating")),
            "needed_by": m.get("needed_by"), "contract": row,
            "locator": m.get("locator"),
        }
        order_by = row.get("order_by") or m.get("order_by")
        lead = row.get("lead_time_days")
        needed = m.get("needed_by")
        if order_by and lead is not None and needed:
            try:
                arrival = parse_day(order_by) + timedelta(days=int(lead))
                slack = (parse_day(needed) - arrival).days
                entry.update({
                    "order_by": str(order_by), "lead_time_days": int(lead),
                    "arrival": arrival.isoformat(), "needed_by": str(needed),
                    "slack_days": slack,
                    "verdict": "赶得上" if slack >= 0 else "赶不上",
                })
            except (ValueError, TypeError) as e:
                entry["verdict"] = "无法核验"
                entry["reason"] = "日期/货期解析失败: {}".format(e)
        else:
            entry["verdict"] = "无法核验"
            entry["reason"] = "缺少 order_by / lead_time_days / needed_by，无法核验货期"
        results.append(entry)
    return results


def main(argv):
    if len(argv) != 4:
        print("用法: python3 check_booking.py <requirements.json> <case.json> <out.json>",
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
    notes = []
    windows = check_overlaps(req, case, idx, notes)
    lead_times = check_lead_times(req, case, idx, notes)
    n_overlap = sum(len(w.get("conflicts") or []) for w in windows)
    n_late = sum(1 for lt in lead_times if lt.get("verdict") == "赶不上")
    out = {
        "case_id": req.get("case_id") or (case.get("case_id") if isinstance(case, dict) else None),
        "plan_version": req.get("plan_version"),
        "booking_windows": windows,
        "lead_times": lead_times,
        "conflict_count": n_overlap,
        "late_count": n_late,
        "notes": notes,
    }
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("check_booking [{}]: 预订冲突 {} 处, 货期赶不上 {} 项".format(
        req.get("plan_version"), n_overlap, n_late))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
