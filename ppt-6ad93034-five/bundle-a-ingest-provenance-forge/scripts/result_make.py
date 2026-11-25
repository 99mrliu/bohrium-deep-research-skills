#!/usr/bin/env python3
"""result.json writer: secure a partial EARLY, improve in place.

Reads the REAL case.json, takes case_id (key "case_id" or "id") and copies
EVERY root field of output_contract verbatim into the result (defaults when
absent: status, editable_source, export_artifact, content_map,
compliance_checks, exceptions). Re-running merges into the existing
result.json so an early partial can be upgraded to success in place.

Usage:
    python3 result_make.py --case /input/case.json --out /app/output/result.json \
        --status partial \
        --set-json 'editable_source="/app/output/presentation.pptx"' \
        --set-json 'compliance_checks={"spans_verified": true}' \
        --exception "soffice missing: no PDF export"
"""
import argparse
import json
import os
import sys

DEFAULT_CONTRACT = {
    "status": "result status: success|partial|unable_to_determine|refused",
    "editable_source": "path to editable deck",
    "export_artifact": "path to exported PDF (or null)",
    "content_map": "map of slide -> evidence",
    "compliance_checks": "named boolean checks",
    "exceptions": "list of known limitations",
}
STATUSES = {"success", "partial", "unable_to_determine", "refused"}


def log(msg):
    print(f"[result_make] {msg}", flush=True)


def default_value(key):
    return {"status": "partial", "editable_source": None, "export_artifact": None,
            "content_map": {}, "compliance_checks": {}, "exceptions": []}.get(key)


def main():
    ap = argparse.ArgumentParser(description="Write/merge result.json from the case contract")
    ap.add_argument("--case", default=None, help="case.json (default: <input>/case.json)")
    ap.add_argument("--out", default=None, help="result.json (default: <output>/result.json)")
    ap.add_argument("--status", choices=sorted(STATUSES), default=None)
    ap.add_argument("--set-json", action="append", default=[], metavar="KEY=JSON",
                    help="set a contract field to a JSON value (repeatable)")
    ap.add_argument("--exception", action="append", default=[],
                    help="append an exception/limitation string (repeatable)")
    ap.add_argument("--check", action="append", default=[], metavar="NAME=BOOL",
                    help="set compliance_checks.NAME to true/false (repeatable)")
    ap.add_argument("--input-dir", default=os.environ.get("CASE_INPUT_DIR", "/input"))
    ap.add_argument("--work-dir", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--output-dir", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args()
    case_path = args.case or os.path.join(args.input_dir, "case.json")
    out_path = args.out or os.path.join(args.output_dir, "result.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    case = {}
    if os.path.isfile(case_path):
        case = json.load(open(case_path, encoding="utf-8"))
    else:
        log(f"WARNING: case.json not found at {case_path}; using defaults")
    case_id = case.get("case_id") or case.get("id") or "unknown"
    contract = case.get("output_contract") or DEFAULT_CONTRACT

    result = {}
    if os.path.isfile(out_path):
        try:
            result = json.load(open(out_path, encoding="utf-8"))
        except Exception:
            result = {}
    result["case_id"] = case_id
    for key in contract:  # every root field of the contract, verbatim keys
        if key not in result:
            result[key] = default_value(key)

    if args.status:
        result["status"] = args.status
    for item in args.set_json:
        if "=" not in item:
            log(f"FATAL: --set-json expects KEY=JSON, got {item!r}")
            return 2
        key, raw = item.split("=", 1)
        result[key] = json.loads(raw)
    for item in args.check:
        if "=" not in item:
            log(f"FATAL: --check expects NAME=BOOL, got {item!r}")
            return 2
        key, raw = item.split("=", 1)
        checks = result.get("compliance_checks")
        if not isinstance(checks, dict):
            checks = {}
        checks[key] = raw.strip().lower() in ("1", "true", "yes")
        result["compliance_checks"] = checks
    if args.exception:
        exc = result.get("exceptions")
        if not isinstance(exc, list):
            exc = [exc] if exc else []
        for e in args.exception:
            if e not in exc:
                exc.append(e)
        result["exceptions"] = exc

    # pass through a synthetic marker declared by the case itself
    if case.get("synthetic_example") and "synthetic_example" not in result:
        result["synthetic_example"] = True

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log(f"wrote {out_path} (status={result.get('status')}, case_id={case_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
