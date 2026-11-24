#!/usr/bin/env python3
"""checkpoint.py -- staged checkpoints so partial work is never lost.

Appends one JSONL record (UTC ISO timestamp, stage, note) to
WORK/checkpoints.jsonl and copies every --snapshot file into
WORK/snapshots/<stage>/ preserving its basename. Idempotent: creates
directories as needed and may be called any number of times per stage;
each call is one appended record, never a rewrite of history.

Usage:
  checkpoint.py --work WORKDIR --stage NAME [--note TEXT] [--snapshot PATH ...]

Exit codes: 0 ok, 2 usage error (e.g. a snapshot path does not exist).
Pure Python 3 standard library; no hardcoded harness paths.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record a staged checkpoint.")
    ap.add_argument("--work", required=True, help="working directory (created if missing)")
    ap.add_argument("--stage", required=True, help="stage name, e.g. read, scaffold, draft, audit")
    ap.add_argument("--note", default="", help="free-text note for the checkpoint record")
    ap.add_argument("--snapshot", action="append", default=[], metavar="PATH",
                    help="file to snapshot into snapshots/<stage>/ (repeatable)")
    args = ap.parse_args(argv)

    for p in args.snapshot:
        if not os.path.isfile(p):
            print("ERROR: snapshot file not found: %s" % p, file=sys.stderr)
            return 2

    os.makedirs(args.work, exist_ok=True)
    snap_dir = os.path.join(args.work, "snapshots", args.stage)
    os.makedirs(snap_dir, exist_ok=True)

    copied = []
    for p in args.snapshot:
        dest = os.path.join(snap_dir, os.path.basename(p))
        shutil.copy2(p, dest)
        copied.append(dest)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "note": args.note,
        "snapshots": copied,
    }
    log_path = os.path.join(args.work, "checkpoints.jsonl")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("checkpoint: stage=%s snapshots=%d -> %s" % (args.stage, len(copied), log_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
