#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_result.py -- assemble /app/output/result.json per the runtime contract.

Required fields: case_id, status (success|partial|failed), editable_source,
export_artifact, content_map, compliance_checks, exceptions.
Status honesty rules: "partial" MUST name its limits in exceptions;
"failed" MUST explain why.

CLI:
  python3 build_result.py --case-id ID --status success \
      --editable-source /app/output/figure.drawio [--editable-source ...] \
      --export-artifact /app/output/figure.png [--export-artifact ...] \
      --content-map FILE --compliance FILE --exceptions FILE --out FILE
--content-map/--compliance/--exceptions accept a JSON file or a literal JSON string.
"""
import argparse
import json
import os
import sys

REQUIRED = ["case_id", "status", "editable_source", "export_artifact",
            "content_map", "compliance_checks", "exceptions"]
STATUSES = ("success", "partial", "failed")


def _load_jsonish(value, default):
    if value is None:
        return default
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def main(argv=None):
    ap = argparse.ArgumentParser(description="assemble result.json")
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--editable-source", action="append", default=[])
    ap.add_argument("--export-artifact", action="append", default=[])
    ap.add_argument("--content-map")
    ap.add_argument("--compliance")
    ap.add_argument("--exceptions")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    result = {
        "case_id": args.case_id,
        "status": args.status,
        "editable_source": args.editable_source,
        "export_artifact": args.export_artifact,
        "content_map": _load_jsonish(args.content_map, {}),
        "compliance_checks": _load_jsonish(args.compliance, []),
        "exceptions": _load_jsonish(args.exceptions, []),
    }
    problems = []
    for field in REQUIRED:
        if field not in result or result[field] in (None, ""):
            problems.append("missing required field: %s" % field)
    if args.status == "partial" and not result["exceptions"]:
        problems.append("status=partial but exceptions is empty (name the limits)")
    if args.status == "failed" and not result["exceptions"]:
        problems.append("status=failed but exceptions is empty (explain why)")
    for path in result["editable_source"] + result["export_artifact"]:
        if not os.path.exists(path):
            problems.append("artifact does not exist: %s" % path)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    summary = {"status": "ok" if not problems else "invalid",
               "out": os.path.abspath(args.out), "problems": problems}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
