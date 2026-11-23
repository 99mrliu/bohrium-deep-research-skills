#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_result.py — assemble and validate /app/output/result.json.

Required contract fields (see references/output-contract.md):
  case_id, status (success|partial|failed), editable_source,
  export_artifact, content_map, compliance_checks, exceptions

Honesty rules enforced here:
  * status must be one of success|partial|failed;
  * 'success' with a non-empty exceptions list is downgraded to 'partial'
    unless --force-status is given (unresolved issues may not hide behind
    a success label);
  * declared artifacts that do not exist on disk are appended to
    exceptions and force status at most 'partial'.

Usage:
  build_result.py --case-id CASE --status partial \
      --editable-source /app/output/figure.svg \
      --editable-source /app/work/claims.json \
      --export-artifact /app/output/figure.png \
      --export-artifact /app/output/figure.pdf \
      --content-map content_map.json --compliance compliance.json \
      --exceptions exceptions.json --out /app/output/result.json
  (--content-map/--compliance/--exceptions accept a JSON file path;
   omit to start from an empty skeleton.)
"""

import argparse
import json
import os
import sys

REQUIRED = ["case_id", "status", "editable_source", "export_artifact",
            "content_map", "compliance_checks", "exceptions"]
STATUSES = ("success", "partial", "failed")


def load_json(path, default):
    if not path:
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--editable-source", action="append", default=[])
    ap.add_argument("--export-artifact", action="append", default=[])
    ap.add_argument("--content-map")
    ap.add_argument("--compliance")
    ap.add_argument("--exceptions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force-status", action="store_true")
    args = ap.parse_args()

    content_map = load_json(args.content_map, {})
    compliance = load_json(args.compliance, [])
    exceptions = load_json(args.exceptions, [])
    if isinstance(exceptions, str):
        exceptions = [exceptions]
    exceptions = list(exceptions)

    # verify declared files exist
    missing = []
    for f in args.editable_source + args.export_artifact:
        if not os.path.exists(f):
            missing.append(f)
    for f in missing:
        exceptions.append("declared file not found on disk: %s" % f)

    status = args.status
    if not args.force_status:
        if status == "success" and exceptions:
            status = "partial"
            exceptions.append(
                "status downgraded success->partial: exceptions non-empty")
        if missing and status == "success":
            status = "partial"

    result = {
        "case_id": args.case_id,
        "status": status,
        "editable_source": args.editable_source,
        "export_artifact": args.export_artifact,
        "content_map": content_map,
        "compliance_checks": compliance,
        "exceptions": exceptions,
    }
    problems = [k for k in REQUIRED if k not in result or result[k] is None]
    if problems:
        print("ERROR: missing required fields: %s" % problems, file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print("wrote %s: status=%s, %d editable, %d exports, %d exceptions" % (
        args.out, status, len(args.editable_source),
        len(args.export_artifact), len(exceptions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
