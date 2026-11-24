#!/usr/bin/env python3
"""change_record.py -- sentence-level change records between two versions.

Revision tasks must preserve a modification trail: what changed, where, and
why. This script diffs an old and a new manuscript at sentence level
(difflib, stdlib) and emits records shaped for a `version_and_boundary.changes`
array. The `rationale` field is left for the writer — a record without a
reason is flagged as needing completion, because an unexplained edit is not a
verifiable edit.

Usage:
  python3 change_record.py --old v1.md --new v2.md --out changes.json \
      [--rationale "fixed attribution of synth03; trimmed related work to budget"]

Exit codes: 0 ok (records written; may still flag missing rationales),
2 usage/IO error.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path


def sentences(text):
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    t = re.sub(r"\s+", " ", " ".join(lines))
    parts = re.split(r"(?<=[.!?])\s+(?=[^0-9\s]|$)", t)
    return [p.strip() for p in parts if len(p.strip()) > 10]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rationale", help="reason applied to every change record")
    args = ap.parse_args()
    try:
        old = sentences(Path(args.old).read_text(encoding="utf-8"))
        new = sentences(Path(args.new).read_text(encoding="utf-8"))
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    changes = []
    n = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        n += 1
        changes.append({
            "id": "chg%d" % n,
            "type": {"replace": "modified", "delete": "deleted", "insert": "added"}[tag],
            "old": " ".join(old[i1:i2])[:500] if i1 < i2 else "",
            "new": " ".join(new[j1:j2])[:500] if j1 < j2 else "",
            "location": "sentence block %d->%d" % (i1 + 1, j1 + 1),
            "rationale": args.rationale or "<TODO: state the reason for this edit>",
        })
    report = {
        "changes": changes,
        "summary": {
            "total": len(changes),
            "added": sum(1 for c in changes if c["type"] == "added"),
            "modified": sum(1 for c in changes if c["type"] == "modified"),
            "deleted": sum(1 for c in changes if c["type"] == "deleted"),
            "missing_rationale": sum(1 for c in changes
                                     if c["rationale"].startswith("<TODO")),
        },
        "note": "sentence-level diff; verify each record keeps scientific intent unchanged",
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    s = report["summary"]
    print("change record: %d changes (+%d ~%d -%d), %d missing rationale -> %s"
          % (s["total"], s["added"], s["modified"], s["deleted"],
             s["missing_rationale"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
