#!/usr/bin/env python3
"""result_make.py — build /app/output/result.json (early-partial + final).

Guarantees the output contract: every root field of the case's
output_contract (from case.json) is present in the result, plus the
original case_id.  Safe to run repeatedly — each run merges into the
existing result file, so secure a partial result EARLY (e.g. right after
reading the case) and enrich it as work proceeds.

Defaults when case.json lacks output_contract:
  status, editable_source, export_artifact, content_map,
  compliance_checks, exceptions

status must be one of: success | partial | unable_to_determine | refused.
A partial status MUST state its limits precisely via --exception.

Usage:
  result_make.py --case /input/case.json --out /app/output/result.json \
      --status partial --set-json 'editable_source=null' \
      --exception "no starting deck in edit mode; planning only"
"""

import argparse
import json
import os

DEFAULT_FIELDS = ["status", "editable_source", "export_artifact",
                  "content_map", "compliance_checks", "exceptions"]

DEFAULTS = {
    "status": "unable_to_determine",
    "editable_source": None,
    "export_artifact": None,
    "content_map": {},
    "compliance_checks": [],
    "exceptions": [],
}

VALID_STATUS = {"success", "partial", "unable_to_determine", "refused"}


def _parse_set(expr):
    """'k="v"' | 'k=123' | 'k=true' | 'k=null' -> (key, python value)"""
    if "=" not in expr:
        raise SystemExit("result_make: bad --set-json %r (want k=json-value)" % expr)
    key, val = expr.split("=", 1)
    key = key.strip()
    val = val.strip()
    try:
        return key, json.loads(val)
    except json.JSONDecodeError:
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            return key, val[1:-1]
        return key, val


def contract_fields(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return list(DEFAULT_FIELDS)


def build_result(case_path, out_path, status, sets, exceptions):
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)
    case_id = case.get("case_id") or case.get("id")

    result = {}
    if out_path and os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            try:
                result = json.load(f)
            except json.JSONDecodeError:
                result = {}

    result["case_id"] = case_id
    for field in contract_fields(case):
        result.setdefault(field, DEFAULTS.get(field))
    # also honour defaults for the standard fields even if the contract
    # omits some of them
    for field in DEFAULT_FIELDS:
        result.setdefault(field, DEFAULTS.get(field))

    if status is not None:
        if status not in VALID_STATUS:
            raise SystemExit("result_make: invalid status %r" % status)
        result["status"] = status
    for expr in sets:
        k, v = _parse_set(expr)
        result[k] = v
    for exc in exceptions:
        result.setdefault("exceptions", [])
        if exc not in result["exceptions"]:
            result["exceptions"].append(exc)

    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json builder (merge-safe)")
    ap.add_argument("--case", default=os.path.join(
        os.environ.get("CASE_INPUT_DIR", "/input"), "case.json"))
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("CASE_OUTPUT_DIR", "/app/output"), "result.json"))
    ap.add_argument("--status", default=None, choices=sorted(VALID_STATUS))
    ap.add_argument("--set-json", action="append", default=[],
                    help="k=json-value; repeatable")
    ap.add_argument("--exception", action="append", default=[],
                    help="append a precise limit/exception; repeatable")
    args = ap.parse_args(argv)

    result = build_result(args.case, args.out, args.status,
                          args.set_json, args.exception)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("wrote %s (case_id=%s, status=%s)"
          % (args.out, result.get("case_id"), result.get("status")))


if __name__ == "__main__":
    main()
