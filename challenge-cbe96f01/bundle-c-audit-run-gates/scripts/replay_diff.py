#!/usr/bin/env python3
"""replay_diff.py -- audit-run-gates stage 4 determinism replay (gate G9).

Compares two artifact directories (original run vs re-run) file by file
via SHA-256. Deterministic products (pages.jsonl, anchors.json and any
file passed via --require-identical) MUST be byte-identical; other files
are reported as informational diffs.

Usage:
  replay_diff.py --run DIR_A --rerun DIR_B --out report.json \
      [--require-identical pages.jsonl anchors.json]
Exit 1 if any required file differs or is missing on either side.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def snapshot(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--rerun", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--require-identical", nargs="*",
                    default=["pages.jsonl", "anchors.json"])
    args = ap.parse_args()

    a = snapshot(Path(args.run))
    b = snapshot(Path(args.rerun))
    report = {"identical": [], "differ": [], "missing": [],
              "required_failures": [], "passed": True}
    for rel in sorted(set(a) | set(b)):
        if rel not in a or rel not in b:
            report["missing"].append(rel)
        elif a[rel] == b[rel]:
            report["identical"].append(rel)
        else:
            report["differ"].append(rel)
    for rel in args.require_identical:
        if rel in report["differ"] or rel in report["missing"]:
            report["required_failures"].append(rel)
    report["passed"] = not report["required_failures"]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"identical": len(report["identical"]),
                      "differ": len(report["differ"]),
                      "missing": len(report["missing"]),
                      "passed": report["passed"]}, ensure_ascii=False))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
