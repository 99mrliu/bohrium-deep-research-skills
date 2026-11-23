#!/usr/bin/env python3
"""build_result.py -- assemble /app/output/result.json from parts and validate
the output contract.

Usage:
    python3 build_result.py --case-id ID --status success|partial|failed \
        --editable-source FILE.tex \
        --export-artifact FILE [--export-artifact FILE2 ...] \
        --content-map FILE.json --compliance FILE.json \
        --exceptions FILE.json --out /app/output/result.json \
        [--limits "describes partial limits"] [--notes "free text"]

content-map file : JSON object {"figure element": "source locator", ...}
compliance file  : JSON list or object with check results
exceptions file  : JSON list of strings (or objects)
Validates required contract fields, warns (in the JSON + stderr) on empty
values; partial status without --limits triggers a warning.
Exit 0 on written result, 2 on bad args.
Only Python 3 standard library.
"""

import argparse
import json
import os
import sys

REQUIRED = ["case_id", "status", "editable_source", "export_artifact",
            "content_map", "compliance_checks", "exceptions"]
STATUSES = ("success", "partial", "failed")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser(description="Assemble and validate result.json.")
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--editable-source", required=True)
    ap.add_argument("--export-artifact", action="append", default=[],
                    help="repeatable: exported files (pdf/png/svg)")
    ap.add_argument("--content-map", required=True, help="JSON file")
    ap.add_argument("--compliance", required=True, help="JSON file")
    ap.add_argument("--exceptions", required=True, help="JSON file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limits", default=None,
                    help="required when status=partial: name the limits")
    ap.add_argument("--notes", default=None)
    args = ap.parse_args()

    warnings = []

    content_map = load_json(args.content_map, {})
    compliance = load_json(args.compliance, [])
    exceptions = load_json(args.exceptions, [])

    if not isinstance(content_map, dict) or not content_map:
        warnings.append("content_map is empty or not an object; every key "
                        "figure element should map to a source locator")
    if not compliance:
        warnings.append("compliance_checks is empty; run verify/export scripts "
                        "and record their JSON")
    if args.status == "partial" and not args.limits:
        warnings.append("status=partial but no --limits given; partial must "
                        "name its limits")
    if args.status == "success" and exceptions:
        warnings.append("status=success but exceptions is non-empty; confirm "
                        "this is honest")
    if not args.export_artifact:
        warnings.append("no export artifacts listed")
    src = args.editable_source
    if not src.endswith(".tex"):
        warnings.append("editable_source should be the .tex source file")

    result = {
        "case_id": args.case_id,
        "status": args.status,
        "editable_source": os.path.abspath(src),
        "export_artifact": [os.path.abspath(a) for a in args.export_artifact],
        "content_map": content_map,
        "compliance_checks": compliance,
        "exceptions": exceptions,
        "generator": "tikz-mechanism-typeset skill (LaTeX/TikZ typeset-driven)",
    }
    if args.limits:
        result["limits"] = args.limits
    if args.notes:
        result["notes"] = args.notes
    if warnings:
        result["contract_warnings"] = warnings

    missing = [k for k in REQUIRED if k not in result or result[k] in (None, "", [])]
    if missing:
        warnings.append("required fields empty/missing: %s" % ", ".join(missing))
        result["contract_warnings"] = warnings

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)

    for w in warnings:
        sys.stderr.write("WARNING: %s\n" % w)
    print(json.dumps({"written": os.path.abspath(args.out),
                      "warnings": warnings}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
