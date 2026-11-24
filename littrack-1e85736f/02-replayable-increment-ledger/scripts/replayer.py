#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replayer.py — 从 journal + previous_snapshot 重放任意一轮，逐字节 diff。

重放方法：取目标 run 之前的全部 journal 记录 + 该轮的 previous snapshot 重建
注册表与水位，用与 record_run 完全相同的纯函数 process_run 重算 events /
deliveries / counts / watermarks_after，然后与 journal 中记录的字段做
canonical JSON 的 sha256 逐字节比较，输出 replay_diff.json。

用法：
  python3 replayer.py --journal increment_journal.jsonl --run-id run-xxxx \
      --snapshot snapshot_before_that_run.json \
      --source crossref=a.json --source arxiv=b.json \
      --case case.json --out replay_diff.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journal_lib as jl
from record_run import load_alert_channel


def diff_events(recorded, replayed):
    """逐事件、逐字段列出差异（仅当整体哈希不一致时调用）。"""
    mismatches = []
    n = max(len(recorded), len(replayed))
    for i in range(n):
        if i >= len(recorded):
            mismatches.append({"event_index": i, "field": None,
                               "recorded": None, "replayed": replayed[i],
                               "reason": "replayed has extra event"})
            continue
        if i >= len(replayed):
            mismatches.append({"event_index": i, "field": None,
                               "recorded": recorded[i], "replayed": None,
                               "reason": "recorded has extra event"})
            continue
        r, p = recorded[i], replayed[i]
        if jl.canonical_json(r) == jl.canonical_json(p):
            continue
        for field in sorted(set(r) | set(p)):
            if jl.canonical_json(r.get(field)) != jl.canonical_json(p.get(field)):
                mismatches.append({
                    "event_index": i,
                    "field": field,
                    "recorded": r.get(field),
                    "replayed": p.get(field),
                    "reason": "field value differs",
                })
    return mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(description="重放一轮增量并与 journal 逐字节 diff")
    ap.add_argument("--journal", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--snapshot", default=None,
                    help="该轮之前的 snapshot（与 record_run 的 --snapshot-in 相同）")
    ap.add_argument("--source", action="append", required=True, help="name=path，可多次")
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", required=True, help="replay_diff.json 输出路径")
    args = ap.parse_args(argv)

    runs = jl.read_journal(args.journal)
    target_idx = None
    for i, r in enumerate(runs):
        if r.get("run_id") == args.run_id:
            target_idx = i
            break
    if target_idx is None:
        report = {
            "run_id": args.run_id,
            "status": "inconsistent",
            "byte_equal": False,
            "mismatches": [{"event_index": None, "field": "run_id",
                            "recorded": None, "replayed": args.run_id,
                            "reason": "run_id not found in journal"}],
            "checks": [],
            "explanation": "目标 run_id 不在 journal 中，无法回放。",
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
        print(json.dumps({"run_id": args.run_id, "status": "inconsistent",
                          "reason": "run not found"}, ensure_ascii=False))
        return 1

    target = runs[target_idx]
    prior_runs = runs[:target_idx]
    channel = target.get("alert_channel") or load_alert_channel(args.case)

    snapshot = None
    if args.snapshot and os.path.exists(args.snapshot):
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

    source_specs = []
    for s in args.source:
        name, path = s.split("=", 1)
        source_specs.append(jl.load_source_spec(name, path))

    replayed = jl.process_run(target["window"]["start_utc"], target["window"]["end_utc"],
                              source_specs, snapshot, prior_runs, channel)

    checks = []

    def add_check(field, recorded_obj, replayed_obj):
        r_hash = jl.sha256_text(jl.canonical_json(recorded_obj))
        p_hash = jl.sha256_text(jl.canonical_json(replayed_obj))
        checks.append({"field": field, "recorded_sha256": r_hash,
                       "replayed_sha256": p_hash, "equal": r_hash == p_hash})
        return r_hash == p_hash

    eq_id = add_check("run_id", target.get("run_id"), replayed["run_id"])
    eq_digest = add_check("input_digest", target.get("input_digest"), replayed["input_digest"])
    eq_counts = add_check("counts", target.get("counts"), replayed["counts"])
    eq_events = add_check("events", target.get("events"), replayed["events"])
    eq_deliv = add_check("deliveries", target.get("deliveries"), replayed["deliveries"])
    eq_wm = add_check("watermarks_after", target.get("watermarks_after"),
                      replayed["watermarks_after"])

    mismatches = []
    if not eq_events:
        mismatches.extend(diff_events(target.get("events") or [], replayed["events"]))
    if not eq_deliv:
        mismatches.extend(diff_events(target.get("deliveries") or [], replayed["deliveries"]))
    for field, eq in (("run_id", eq_id), ("input_digest", eq_digest),
                      ("counts", eq_counts), ("watermarks_after", eq_wm)):
        if not eq:
            mismatches.append({
                "event_index": None, "field": field,
                "recorded": target.get(field),
                "replayed": replayed.get(field if field != "run_id" else "run_id"),
                "reason": "canonical bytes differ",
            })

    byte_equal = all(c["equal"] for c in checks)
    report = {
        "run_id": args.run_id,
        "status": "consistent" if byte_equal else "inconsistent",
        "byte_equal": byte_equal,
        "journal_path": args.journal,
        "journal_line": target_idx + 1,
        "snapshot_used": args.snapshot,
        "checks": checks,
        "mismatches": mismatches,
        "explanation": (
            "重放结果与 journal 记录逐字节一致：状态重建与判定规则可完全复现。"
            if byte_equal else
            "重放结果与 journal 记录存在差异，详见 mismatches。"
        ),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"run_id": args.run_id, "status": report["status"],
                      "byte_equal": byte_equal}, ensure_ascii=False))
    return 0 if byte_equal else 1


if __name__ == "__main__":
    sys.exit(main())
