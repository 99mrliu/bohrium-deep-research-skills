#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_contract.py — output-contract validator (合同校验) for delivery-forge.

Reads the case's ACTUAL `output_contract` field names from the case file —
never assumes a fixed schema — and verifies that `result.json` in the
output directory is complete and honest before submission. Emits
`contract_check.json`; non-zero exit on any violation. A failed contract
check blocks delivery (quality-gate order: render → census → contract
validate).

Checks:
  1. result.json exists in the output dir and parses as a JSON object.
  2. result["case_id"] equals the case file's case_id.
  3. result contains EVERY field named by the case's output_contract.
     A field may be null/absent ONLY if status is "partial" or "failed"
     AND the gap is named inside the `uncertainty` field (string or list).
  4. status ∈ {"success", "partial", "failed"}.
  5. sources is a non-empty list.
  6. change records exist: `change_log` (or `change_records`) field is a
     non-empty list, or a change_log.md file is present in the output dir.
  7. Every file referenced inside result.json (any string value that looks
     like a relative file path with an extension, URLs excluded) actually
     exists in the output dir.

Contract field-name discovery:
  * output_contract as list  -> the list items (strings).
  * output_contract as dict  -> its keys (dict of field -> description).
  * output_contract as object with "fields"/"required" list/dict inside.
  * MISSING output_contract  -> documented fallback, the topic's standard
    fields: deliverable, fact_source_map, version_boundary, status,
    sources, uncertainty, change_log.

Usage:
  python3 validate_contract.py --case /input/case.json --outdir /app/output
"""
import argparse
import json
import os
import re
import sys

FALLBACK_FIELDS = ["deliverable", "fact_source_map", "version_boundary",
                   "status", "sources", "uncertainty", "change_log"]
HONEST_STATUSES = {"success", "partial", "failed"}
PATHISH_RE = re.compile(r"^[\w./\-一-鿿（）() ]+\.[A-Za-z0-9]{1,8}$")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def discover_contract_fields(case):
    """Return (fields, origin). origin ∈ explicit|fallback."""
    oc = case.get("output_contract")
    fields = None
    if isinstance(oc, list) and oc:
        fields = [str(f) for f in oc]
    elif isinstance(oc, dict) and oc:
        for key in ("fields", "required", "required_fields"):
            sub = oc.get(key)
            if isinstance(sub, list) and sub:
                fields = [str(f) for f in sub]
                break
            if isinstance(sub, dict) and sub:
                fields = list(sub)
                break
        if fields is None:
            fields = list(oc)
    if fields:
        return fields, "explicit"
    return list(FALLBACK_FIELDS), "fallback"


def iter_strings(obj):
    """Yield every string value nested anywhere in obj."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_strings(v)


# Top-level result.json keys that carry provenance/prose, NOT deliverable
# file references: strings under them are exempt from the existence check.
NON_FILE_KEYS = {"sources", "uncertainty", "change_log", "change_records",
                 "case_id", "_comment", "status"}


def uncertainty_mentions(uncertainty, field):
    if uncertainty is None:
        return False
    blob = " ".join(iter_strings(uncertainty)) if not isinstance(uncertainty, str) else uncertainty
    return field.lower() in blob.lower()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate result.json against the case's actual output_contract.")
    ap.add_argument("--case", required=True, help="case.json path (copy is fine)")
    ap.add_argument("--outdir", required=True, help="output directory containing result.json")
    ap.add_argument("--report", default=None, help="contract_check.json path (default: <outdir>/contract_check.json)")
    args = ap.parse_args(argv)

    report_path = args.report or os.path.join(args.outdir, "contract_check.json")
    check = {"tool": "validate_contract.py", "case": os.path.abspath(args.case),
             "outdir": os.path.abspath(args.outdir), "violations": [], "warnings": []}

    def violate(msg):
        check["violations"].append(msg)

    # --- case file -------------------------------------------------------
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except Exception as exc:
        violate("case file unreadable: %s: %s" % (type(exc).__name__, exc))
        case = {}
    case_id = case.get("case_id")
    fields, origin = discover_contract_fields(case)
    check["contract_fields"] = fields
    check["contract_origin"] = origin
    if origin == "fallback":
        check["warnings"].append("case file has no explicit output_contract; "
                                 "using documented fallback fields: %s" % ", ".join(fields))

    # --- result.json -----------------------------------------------------
    result_path = os.path.join(args.outdir, "result.json")
    result = None
    if not os.path.isfile(result_path):
        violate("result.json missing at %s" % result_path)
    else:
        try:
            with open(result_path, "r", encoding="utf-8") as fh:
                result = json.load(fh)
            if not isinstance(result, dict):
                violate("result.json is not a JSON object")
                result = None
        except Exception as exc:
            violate("result.json does not parse: %s: %s" % (type(exc).__name__, exc))

    if result is not None:
        # case_id match
        if case_id is not None and result.get("case_id") != case_id:
            violate("case_id mismatch: result has %r, case file has %r"
                    % (result.get("case_id"), case_id))

        status = result.get("status")
        # honest status
        if status not in HONEST_STATUSES:
            violate("status %r not in %s" % (status, sorted(HONEST_STATUSES)))

        # every contract field present (null allowed only when partial/failed
        # AND the gap is named in uncertainty)
        degraded = status in ("partial", "failed")
        missing_fields = []
        for f in fields:
            val = result.get(f)
            if val is None or val == "":
                if degraded and uncertainty_mentions(result.get("uncertainty"), f):
                    check["warnings"].append(
                        "field '%s' empty but excused: status=%s and gap named in uncertainty" % (f, status))
                else:
                    missing_fields.append(f)
        for f in missing_fields:
            violate("contract field missing/empty: '%s'" % f)

        # non-empty sources
        src = result.get("sources")
        if not isinstance(src, list) or not src:
            violate("sources must be a non-empty list")

        # change records
        cl = result.get("change_log") or result.get("change_records")
        cl_ok = isinstance(cl, list) and len(cl) > 0
        cl_file = os.path.isfile(os.path.join(args.outdir, "change_log.md"))
        if not cl_ok and not cl_file:
            violate("no change records: change_log/change_records list empty and change_log.md absent")

        # referenced files must exist in the output dir (provenance/prose
        # fields like sources/uncertainty/change_log are exempt)
        missing_files = []
        refs = []
        for k, v in result.items():
            if k in NON_FILE_KEYS:
                continue
            refs.extend(iter_strings(v))
        for s in refs:
            if URL_RE.match(s) or not PATHISH_RE.match(s):
                continue
            if os.path.isabs(s):
                continue  # absolute runtime paths (e.g. /input/...) not checked
            if not os.path.isfile(os.path.join(args.outdir, s)):
                missing_files.append(s)
        for s in sorted(set(missing_files)):
            violate("referenced file not found in output dir: '%s'" % s)

    check["verdict"] = "PASS" if not check["violations"] else "FAIL"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(check, fh, ensure_ascii=False, indent=2)

    print("contract: %s — %d violation(s), %d warning(s) (contract origin: %s, %d fields)"
          % (check["verdict"], len(check["violations"]), len(check["warnings"]), origin, len(fields)))
    for v in check["violations"]:
        print("  VIOLATION: %s" % v)
    return 0 if not check["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
