#!/usr/bin/env python3
"""make_result.py -- idempotently create / improve result.json for a case.

Usage:
    python3 make_result.py --case /input/case.json --out /app/output/result.json \
        --status <status> [--note "..."] [--field key=value]... [--force]

- Creates result.json if absent, containing the original case_id and every key
  declared in output_contract (value "" until filled).
- Never overwrites a non-empty existing field unless --force.
- Appends {"note","status"} (with UTC timestamp) to a "change_record" list.
- Safe to run FIRST, before any real work, to secure a partial deliverable.

Stdlib only.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

VALID_STATUS = {"success", "partial", "unable_to_determine", "refused"}


def main():
    ap = argparse.ArgumentParser(description="Create/improve result.json idempotently.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--out", required=True, help="path to result.json")
    ap.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    ap.add_argument("--note", default="", help="free-form note for the change record")
    ap.add_argument("--field", action="append", default=[],
                    help="key=value to fill into result.json (repeatable)")
    ap.add_argument("--force", action="store_true", help="allow overwriting non-empty fields")
    args = ap.parse_args()

    with open(args.case, "r", encoding="utf-8") as f:
        case = json.load(f)
    case_id = case.get("case_id")
    if not case_id:
        sys.exit("ERROR: case.json has no 'case_id'")
    contract = case.get("output_contract", {})
    if isinstance(contract, list):
        contract_keys = contract
    elif isinstance(contract, dict):
        contract_keys = list(contract.keys())
    else:
        contract_keys = []

    if os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8") as f:
            result = json.load(f)
    else:
        result = {}
    result["case_id"] = case_id  # always keep original case_id in sync
    for k in contract_keys:
        result.setdefault(k, "")
    result.setdefault("status", "")
    result.setdefault("change_record", [])

    for kv in args.field:
        if "=" not in kv:
            sys.exit(f"ERROR: --field must be key=value, got {kv!r}")
        key, value = kv.split("=", 1)
        key = key.strip()
        if not key:
            sys.exit("ERROR: --field key must be non-empty")
        existing = result.get(key, "")
        if existing and not args.force:
            print(f"  SKIP {key!r}: already non-empty (use --force to overwrite)")
        else:
            result[key] = value
            print(f"  SET  {key!r} = {value[:60]!r}")

    result["status"] = args.status
    result["change_record"].append({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": args.status,
        "note": args.note,
    })

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, args.out)  # atomic-ish write

    empty = [k for k in contract_keys if not result.get(k)]
    print(f"make_result: case_id={case_id} status={args.status} "
          f"contract_fields={len(contract_keys)} empty={len(empty)}")
    if empty:
        print(f"  still empty: {', '.join(empty)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
