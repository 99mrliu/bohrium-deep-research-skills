#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""freshness_check.py — 窗口新鲜度与防旧文重报（门禁 3/4）。

对待检 result.json 中 new_items 的每一条：
1. 窗口归属：条目 published_date 必须落在 case.json window.start ~ window.end
   （闭区间）内；窗口外条目除非带 "backfill": true 标记（降级为 warn）否则 fail；
2. 防旧文重报：条目 DOI 不得出现在 previous_snapshot 中（出现即 fail，
   这是"旧文被当作新增重复提醒"的典型错误）；
3. result.window（若有）应与 case.window 一致（不一致 = warn）。

previous_snapshot 定位顺序：
  a) --snapshot 显式指定；
  b) case.json 的 materials.previous_snapshot（相对 case.json 所在目录）；
  c) case.json 同级目录的 previous_snapshot.json 或 materials/previous_snapshot.json。

用法：
    python3 freshness_check.py --case case.json --result result.json \
        [--snapshot previous_snapshot.json] [--out report.json]

退出码：0=pass，2=warn，1=fail。仅标准库；永不访问网络。
"""
import argparse
import sys
from pathlib import Path

from qa_lib import (QaError, check, date_in_window, dump_json, load_json,
                    load_snapshot_dois, make_report, norm_doi,
                    parse_iso_date)


def _find_snapshot(args, case):
    if args.snapshot:
        return Path(args.snapshot)
    case_dir = Path(args.case).resolve().parent
    rel = None
    mats = case.get("materials") if isinstance(case, dict) else None
    if isinstance(mats, dict):
        rel = mats.get("previous_snapshot")
    candidates = []
    if rel:
        candidates.append(case_dir / rel)
    candidates.append(case_dir / "previous_snapshot.json")
    candidates.append(case_dir / "materials" / "previous_snapshot.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def freshness(case, result, snapshot_path):
    checks = []
    window = case.get("window") or {}
    start, end = window.get("start"), window.get("end")
    if not start or not end:
        checks.append(check(
            "window.declared", "fail",
            "case.json 缺少 window.start / window.end，无法执行新鲜度核验"))
        return checks
    checks.append(check(
        "window.declared", "pass", f"追踪窗口: {start} ~ {end}（闭区间）"))

    # result.window 一致性
    rw = result.get("window")
    if isinstance(rw, dict):
        if rw.get("start") != start or rw.get("end") != end:
            checks.append(check(
                "window.consistent", "warn",
                f"result.window={rw.get('start')}~{rw.get('end')} 与 "
                f"case.window={start}~{end} 不一致"))
        else:
            checks.append(check(
                "window.consistent", "pass", "result.window 与 case.window 一致"))

    # snapshot 载入
    known = set()
    if snapshot_path and Path(snapshot_path).is_file():
        known = load_snapshot_dois(snapshot_path)
        checks.append(check(
            "snapshot.loaded", "pass",
            f"previous_snapshot 已载入: {snapshot_path}（{len(known)} 个已知 DOI）"))
    else:
        checks.append(check(
            "snapshot.loaded", "warn",
            "未找到 previous_snapshot：跳过旧文重报检查（结果可信度下降）"))

    items = result.get("new_items")
    if not isinstance(items, list) or not items:
        checks.append(check(
            "new_items.present", "warn",
            "new_items 缺失或为空：无条目可核验新鲜度"))
        return checks

    seen_dois = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            checks.append(check(
                f"item[{idx}].shape", "fail", f"new_items[{idx}] 不是对象"))
            continue
        doi = norm_doi(item.get("doi"))
        label = f"new_items[{idx}]" + (f" ({doi})" if doi else "")
        backfill = bool(item.get("backfill"))

        # --- 1. 窗口归属 ---
        d = parse_iso_date(item.get("published_date") or item.get("date"))
        if d is None:
            checks.append(check(
                f"item[{idx}].window", "fail",
                f"{label} 缺少合法 published_date，无法核验窗口归属"))
        else:
            in_win = date_in_window(d, start, end)
            if in_win:
                checks.append(check(
                    f"item[{idx}].window", "pass",
                    f"{label} 日期 {d} 在窗口 {start}~{end} 内"))
            elif backfill:
                checks.append(check(
                    f"item[{idx}].window", "warn",
                    f"{label} 日期 {d} 在窗口外，但带 backfill 标记"
                    f"（补录条目，需在 change_records 中说明）"))
            else:
                checks.append(check(
                    f"item[{idx}].window", "fail",
                    f"{label} 日期 {d} 落在窗口 {start}~{end} 之外，"
                    f"且无 backfill 标记（不属于本窗口新增）"))

        # --- 2. 防旧文重报 ---
        if doi:
            if doi in known:
                checks.append(check(
                    f"item[{idx}].dedup", "fail",
                    f"{label} 已存在于 previous_snapshot（旧文重报，应去重）"))
            elif snapshot_path:
                checks.append(check(
                    f"item[{idx}].dedup", "pass",
                    f"{label} 不在 previous_snapshot 中"))
            # --- 3. result 内部重复 ---
            if doi in seen_dois:
                checks.append(check(
                    f"item[{idx}].selfdup", "fail",
                    f"{label} 与 new_items[{seen_dois[doi]}] DOI 重复（结果内部重复）"))
            else:
                seen_dois[doi] = idx
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description="窗口新鲜度与防旧文重报（tracking-qa-harness 门禁 3/4）")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--result", required=True, help="待检 result.json 路径")
    ap.add_argument("--snapshot", default=None, help="previous_snapshot.json 路径（可自动定位）")
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径")
    args = ap.parse_args(argv)

    try:
        case = load_json(args.case)
        result = load_json(args.result)
        snap = _find_snapshot(args, case)
        checks = freshness(case, result, snap)
    except QaError as exc:
        checks = [check("tool.error", "fail", f"工具自身错误: {exc}")]

    report = make_report("freshness_check", checks)
    if args.out:
        dump_json(report, args.out)
    print(f"[freshness_check] status={report['status']} "
          f"errors={report['summary']['errors']} warnings={report['summary']['warnings']}")
    for c in checks:
        if c["status"] != "pass":
            print(f"  - [{c['status']}] {c['id']}: {c['message']}")
    return {"pass": 0, "warn": 2, "fail": 1}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
