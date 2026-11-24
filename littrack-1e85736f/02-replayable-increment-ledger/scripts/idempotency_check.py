#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""idempotency_check.py — 证明同一轮在相同快照上重跑产生零新事件、零二次投递。

方法：把 journal 与 snapshot-in 复制到临时目录，用与正式运行完全相同的参数
再跑一次 record_run.py，然后验证：
  1. record_run 报告 appended=False（run-already-recorded-idempotent-noop）；
  2. 临时 journal 与原 journal 逐字节相同（零追加）；
  3. 运行摘要中 new/version_update 事件数 = 0 且 deliveries 数 = 0。

用法：
  python3 idempotency_check.py --case case.json \
      --window-start ... --window-end ... \
      --source crossref=a.json --source arxiv=b.json \
      --journal increment_journal.jsonl --snapshot-in snapshot_before.json \
      --out idempotency_report.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journal_lib as jl


def main(argv=None):
    ap = argparse.ArgumentParser(description="增量轮次幂等性校验")
    ap.add_argument("--case", default=None)
    ap.add_argument("--window-start", required=True)
    ap.add_argument("--window-end", required=True)
    ap.add_argument("--source", action="append", required=True)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--snapshot-in", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    record_run = os.path.join(script_dir, "record_run.py")

    journal_bytes_before = b""
    if os.path.exists(args.journal):
        with open(args.journal, "rb") as f:
            journal_bytes_before = f.read()

    with tempfile.TemporaryDirectory(prefix="idempotency-") as td:
        journal_copy = os.path.join(td, "journal.jsonl")
        with open(journal_copy, "wb") as f:
            f.write(journal_bytes_before)
        snapshot_copy = None
        if args.snapshot_in and os.path.exists(args.snapshot_in):
            snapshot_copy = os.path.join(td, "snapshot_in.json")
            shutil.copyfile(args.snapshot_in, snapshot_copy)
        snapshot_out = os.path.join(td, "snapshot_out.json")
        summary_path = os.path.join(td, "rerun_summary.json")

        cmd = [sys.executable, record_run,
               "--window-start", args.window_start,
               "--window-end", args.window_end,
               "--journal", journal_copy,
               "--snapshot-out", snapshot_out,
               "--run-summary", summary_path]
        if args.case:
            cmd += ["--case", args.case]
        if snapshot_copy:
            cmd += ["--snapshot-in", snapshot_copy]
        for s in args.source:
            cmd += ["--source", s]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        with open(journal_copy, "rb") as f:
            journal_bytes_after = f.read()

        summary = {}
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)

    journal_identical = journal_bytes_before == journal_bytes_after
    counts = summary.get("counts") or {}
    new_events = (counts.get("new") or 0) + (counts.get("version_updates") or 0)
    deliveries = len(summary.get("deliveries") or [])
    appended_flag = summary.get("appended")

    ok = (proc.returncode == 0 and appended_flag is False
          and journal_identical and new_events == 0 and deliveries == 0)

    report = {
        "status": "pass" if ok else "fail",
        "window": {"start_utc": args.window_start, "end_utc": args.window_end},
        "journal_path": args.journal,
        "journal_sha256_before": jl.sha256_text(journal_bytes_before.decode("utf-8", "replace"))
        if journal_bytes_before else None,
        "journal_byte_identical_after_rerun": journal_identical,
        "rerun_appended": appended_flag,
        "rerun_reason": summary.get("reason"),
        "rerun_run_id": summary.get("run_id"),
        "new_events_after_rerun": new_events,
        "deliveries_after_rerun": deliveries,
        "record_run_returncode": proc.returncode,
        "record_run_stdout": (proc.stdout or "").strip(),
        "record_run_stderr": (proc.stderr or "").strip()[-2000:],
        "explanation": (
            "同一轮在相同快照上重跑：零追加、零新事件、零二次投递，幂等性成立。"
            if ok else
            "幂等性校验未通过，详见各字段。"
        ),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"status": report["status"],
                      "journal_byte_identical": journal_identical,
                      "new_events": new_events, "deliveries": deliveries},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
