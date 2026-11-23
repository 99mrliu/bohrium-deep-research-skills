#!/usr/bin/env python3
"""write_result.py — safe, incremental result.json writer.

Semantics:
  * if result.json does not exist, create it with case_id (from
    /input/case.json), the given status, and every key declared in the
    case's output_contract ("" when unfilled);
  * never overwrite a non-empty field without --force;
  * --field key=value fills empty (or forced) fields; --note appends a
    note; every invocation appends an entry to the change_record list.
"""
import argparse
import json
import os
import sys
import time

VALID_STATUS = ("success", "partial", "unable_to_determine", "refused")


def contract_keys(case):
    oc = case.get("output_contract", [])
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return list(oc)
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--out", required=True, help="result.json path")
    ap.add_argument("--status", required=True, choices=VALID_STATUS)
    ap.add_argument("--note", default=None)
    ap.add_argument("--field", action="append", default=[],
                    metavar="key=value")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting non-empty fields")
    args = ap.parse_args()

    with open(args.case, "r", encoding="utf-8") as fh:
        case = json.load(fh)
    cid = case.get("case_id", "")
    keys = contract_keys(case)

    if os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8") as fh:
            result = json.load(fh)
    else:
        result = {"case_id": cid, "status": args.status}
        for k in keys:
            result.setdefault(k, "")

    # keep case_id immutable and aligned with the actual case file
    if result.get("case_id") not in (cid, ""):
        sys.stderr.write("WARNING: case_id mismatch, keeping existing %r\n"
                         % result.get("case_id"))
    result["case_id"] = result.get("case_id") or cid
    result["status"] = args.status

    for kv in args.field:
        if "=" not in kv:
            sys.stderr.write("ERROR: --field needs key=value, got %r\n" % kv)
            sys.exit(2)
        k, v = kv.split("=", 1)
        old = result.get(k, "")
        if old not in ("", None) and not args.force:
            sys.stderr.write(
                "SKIP: field %r already non-empty; use --force to overwrite\n"
                % k)
            continue
        result[k] = v

    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "status": args.status}
    if args.note:
        record["note"] = args.note
    result.setdefault("change_record", []).append(record)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("wrote %s (case_id=%s, status=%s, fields=%d)"
          % (args.out, result["case_id"], result["status"], len(keys)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
