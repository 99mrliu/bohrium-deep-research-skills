#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize_result.py — create / safely update result.json against the case's output_contract.

Usage:
  python3 finalize_result.py --case /input/case.json --out /app/output/result.json \
      --status partial [--note "..."] [--field key=value]... [--force]

Guarantees:
  - If result.json does not exist, create it with the original case_id and every key
    declared in output_contract ("" when unfilled). Run this FIRST to secure a valid,
    submittable partial result, then improve it in place.
  - Never overwrite a non-empty field unless --force is given.
  - Every invocation appends an entry to the change_record list.
Python 3.8+, stdlib only.
"""
import argparse
import json
import os
from collections import OrderedDict

VALID_STATUS = ("success", "partial", "unable_to_determine", "refused")


def load_case(path):
    with open(path, "r", encoding="utf-8") as fh:
        case = json.load(fh)
    if "case_id" not in case:
        raise SystemExit("error: case file %s has no case_id" % path)
    contract = case.get("output_contract", {})
    if isinstance(contract, list):
        contract = {k: "" for k in contract}
    if not isinstance(contract, dict):
        raise SystemExit("error: output_contract must be an object or list of keys")
    return case["case_id"], contract


def parse_field(kv):
    if "=" not in kv:
        raise SystemExit("error: --field expects key=value, got %r" % kv)
    k, v = kv.split("=", 1)
    return k.strip(), v


def main():
    ap = argparse.ArgumentParser(description="Create/update result.json per output_contract.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", required=True, choices=VALID_STATUS)
    ap.add_argument("--note", default="")
    ap.add_argument("--field", action="append", default=[], metavar="key=value")
    ap.add_argument("--force", action="store_true", help="allow overwriting non-empty fields")
    args = ap.parse_args()

    case_id, contract = load_case(args.case)

    if os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8") as fh:
            result = json.load(fh)
        if result.get("case_id") != case_id:
            raise SystemExit("error: existing result.json case_id %r != case file %r"
                             % (result.get("case_id"), case_id))
    else:
        result = OrderedDict()
        result["case_id"] = case_id
        for key in contract:
            result[key] = ""
        result["status"] = "partial"
        result["change_record"] = []

    # ensure every contract key exists
    for key in contract:
        result.setdefault(key, "")
    result.setdefault("change_record", [])

    applied, skipped = [], []
    for kv in args.field:
        k, v = parse_field(kv)
        existing = result.get(k, "")
        if existing and not args.force:
            skipped.append(k)
            continue
        result[k] = v
        applied.append(k)

    result["status"] = args.status
    entry = OrderedDict()
    entry["status"] = args.status
    if args.note:
        entry["note"] = args.note
    entry["fields_set"] = applied
    if skipped:
        entry["fields_skipped_nonempty"] = skipped
    result["change_record"].append(entry)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("wrote %s: status=%s applied=%s skipped=%s"
          % (args.out, args.status, ",".join(applied) or "-", ",".join(skipped) or "-"))


if __name__ == "__main__":
    main()
