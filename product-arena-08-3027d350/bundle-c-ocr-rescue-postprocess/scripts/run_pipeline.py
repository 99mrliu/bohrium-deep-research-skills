#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py -- convenience orchestrator for the three pipeline stages.

Runs confusion_scan.py -> postcorrect.py -> ocr_qc.py with shared arguments
and stops on the first non-zero exit code, propagating it. Stdlib only.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description="Run the full ocr-rescue-postprocess pipeline.")
    ap.add_argument("--input", required=True, help="raw OCR text (pages separated by form feeds)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--case", default=None, help="case.json (case_id + output_contract)")
    ap.add_argument("--threshold", default="high", choices=["high", "medium"])
    ap.add_argument("--aggressive", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    steps = [
        [sys.executable, str(HERE / "confusion_scan.py"),
         "--input", args.input, "--out", str(out)],
        [sys.executable, str(HERE / "postcorrect.py"),
         "--input", args.input,
         "--candidates", str(out / "candidates.jsonl"),
         "--out", str(out),
         "--threshold", args.threshold]
        + (["--aggressive"] if args.aggressive else []),
        [sys.executable, str(HERE / "ocr_qc.py"),
         "--raw", args.input,
         "--corrected", str(out / "corrected.txt"),
         "--candidates", str(out / "candidates.jsonl"),
         "--change-log", str(out / "change_log.jsonl"),
         "--review", str(out / "review_list.json"),
         "--out", str(out)]
        + (["--case", args.case] if args.case else []),
    ]
    for i, cmd in enumerate(steps, start=1):
        print("== step %d: %s" % (i, Path(cmd[1]).name), flush=True)
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            sys.stderr.write("pipeline aborted at step %d (exit %d)\n" % (i, proc.returncode))
            sys.exit(proc.returncode)
    print("pipeline finished; outputs in %s" % out)
    sys.exit(0)


if __name__ == "__main__":
    main()
