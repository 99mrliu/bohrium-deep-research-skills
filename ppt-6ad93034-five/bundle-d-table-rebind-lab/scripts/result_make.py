#!/usr/bin/env python3
"""result_make.py - write /app/output/result.json (early-partial + final).

Contract:
  * result.json MUST contain the original case_id (case.json key "case_id" or
    "id") and EVERY root field of the case's output_contract (read from
    case.json; if output_contract is absent, the defaults are: status,
    editable_source, export_artifact, content_map, compliance_checks,
    exceptions).
  * status is one of success | partial | unable_to_determine | refused.
  * Run this EARLY with --status partial to secure a valid result.json before
    any heavy step; run it again at the end with the final status. Existing
    fields are preserved across runs unless overwritten via --set-json.

Usage:
  python3 /skills/weekly-skill/scripts/result_make.py \
      --case /input/case.json --out /app/output/result.json \
      --status partial \
      --set-json 'editable_source="presentation.pptx"' \
      --exception "soffice missing: no PDF export"
(--set-json takes a JSON value; --exception is repeatable.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DEFAULT_FIELDS = ["status", "editable_source", "export_artifact",
                  "content_map", "compliance_checks", "exceptions"]
STATUSES = {"success", "partial", "unable_to_determine", "refused"}

FIELD_DEFAULTS = {
    "status": "partial",
    "editable_source": "presentation.pptx",
    "export_artifact": None,
    "content_map": {},
    "compliance_checks": {},
    "exceptions": [],
}


def fail(msg: str, code: int = 2) -> "None":
    print(f"[result_make] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    ap = argparse.ArgumentParser(description="Write/merge result.json.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--out", required=True, help="path to result.json")
    ap.add_argument("--status", default=None, choices=sorted(STATUSES))
    ap.add_argument("--set-json", dest="sets", action="append", default=[],
                    metavar='k=json', help="set field k to a JSON value")
    ap.add_argument("--exception", dest="exceptions", action="append",
                    default=[], help="append an exception note (repeatable)")
    args = ap.parse_args()

    # ---- case identity + output contract
    case_id, fields = None, list(DEFAULT_FIELDS)
    if os.path.isfile(args.case):
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
        case_id = case.get("case_id") or case.get("id")
        contract = case.get("output_contract")
        if isinstance(contract, dict) and contract:
            fields = list(contract.keys())
        elif isinstance(contract, list) and contract:
            fields = [str(x) for x in contract]
    else:
        print(f"[result_make] WARNING: case file {args.case} not found; "
              f"using default contract fields", file=sys.stderr)
    if not case_id:
        fail("case_id not found (need key 'case_id' or 'id' in case.json)")

    # ---- load existing result (early-partial -> final merge)
    result = {}
    if os.path.isfile(args.out):
        with open(args.out, encoding="utf-8") as f:
            result = json.load(f)

    result["case_id"] = case_id
    for field in fields:
        if field not in result:
            result[field] = (FIELD_DEFAULTS.get(field)
                             if field in FIELD_DEFAULTS else None)
    if args.status:
        result["status"] = args.status
    elif not result.get("status"):
        result["status"] = "partial"

    # export_artifact: auto-detect the PDF next to result.json
    if "export_artifact" in fields and not result.get("export_artifact"):
        pdf = os.path.join(os.path.dirname(os.path.abspath(args.out)),
                           "presentation.pdf")
        if os.path.isfile(pdf):
            result["export_artifact"] = "presentation.pdf"

    for kv in args.sets:
        k, sep, v = kv.partition("=")
        if not sep or not k:
            fail(f"bad --set-json {kv!r}; expected k=json")
        try:
            result[k] = json.loads(v)
        except json.JSONDecodeError:
            result[k] = v
    if args.exceptions:
        exc = result.get("exceptions")
        if not isinstance(exc, list):
            exc = [] if exc is None else [exc]
        exc.extend(args.exceptions)
        result["exceptions"] = exc

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[result_make] wrote {args.out}: case_id={case_id}, "
          f"status={result['status']}, fields={sorted(result.keys())}")


if __name__ == "__main__":
    main()
