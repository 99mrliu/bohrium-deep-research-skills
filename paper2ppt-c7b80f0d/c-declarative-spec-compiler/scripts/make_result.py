#!/usr/bin/env python3
"""make_result.py -- create/update /app/output/result.json from the case contract.

Reads /input/case.json, preserves case_id and any richer content already in
result.json, guarantees every field named by the case's output_contract exists,
and stamps status / sources / uncertainty / change_record. Robust by design:
tolerates missing keys, and output_contract given as a list of strings, a list
of dicts ({"name"|"field"|"key": ...}), or a dict of field names.

Save a partial result.json EARLY (run this right after reading the case), then
re-run at the end with --status complete. Pure Python 3 stdlib.
"""
import argparse
import json
import os
import sys
import time


def _contract_fields(case):
    """Extract required output field names from a case's output_contract."""
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(oc, dict):
        if isinstance(oc.get("fields"), list):
            items = oc["fields"]
        elif isinstance(oc.get("required"), list):
            items = oc["required"]
        else:
            items = list(oc.keys())
    elif isinstance(oc, list):
        items = oc
    else:
        return []
    for it in items:
        if isinstance(it, str) and it.strip():
            fields.append(it.strip())
        elif isinstance(it, dict):
            for k in ("name", "field", "key"):
                if isinstance(it.get(k), str) and it[k].strip():
                    fields.append(it[k].strip())
                    break
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(description="Create/update /app/output/result.json.")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--status", default="partial", choices=["partial", "complete", "failed"])
    ap.add_argument("--sources", default=None, help="JSON list or comma-separated source files")
    ap.add_argument("--uncertainty", default=None, help="uncertainty statement")
    ap.add_argument("--note", default=None, help="change-record note for this update")
    args = ap.parse_args(argv)

    case = {}
    if os.path.isfile(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
        except json.JSONDecodeError as e:
            print(f"make_result: WARNING case.json unreadable ({e}); continuing with defaults",
                  file=sys.stderr)
    else:
        print(f"make_result: WARNING {args.case} not found; continuing with defaults",
              file=sys.stderr)

    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    fields = _contract_fields(case)

    result = {}
    if os.path.isfile(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                prev = json.load(f)
            if isinstance(prev, dict):
                result = prev  # preserve existing richer content
        except json.JSONDecodeError:
            print("make_result: WARNING existing result.json invalid; starting fresh",
                  file=sys.stderr)

    result["case_id"] = result.get("case_id") or case_id
    if result["case_id"] != case_id and case_id != "unknown-case":
        result["case_id"] = case_id  # original case id always wins

    missing = []
    for fld in fields:
        if fld not in result or result[fld] in (None, "", [], {}):
            result[fld] = {"status": "pending",
                           "note": "field required by output_contract; "
                                   "populated when the artifact is produced"}
            missing.append(fld)

    result["status"] = args.status
    if args.sources:
        try:
            result["sources"] = json.loads(args.sources)
        except json.JSONDecodeError:
            result["sources"] = [s.strip() for s in args.sources.split(",") if s.strip()]
    result.setdefault("sources", [])
    if args.uncertainty is not None:
        result["uncertainty"] = args.uncertainty
    result.setdefault("uncertainty",
                      "Not yet assessed; see compile_report.json warnings and "
                      "render_manifest.json status for known limitations.")

    cr = result.get("change_record")
    if not isinstance(cr, list):
        cr = []
    cr.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "status": args.status,
               "note": args.note or f"result.json {'updated' if cr else 'created'} by make_result.py",
               "missing_contract_fields": missing})
    result["change_record"] = cr

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.out)
    print(f"make_result: wrote {args.out} status={args.status} case_id={result['case_id']} "
          f"contract_fields={len(fields)} pending={missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
