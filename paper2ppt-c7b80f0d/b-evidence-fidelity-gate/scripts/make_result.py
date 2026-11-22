#!/usr/bin/env python3
"""make_result.py -- write/update /app/output/result.json from case.json.

Stdlib only. Robust against real-world case.json shapes:
  * case id may be under "case_id", "id", "caseId", or nested "case"."id";
  * "output_contract" may be missing, a list of field names (list of str),
    a list of dicts (each with "name"/"field"/"key"), or a dict containing
    "fields"/"required_fields" in either of those forms.

Merging rules (never destroys existing richer content):
  * an existing result.json is loaded and updated in place;
  * contract fields missing from the result are created with a null
    placeholder; existing non-empty values are kept untouched;
  * "case_id" is set/updated from the case;
  * --status sets top-level "status"; --uncertainty appends to "uncertainty"
    (list-ified if needed); --note appends a timestamped entry to "change_log";
  * no key is ever deleted.

Usage:
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      [--status partial|complete|failed] [--uncertainty "text"] [--note "text"]

Exit codes: 0 success; 2 bad inputs.
"""
import argparse
import datetime
import json
import os
import sys


def fail(msg):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(2)


def field_names(contract):
    """Extract required field names from any tolerated contract shape."""
    if contract is None:
        return []
    if isinstance(contract, dict):
        for k in ("fields", "required_fields", "required", "outputs"):
            if k in contract:
                return field_names(contract[k])
        # dict of fieldname -> spec
        return [str(k) for k in contract.keys()]
    if isinstance(contract, list):
        out = []
        for item in contract:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for k in ("name", "field", "key", "id"):
                    if isinstance(item.get(k), str):
                        out.append(item[k])
                        break
        return out
    return []


def find_case_id(case):
    for k in ("case_id", "caseId", "id", "name"):
        if isinstance(case.get(k), str) and case[k]:
            return case[k]
    inner = case.get("case")
    if isinstance(inner, dict):
        for k in ("case_id", "id"):
            if isinstance(inner.get(k), str) and inner[k]:
                return inner[k]
    return None


def main():
    ap = argparse.ArgumentParser(description="Write/update result.json honoring output_contract.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--status", default=None,
                    choices=["partial", "complete", "failed", "in_progress"])
    ap.add_argument("--uncertainty", default=None, help="uncertainty note to append")
    ap.add_argument("--note", default=None, help="change-record note to append")
    args = ap.parse_args()

    if not os.path.isfile(args.case):
        fail("case.json not found: %s" % args.case)
    try:
        case = json.load(open(args.case, encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail("case.json is not valid JSON: %s" % e)
    if not isinstance(case, dict):
        fail("case.json top level is not an object")

    result = {}
    if os.path.isfile(args.out):
        try:
            existing = json.load(open(args.out, encoding="utf-8"))
            if isinstance(existing, dict):
                result = existing
        except json.JSONDecodeError:
            sys.stderr.write("WARNING: existing %s is not valid JSON; starting fresh "
                             "(old file left untouched at %s.bak)\n" % (args.out, args.out))
            os.replace(args.out, args.out + ".bak")

    cid = find_case_id(case)
    if cid:
        result["case_id"] = cid
    elif "case_id" not in result:
        result["case_id"] = None
        sys.stderr.write("WARNING: no case id found in case.json\n")

    for fname in field_names(case.get("output_contract")):
        if fname not in result or result[fname] in (None, "", [], {}):
            result.setdefault(fname, None)  # placeholder; never overwrite real content

    if args.status:
        result["status"] = args.status
    else:
        result.setdefault("status", "partial")

    if args.uncertainty:
        unc = result.get("uncertainty")
        if unc is None:
            result["uncertainty"] = [args.uncertainty]
        elif isinstance(unc, list):
            unc.append(args.uncertainty)
        else:
            result["uncertainty"] = [str(unc), args.uncertainty]
    else:
        result.setdefault("uncertainty", [])

    log = result.get("change_log")
    if not isinstance(log, list):
        log = [] if log is None else [str(log)]
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    log.append({"ts": ts, "note": args.note or ("status -> %s" % result["status"])})
    result["change_log"] = log

    result.setdefault("sources", [])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    sys.stdout.write("result.json updated: case_id=%r status=%r fields=%d -> %s\n"
                     % (result.get("case_id"), result.get("status"),
                        len(field_names(case.get("output_contract"))), args.out))


if __name__ == "__main__":
    main()
