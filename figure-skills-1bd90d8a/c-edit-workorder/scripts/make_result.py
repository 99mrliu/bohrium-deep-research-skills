#!/usr/bin/env python3
"""make_result.py - create or update /app/output/result.json honestly.

PURE STDLIB.  Run EARLY (first minutes of the budget) to guarantee a partial
result exists, then re-run to refine.  Guarantees:
  * case_id copied verbatim from case.json (never invented)
  * every field named by the case output_contract exists - "pending"
    placeholders until real content is supplied; existing richer content is
    never overwritten by placeholders
  * status / sources / uncertainty / change_record stamped from args

Tolerates output_contract as: dict {field: description}, list of strings, or
list of dicts (keys like name/field/key/id).

Usage:
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --status partial --sources "paper.pdf#page=3,data.csv#column=rate" \
      --uncertainty "yerr column missing in CSV" --note "compose done"
"""
import argparse
import datetime
import json
import os
import sys


def contract_fields(case):
    oc = case.get("output_contract")
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                for k in ("name", "field", "key", "id"):
                    if k in item:
                        fields.append(str(item[k]))
                        break
    elif isinstance(oc, str):
        fields = [oc]
    return [f for f in fields if f]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default=None)
    ap.add_argument("--sources", default=None,
                    help="comma-separated list or JSON array")
    ap.add_argument("--uncertainty", default=None)
    ap.add_argument("--change-record", dest="change_record", default=None,
                    help="path to change_log.json or a short string")
    ap.add_argument("--note", default=None)
    args = ap.parse_args()

    case = {}
    try:
        with open(args.case, encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("WARNING: case.json unreadable (%s); case_id will be 'unknown'"
              % exc, file=sys.stderr)
    case_id = case.get("case_id", case.get("id", "unknown"))

    result = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as fh:
                result = json.load(fh)
        except (OSError, json.JSONDecodeError):
            result = {}

    result["case_id"] = case_id  # always verbatim from case.json
    fields = contract_fields(case)
    for f in fields:
        if f not in result or result[f] in (None, ""):
            result[f] = "pending"
    result["output_contract_fields"] = fields

    if args.status is not None:
        result["status"] = args.status
    else:
        result.setdefault("status", "partial")

    if args.sources is not None:
        s = args.sources.strip()
        if s.startswith("["):
            try:
                result["sources"] = json.loads(s)
            except json.JSONDecodeError:
                result["sources"] = [s]
        else:
            result["sources"] = [x.strip() for x in s.split(",") if x.strip()]
    else:
        result.setdefault("sources", [])

    if args.uncertainty is not None:
        result["uncertainty"] = args.uncertainty
    else:
        result.setdefault("uncertainty",
                          "not yet assessed (result saved early)")

    if args.change_record is not None:
        cr = args.change_record
        if os.path.exists(cr):
            try:
                with open(cr, encoding="utf-8") as fh:
                    data = json.load(fh)
                result["change_record"] = data.get("summary", data)
            except (OSError, json.JSONDecodeError):
                result["change_record"] = "unreadable: %s" % cr
        else:
            result["change_record"] = cr
    else:
        result.setdefault("change_record", "no edits applied yet")

    notes = result.setdefault("notes", [])
    if isinstance(notes, str):
        notes = result["notes"] = [notes]
    if args.note:
        notes.append("%s %s" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            args.note))
    result["updated_at"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    missing = [f for f in fields if result.get(f) in (None, "", "pending")]
    print("result.json: case_id=%s status=%s contract_fields=%d pending=%s"
          % (case_id, result["status"], len(fields), missing or "none"))


if __name__ == "__main__":
    main()
