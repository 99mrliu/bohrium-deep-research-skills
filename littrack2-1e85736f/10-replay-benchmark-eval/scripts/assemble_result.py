#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 汇总产出最终 result.json。

规则：
  - result.json 必含 case.json output_contract.required_fields 中的全部字段；
  - 任一上游产物缺失/不可读时，对应字段补 null，status 置 "partial"，
    并在 notes 中说明缺什么；绝不编造真值、指标或文献。
  - benchmark_constructible 只依据 truth.json 是否由快照对生成来判定。

仅使用 Python3 标准库，完全离线。
"""
import argparse
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def try_load(path):
    if path and os.path.isfile(path):
        try:
            return load_json(path)
        except (OSError, ValueError):
            return None
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总最终 result.json")
    ap.add_argument("--case", required=True, help="case.json")
    ap.add_argument("--truth", default=None)
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--regression", default=None)
    ap.add_argument("--report", default=None, help="eval_report.md 路径（仅存引用，不解析）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = load_json(args.case)
    contract = case.get("output_contract") or {}
    required = contract.get("required_fields") or []

    truth = try_load(args.truth)
    metrics = try_load(args.metrics)
    regression = try_load(args.regression)
    report_ok = bool(args.report and os.path.isfile(args.report))

    missing = []
    if truth is None:
        missing.append("truth.json 缺失或不可读（无法构造/加载增量真值）")
    if metrics is None:
        missing.append("metrics.json 缺失或不可读（无候选清单或计算失败）")
    if not report_ok:
        missing.append("eval_report.md 未生成")

    benchmark_constructible = bool(
        truth and str(truth.get("source_basis", "")).startswith("snapshot_pair"))

    result = {
        "case_id": case.get("case_id"),
        "status": "ok",
        "synthetic": case.get("synthetic"),
        "benchmark_constructible": benchmark_constructible,
        "snapshot_pair": {
            "prev": (truth or {}).get("snapshots", {}).get("prev"),
            "now": (truth or {}).get("snapshots", {}).get("now"),
            "added_count": (truth or {}).get("counts", {}).get("added_total"),
        } if truth else None,
        "truth_summary": (truth or {}).get("counts") if truth else None,
        "metrics_summary": {
            "counts": metrics.get("counts"),
            "metrics": metrics.get("metrics"),
        } if metrics else None,
        "regression_summary": {
            "status": regression.get("status"),
            "baseline_run_id": regression.get("baseline_run_id"),
            "verdict": regression.get("verdict"),
            "flags": [f["type"] for f in regression.get("flags", [])],
        } if regression else None,
        "artifacts": {
            "truth_json": args.truth if truth else None,
            "metrics_json": args.metrics if metrics else None,
            "regression_json": args.regression if regression else None,
            "eval_report_md": args.report if report_ok else None,
        },
        "limitations": [
            "真值由快照对机械构造，非人工标注；单快照场景无法构造真值。",
            "backfill 判定依赖 published 字段准确性；日期缺失者单列 unclassifiable。",
            "本结果仅为测量输出，不构成对任何追踪管道检索结果的背书。",
        ],
        "notes": [],
    }

    if case.get("synthetic"):
        result["notes"].append("合成数据：" + (case.get("synthetic_note") or "本案例为合成示例。"))
    if missing:
        result["status"] = "partial"
        result["notes"].append("降级 partial，原因：" + "；".join(missing))
    if not benchmark_constructible and truth is not None:
        result["status"] = "partial"
        result["notes"].append("truth.json 存在但非快照对构造，benchmark_constructible=false。")

    # 契约兜底：required_fields 中缺失的键补 null
    for k in required:
        result.setdefault(k, None)
    unknown = [k for k in required if result.get(k) is None]
    if unknown and result["status"] == "ok":
        result["status"] = "partial"
        result["notes"].append("契约字段为 null：%s" % unknown)

    dump_json(args.out, result)
    print("result: status=%s benchmark_constructible=%s missing=%d"
          % (result["status"], result["benchmark_constructible"], len(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
