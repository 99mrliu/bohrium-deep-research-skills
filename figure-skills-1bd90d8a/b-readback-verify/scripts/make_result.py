#!/usr/bin/env python3
"""make_result.py -- create or update /app/output/result.json.

Copies case_id verbatim from case.json, tolerates output_contract given as
a dict {field: spec}, a list of strings, or a list of dicts with a
"name"/"field" key. Existing richer content is preserved: contract fields
that are already filled are never overwritten; missing ones get a
"pending" placeholder. Every call appends a timestamped change_record
entry.

Usage:
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      [--status partial|complete|failed] [--sources sources.json] \
      [--uncertainty "text"] [--note "what changed"]
"""
import sys
import os
import json
import argparse
import datetime


def contract_fields(case):
    oc = case.get("output_contract", [])
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") \
                    or item.get("key")
                if name:
                    fields.append(str(name))
    return fields


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--status", default=None)
    ap.add_argument("--sources", default=None,
                    help="JSON file (list/dict) or a single source string")
    ap.add_argument("--uncertainty", default=None)
    ap.add_argument("--note", default=None)
    args = ap.parse_args()

    case = {}
    if os.path.isfile(args.case):
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    else:
        sys.stderr.write("make_result: WARNING case file %s not found\n"
                         % args.case)

    result = {}
    if os.path.isfile(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            result = {}

    if case.get("case_id") is not None:
        result["case_id"] = case["case_id"]  # verbatim
    result.setdefault("status", "partial")
    if args.status:
        result["status"] = args.status

    for field in contract_fields(case):
        result.setdefault(field, "pending")

    if args.sources:
        loaded = None
        if os.path.isfile(args.sources):
            try:
                with open(args.sources, encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                loaded = None  # not a JSON file -> record as a path string
        if loaded is not None:
            result["sources"] = loaded
        else:
            prev = result.get("sources")
            lst = prev if isinstance(prev, list) else (
                [prev] if prev else [])
            lst.append(args.sources)
            result["sources"] = lst
    result.setdefault("sources", [])
    if args.uncertainty is not None:
        result["uncertainty"] = args.uncertainty
    result.setdefault("uncertainty", "not yet assessed")

    cr = result.get("change_record")
    if not isinstance(cr, list):
        cr = []
    entry = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
             "status": result["status"]}
    if args.note:
        entry["note"] = args.note
    cr.append(entry)
    result["change_record"] = cr

    outdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(outdir or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("make_result: wrote %s (status=%s, fields=%d)" %
          (args.out, result["status"],
           len([k for k in result if k not in
                ("case_id", "status", "sources", "uncertainty",
                 "change_record")])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
