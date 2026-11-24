#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""record_run.py — 执行一轮增量导入并把证据追加到 increment_journal.jsonl。

特性：
- 完全离线，仅标准库；
- run_id 由 (窗口, 输入摘要) 确定性导出；同一轮在相同快照上重跑 -> 幂等空操作
  （不追加 journal、不产生新事件、不二次投递、snapshot 原样复制）；
- 每条判定都带 locator（文件 + JSON 路径 + 文件 sha256）与命中规则。

用法：
  python3 record_run.py --case case.json \
      --window-start 2025-06-08T00:00:00Z --window-end 2025-06-15T00:00:00Z \
      --source crossref=path/to/crossref.json --source arxiv=path/to/arxiv.json \
      --journal increment_journal.jsonl \
      --snapshot-in previous_snapshot.json --snapshot-out snapshot.json \
      --run-summary run_summary.json
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journal_lib as jl


def load_alert_channel(case_path):
    if case_path and os.path.exists(case_path):
        try:
            with open(case_path, "r", encoding="utf-8") as f:
                case = json.load(f)
            return ((case.get("alerts") or {}).get("channel")) or "log"
        except (json.JSONDecodeError, OSError):
            pass
    return "log"


def write_snapshot(path, snapshot_obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot_obj, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="记录一轮增量导入到 append-only journal")
    ap.add_argument("--case", default=None, help="case.json 路径（读取 alerts.channel；可缺省）")
    ap.add_argument("--window-start", required=True, help="窗口起点（UTC，含）")
    ap.add_argument("--window-end", required=True, help="窗口终点（UTC，不含）")
    ap.add_argument("--source", action="append", required=True,
                    help="name=path 形式，可多次（如 crossref=a.json）")
    ap.add_argument("--journal", required=True, help="increment_journal.jsonl 路径")
    ap.add_argument("--snapshot-in", default=None, help="上一轮快照（可缺省=空注册表）")
    ap.add_argument("--snapshot-out", required=True, help="本轮结束后写出的快照")
    ap.add_argument("--run-summary", required=True, help="本轮运行摘要 JSON 输出路径")
    ap.add_argument("--alerts-channel", default=None, help="覆盖告警渠道（默认读 case.json，否则 log）")
    args = ap.parse_args(argv)

    channel = args.alerts_channel or load_alert_channel(args.case)

    source_specs = []
    for s in args.source:
        if "=" not in s:
            ap.error("--source 必须为 name=path 形式: %r" % s)
        name, path = s.split("=", 1)
        source_specs.append(jl.load_source_spec(name, path))

    snapshot_in = None
    if args.snapshot_in and os.path.exists(args.snapshot_in):
        with open(args.snapshot_in, "r", encoding="utf-8") as f:
            snapshot_in = json.load(f)

    prior_runs = jl.read_journal(args.journal)
    result = jl.process_run(args.window_start, args.window_end, source_specs,
                            snapshot_in, prior_runs, channel)

    # ---- 幂等：run_id 已由 (窗口, 输入摘要) 确定性导出 ----
    existing_ids = {r.get("run_id") for r in prior_runs}
    if result["run_id"] in existing_ids:
        if args.snapshot_in and os.path.exists(args.snapshot_in):
            shutil.copyfile(args.snapshot_in, args.snapshot_out)
        else:
            write_snapshot(args.snapshot_out, {
                "schema": "increment-snapshot/1.0",
                "note": "idempotent no-op; no snapshot-in was provided",
                "as_of_utc": args.window_end,
                "sources": result["watermarks_before"],
                "seen_items": jl.registry_to_seen_items(
                    jl.registry_from(snapshot_in, prior_runs)),
            })
        summary = {
            "appended": False,
            "reason": "run-already-recorded-idempotent-noop",
            "run_id": result["run_id"],
            "window": result["window"],
            "counts": {"candidates": result["counts"]["candidates"], "in_window": 0,
                       "new": 0, "version_updates": 0, "duplicates": 0,
                       "skipped_out_of_window": 0, "skipped_no_date": 0},
            "events": [],
            "deliveries": [],
            "journal_path": args.journal,
            "journal_line": None,
            "journal_sha256": jl.sha256_file(args.journal) if os.path.exists(args.journal) else None,
            "snapshot_in": args.snapshot_in,
            "snapshot_out": args.snapshot_out,
            "sources": [{"name": s["name"], "path": s["path"], "sha256": s["file_sha256"]}
                        for s in source_specs],
        }
        with open(args.run_summary, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
        print(json.dumps({"appended": False, "run_id": result["run_id"],
                          "reason": summary["reason"]}, ensure_ascii=False))
        return 0

    record = jl.build_run_record(result, source_specs)
    jl.append_run(args.journal, record)

    snapshot_out = {
        "schema": "increment-snapshot/1.0",
        "as_of_utc": args.window_end,
        "sources": result["watermarks_after"],
        "seen_items": jl.registry_to_seen_items(result["registry"]),
    }
    write_snapshot(args.snapshot_out, snapshot_out)

    summary = {
        "appended": True,
        "run_id": result["run_id"],
        "window": result["window"],
        "counts": result["counts"],
        "events": result["events"],
        "deliveries": result["deliveries"],
        "watermarks_before": result["watermarks_before"],
        "watermarks_after": result["watermarks_after"],
        "journal_path": args.journal,
        "journal_line": len(prior_runs) + 1,
        "journal_sha256": jl.sha256_file(args.journal),
        "snapshot_in": args.snapshot_in,
        "snapshot_out": args.snapshot_out,
        "sources": [{"name": s["name"], "path": s["path"], "sha256": s["file_sha256"]}
                    for s in source_specs],
    }
    with open(args.run_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"appended": True, "run_id": result["run_id"],
                      "counts": result["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
