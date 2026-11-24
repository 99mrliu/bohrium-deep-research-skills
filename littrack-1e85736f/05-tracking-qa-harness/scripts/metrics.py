#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metrics.py — 追踪运行质量指标（门禁 4/4 的量化部分）。

计算以下指标（完整定义见 references/metrics-definition.md）：
- window_coverage       窗口覆盖率（宽松口径：按 DOI 计）
- window_coverage_strict 窗口覆盖率（严格口径：仅计通过全部门禁的条目）
- dedup_rate            去重失败率（内部重复 + 与 previous_snapshot 重叠）
- alert_precision       提醒精确率（通过全部门禁的条目 / 全部条目）
- quarantine_rate       隔离率（任一门禁 fail 的条目 / 全部条目）
- locator_resolvability locator 可解析率（来自 evidence_spotcheck 报告）
- delivery_consistency  投递一致性（对照 delivery_log，可选）

指标不可计算时输出 null 并在 notes 说明（诚实 unknown，绝不编造）。

用法：
    python3 metrics.py --case case.json --result result.json \
        [--spotcheck spotcheck_report.json] [--freshness freshness_report.json] \
        [--out metrics_report.json]

退出码：始终 0（指标本身不做门禁判定，判定见 qa_report.py）。仅标准库。
"""
import argparse
import sys
from pathlib import Path

from qa_lib import (QaError, date_in_window, dump_json, iter_records,
                    load_json, load_snapshot_dois, norm_doi, record_dates,
                    record_doi)


def _result_items(result):
    items = result.get("new_items")
    return items if isinstance(items, list) else []


def _failed_item_indexes(report):
    """从子门禁报告提取 fail 检查涉及的 new_items 下标集合。"""
    bad = set()
    for c in (report or {}).get("checks", []):
        if c.get("status") == "fail":
            cid = c.get("id", "")
            if cid.startswith("item[") and "]." in cid:
                try:
                    bad.add(int(cid[5:cid.index("].")]))
                except ValueError:
                    pass
    return bad


def _locator_resolvability(spot_report, n_items):
    if not spot_report or n_items == 0:
        return None, "无 evidence_spotcheck 报告或条目数为 0，指标不可计算"
    ok = sum(1 for c in spot_report.get("checks", [])
             if c.get("id", "").endswith(".locator") and c.get("status") == "pass")
    total = sum(1 for c in spot_report.get("checks", [])
                if c.get("id", "").endswith(".locator"))
    if total == 0:
        return None, "spotcheck 报告中无 locator 检查记录"
    return ok / total, f"{ok}/{total} 条 locator 可解析"


def _expected_pool(case, case_dir, snapshot_dois, notes):
    """从 case.materials.sources 展开"本窗口应新增"的期望 DOI 集合。"""
    window = case.get("window") or {}
    start, end = window.get("start"), window.get("end")
    mats = case.get("materials") or {}
    sources = mats.get("sources") or []
    if not (start and end and sources):
        notes.append("case.json 缺少 window 或 materials.sources，期望集合不可计算")
        return None
    expected = set()
    for rel in sources:
        path = case_dir / rel
        try:
            doc = load_json(path)
        except QaError as exc:
            notes.append(f"源文件不可读: {exc}")
            continue
        for rec in iter_records(doc):
            doi = record_doi(rec)
            if not doi or doi in snapshot_dois:
                continue
            if any(date_in_window(d, start, end) for d in record_dates(rec)):
                expected.add(doi)
    return expected


def compute(case, result, case_dir, spot_report=None, fresh_report=None):
    notes = []
    items = _result_items(result)
    n = len(items)
    dois = [norm_doi(it.get("doi")) for it in items if isinstance(it, dict)]
    dois = [d for d in dois if d]

    # snapshot
    snap_dois = set()
    mats = case.get("materials") or {}
    snap_rel = mats.get("previous_snapshot")
    if snap_rel and (case_dir / snap_rel).is_file():
        snap_dois = load_snapshot_dois(case_dir / snap_rel)

    # 门禁 fail 条目（用于严格口径 / 精确率 / 隔离率）
    bad = _failed_item_indexes(spot_report) | _failed_item_indexes(fresh_report)
    sub_reports_given = spot_report is not None or fresh_report is not None

    metrics = {}

    # --- alert_precision / quarantine_rate ---
    if n == 0:
        metrics["alert_precision"] = None
        metrics["quarantine_rate"] = None
        notes.append("new_items 为空：精确率/隔离率不可计算")
    elif not sub_reports_given:
        metrics["alert_precision"] = None
        metrics["quarantine_rate"] = None
        notes.append("未提供 spotcheck/freshness 子报告：精确率/隔离率不可计算")
    else:
        metrics["alert_precision"] = (n - len(bad)) / n
        metrics["quarantine_rate"] = len(bad) / n
        notes.append(f"通过全部已运行门禁的条目 {n - len(bad)}/{n}")

    # --- locator_resolvability ---
    val, note = _locator_resolvability(spot_report, n)
    metrics["locator_resolvability"] = val
    notes.append(f"locator 可解析率: {note}")

    # --- dedup_rate ---
    if n == 0:
        metrics["dedup_rate"] = None
    else:
        internal_dup = len(dois) - len(set(dois))
        snapshot_overlap = sum(1 for d in set(dois) if d in snap_dois)
        metrics["dedup_rate"] = (internal_dup + snapshot_overlap) / n
        notes.append(f"去重失败: 内部重复 {internal_dup} 条，"
                     f"与 previous_snapshot 重叠 {snapshot_overlap} 条")

    # --- window_coverage ---
    expected = _expected_pool(case, case_dir, snap_dois, notes)
    if expected is None or not expected:
        metrics["window_coverage"] = None
        metrics["window_coverage_strict"] = None
        if expected is not None:
            notes.append("期望集合为空：窗口内源记录均在 snapshot 中")
    else:
        got = set(dois)
        covered = expected & got
        metrics["window_coverage"] = len(covered) / len(expected)
        if sub_reports_given:
            valid_dois = {dois[i] for i in range(n)
                          if i not in bad and i < len(dois)}
            metrics["window_coverage_strict"] = \
                len(expected & valid_dois) / len(expected)
        else:
            metrics["window_coverage_strict"] = None
        missing = sorted(expected - got)
        notes.append(f"期望新增 {len(expected)} 条，result 覆盖 {len(covered)} 条"
                     + (f"，缺失: {missing}" if missing else ""))

    # --- delivery_consistency（可选，对照投递记录） ---
    log_rel = mats.get("delivery_log")
    if log_rel and (case_dir / log_rel).is_file():
        log = load_json(case_dir / log_rel)
        delivered = {norm_doi(e.get("doi") if isinstance(e, dict) else e)
                     for e in (log.get("delivered") or [])}
        delivered.discard(None)
        if n and dois:
            hit = sum(1 for d in dois if d in delivered)
            metrics["delivery_consistency"] = hit / len(dois)
            notes.append(f"投递一致性: {hit}/{len(dois)} 条 result 条目在投递记录中")
        else:
            metrics["delivery_consistency"] = None
    else:
        metrics["delivery_consistency"] = None
        notes.append("无 delivery_log：投递一致性不可计算")

    return {
        "tool": "metrics",
        "status": "pass",
        "metrics": metrics,
        "counts": {
            "new_items": n,
            "expected_in_window": (len(expected) if expected else None),
            "quarantined_items": sorted(bad) if sub_reports_given else None,
        },
        "notes": notes,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="追踪运行质量指标（tracking-qa-harness）")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--result", required=True, help="待检 result.json 路径")
    ap.add_argument("--spotcheck", default=None, help="evidence_spotcheck 报告 JSON")
    ap.add_argument("--freshness", default=None, help="freshness_check 报告 JSON")
    ap.add_argument("--out", default=None, help="指标报告输出路径")
    args = ap.parse_args(argv)

    try:
        case = load_json(args.case)
        result = load_json(args.result)
        case_dir = Path(args.case).resolve().parent
        spot = load_json(args.spotcheck) if args.spotcheck else None
        fresh = load_json(args.freshness) if args.freshness else None
        report = compute(case, result, case_dir, spot, fresh)
    except QaError as exc:
        report = {"tool": "metrics", "status": "fail",
                  "metrics": {}, "counts": {}, "notes": [f"工具自身错误: {exc}"]}

    if args.out:
        dump_json(report, args.out)
    print("[metrics]")
    for k, v in report["metrics"].items():
        s = "null" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
        print(f"  {k} = {s}")
    for note in report["notes"]:
        print(f"  note: {note}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
