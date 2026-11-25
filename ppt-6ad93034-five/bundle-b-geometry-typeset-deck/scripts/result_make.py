#!/usr/bin/env python3
"""result_make.py -- write result.json (early-partial AND final).

    result_make.py [--case /input/case.json] [--out /app/output/result.json] \
        --status success|partial|unable_to_determine|refused \
        [--set-json 'compliance_checks={"render_audit":"PASS"}'] ... \
        [--exception "soffice missing; render audit RENDERER_MISSING"] ...

The output ALWAYS contains the original case_id (case.json key `case_id` or
`id`) and EVERY root field of the case's output_contract (read from case.json;
if absent, the six defaults: status, editable_source, export_artifact,
content_map, compliance_checks, exceptions). Unknown contract fields are
filled with null and listed in `_unfilled_contract_fields` so nothing is ever
silently fabricated.

Call it EARLY with --status partial to secure a valid result.json before any
heavy work, then again at the end with the final status. Repeated --set-json
and --exception flags merge into the same file.
"""
import argparse
import json
import os
import sys

DEFAULT_CONTRACT_FIELDS = ["status", "editable_source", "export_artifact",
                           "content_map", "compliance_checks", "exceptions"]
VALID_STATUS = {"success", "partial", "unable_to_determine", "refused"}


def load_case(case_path):
    if case_path and os.path.isfile(case_path):
        try:
            with open(case_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001 - a broken case.json must not lose the result
            return {}
    return {}


def contract_fields(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict) and oc:
        return list(oc.keys())
    if isinstance(oc, list) and oc:
        return [str(k) for k in oc]
    return list(DEFAULT_CONTRACT_FIELDS)


def field_default(field, status, out_dir):
    if field == "status":
        return status
    if field == "editable_source":
        p = os.path.join(out_dir, "presentation.pptx")
        return p if os.path.isfile(p) else None
    if field == "export_artifact":
        p = os.path.join(out_dir, "presentation.pdf")
        return p if os.path.isfile(p) else None
    if field == "content_map":
        return "layout.json"
    if field == "compliance_checks":
        ra = os.path.join(out_dir, "render_audit.json")
        if os.path.isfile(ra):
            try:
                with open(ra, encoding="utf-8") as fh:
                    return {"render_audit": json.load(fh).get("verdict")}
            except Exception:  # noqa: BLE001
                pass
        return {}
    if field == "exceptions":
        return []
    return None


def parse_set_json(fragment):
    """Parse 'k=<json>' -> (k, value). Falls back to string value."""
    key, sep, raw = fragment.partition("=")
    if not sep or not key.strip():
        raise ValueError("bad --set-json %r (expected k=<json>)" % fragment)
    key = key.strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key, value


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write a contract-complete result.json.")
    ap.add_argument("--case", default=os.path.join(
        os.environ.get("CASE_INPUT_DIR", "/input"), "case.json"))
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("CASE_OUTPUT_DIR", "/app/output"), "result.json"))
    ap.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    ap.add_argument("--set-json", dest="set_json", action="append", default=[],
                    metavar="K=JSON", help="set/override a top-level field")
    ap.add_argument("--exception", dest="exceptions", action="append", default=[],
                    help="append one exception/limitation string")
    args = ap.parse_args(argv)

    case = load_case(args.case)
    case_id = case.get("case_id") or case.get("id") or "unknown"
    fields = contract_fields(case)
    out_dir = os.path.dirname(args.out) or "."
    os.makedirs(out_dir, exist_ok=True)

    # merge over any existing (early-partial) result
    result = {}
    if os.path.isfile(args.out):
        try:
            with open(args.out, encoding="utf-8") as fh:
                result = json.load(fh)
        except Exception:  # noqa: BLE001
            result = {}

    result["case_id"] = case_id
    unfilled = []
    for field in fields:
        if field == "status" or field not in result:
            val = field_default(field, args.status, out_dir)
            if field not in DEFAULT_CONTRACT_FIELDS and val is None \
                    and result.get(field) is None:
                unfilled.append(field)
            result[field] = val
    result["status"] = args.status

    for frag in args.set_json:
        key, value = parse_set_json(frag)
        result[key] = value
    if args.exceptions:
        exc = result.get("exceptions")
        if not isinstance(exc, list):
            exc = []
        exc.extend(args.exceptions)
        result["exceptions"] = exc
    if unfilled:
        result["_unfilled_contract_fields"] = unfilled
    if args.status == "partial" and not result.get("exceptions"):
        result["exceptions"] = ["partial result written early; pipeline not finished"]

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("result_make: case_id=%s status=%s contract_fields=%d -> %s"
          % (case_id, args.status, len(fields), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
