#!/usr/bin/env python3
"""make_result.py - create / update /app/output/result.json honestly.

- Copies case_id verbatim from case.json.
- Tolerates output_contract as dict, list of strings, or list of dicts
  (keys: field/name/key); guarantees every contract field exists (filled
  with "pending" placeholders that later runs can replace).
- Preserves existing richer content: never overwrites a non-placeholder
  value with a placeholder.
- Appends a timestamped entry to change_record on every run.

Usage:
    python3 make_result.py --case /input/case.json \
        --out /app/output/result.json \
        [--status partial|complete|failed] \
        [--source "paper.pdf#page=4,table=2"] ... \
        [--uncertainty "value on p.5 illegible; flagged uncertain"] ... \
        [--note "intake: partial scaffold created"]
"""
import argparse
import datetime
import json
import os
import sys

VERSION = "1.0.0"
PLACEHOLDERS = {None, "", "pending", "todo", "tbd"}


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def contract_fields(case):
    """Extract output_contract field names from any supported shape."""
    oc = (case or {}).get("output_contract")
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                for k in ("field", "name", "key"):
                    if isinstance(item.get(k), str):
                        fields.append(item[k])
                        break
    # de-duplicate, keep order; never shadow core fields we manage
    seen, out = set(), []
    for f in fields:
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Create/update result.json per the output contract.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--out", required=True, help="path to result.json")
    ap.add_argument("--status", choices=["partial", "complete", "failed"])
    ap.add_argument("--source", action="append", default=[],
                    help="repeatable source locator string")
    ap.add_argument("--uncertainty", action="append", default=[],
                    help="repeatable uncertainty statement")
    ap.add_argument("--note", help="change_record entry for this run")
    args = ap.parse_args(argv)

    case = load_json(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown"
    fields = contract_fields(case)

    existing = load_json(args.out)
    result = existing if isinstance(existing, dict) else {}

    result["case_id"] = case_id  # always verbatim from the case

    # core fields
    if args.status:
        result["status"] = args.status
    elif result.get("status") not in ("partial", "complete", "failed"):
        result["status"] = "partial"
    for key in ("sources", "uncertainty", "change_record"):
        if not isinstance(result.get(key), list):
            result[key] = []

    for s in args.source:
        if s not in result["sources"]:
            result["sources"].append(s)
    for u in args.uncertainty:
        if u not in result["uncertainty"]:
            result["uncertainty"].append(u)

    # guarantee contract fields exist without clobbering real content
    for f in fields:
        if f in ("case_id", "status", "sources", "uncertainty",
                 "change_record"):
            continue
        if result.get(f) in PLACEHOLDERS or f not in result:
            result[f] = "pending"

    result["change_record"].append({
        "ts_utc": utcnow(),
        "status": result["status"],
        "note": args.note or "make_result run",
    })

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False, sort_keys=True)
    print("make_result %s: case_id=%s status=%s contract_fields=%d "
          "changes=%d" % (VERSION, case_id, result["status"], len(fields),
                          len(result["change_record"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
