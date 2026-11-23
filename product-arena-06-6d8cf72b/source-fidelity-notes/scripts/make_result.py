#!/usr/bin/env python3
"""make_result.py -- assemble the contracted result.json from authored notes.

The notes file keeps the agent-authored content; this script only:
  1. copies ``result_fields`` from the notes into the exact fields the
     case's ``output_contract`` requires (required keys must exist);
  2. checks declared JSON types against the contract subset it understands
     (string/number/integer/boolean/array/object) and warns on unknown
     schema keywords instead of silently passing them;
  3. merges the anchor_check report and the fidelity receipt into the
     honest run status:
       success  = every required field filled, anchor check pass, fidelity ok
       partial  = anything else deliverable (limits must name the gaps)
       failed   = no readable source at all
  It NEVER deletes authored content and NEVER upgrades status by itself.
"""
import argparse
import json
import os
import sys

JSON_TYPES = {
    "string": str, "number": (int, float), "integer": int,
    "boolean": bool, "array": list, "object": dict,
}


def type_ok(value, schema):
    t = schema.get("type")
    if isinstance(t, list):  # union types
        return any(type_ok(value, dict(schema, type=one)) for one in t)
    if t is None:
        return True
    if t == "number" and isinstance(value, bool):
        return False
    if t == "integer" and isinstance(value, bool):
        return False
    py = JSON_TYPES.get(t)
    if py is None:
        return None  # unknown type -> caller must warn
    return isinstance(value, py)


def check_contract_subset(contract, result, path="$"):
    problems, warnings = [], []
    if not isinstance(contract, dict):
        return problems, warnings
    known = {"type", "required", "properties", "items", "additionalProperties"}
    for key in contract:
        if key not in known and not key.startswith("$") and key not in (
                "title", "description", "enum", "default", "minimum", "maximum",
                "minItems", "maxItems", "minLength", "maxLength", "pattern"):
            warnings.append("unsupported schema keyword %s at %s" % (key, path))
    t = contract.get("type")
    if t and result is not None:
        ok = type_ok(result, contract)
        if ok is False:
            problems.append("type mismatch at %s: want %s" % (path, t))
    if t == "object" and isinstance(result, dict):
        for req in contract.get("required", []):
            if req not in result:
                problems.append("missing required field %s.%s" % (path, req))
        props = contract.get("properties", {})
        for key, sub in props.items():
            if key in result:
                p2, w2 = check_contract_subset(sub, result[key], "%s.%s" % (path, key))
                problems += p2
                warnings += w2
    if t == "array" and isinstance(result, list) and "items" in contract:
        for i, item in enumerate(result):
            p2, w2 = check_contract_subset(contract["items"], item, "%s[%d]" % (path, i))
            problems += p2
            warnings += w2
    if "enum" in contract and result is not None and result not in contract["enum"]:
        problems.append("value at %s not in enum" % path)
    return problems, warnings


def null_paths(node, path="$"):
    out = []
    if node is None:
        out.append(path)
    elif isinstance(node, dict):
        for k, v in node.items():
            out += null_paths(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += null_paths(v, "%s[%d]" % (path, i))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--scan", required=True, help="directory with fidelity.json")
    ap.add_argument("--anchor-report")
    ap.add_argument("--out", required=True, help="output directory, e.g. /app/output")
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    with open(args.notes, encoding="utf-8") as fh:
        notes = json.load(fh)
    with open(os.path.join(args.scan, "fidelity.json"), encoding="utf-8") as fh:
        fidelity = json.load(fh)
    anchor_report = None
    if args.anchor_report and os.path.exists(args.anchor_report):
        with open(args.anchor_report, encoding="utf-8") as fh:
            anchor_report = json.load(fh)

    if fidelity.get("status") == "unreadable":
        result = {
            "case_id": case.get("case_id", "unknown"),
            "status": "failed",
            "failure": fidelity.get("reason"),
            "handover": fidelity.get("handover"),
            "sources": [],
        }
        _write(args.out, result)
        print(json.dumps({"status": "failed"}))
        return 0

    result = {"case_id": case.get("case_id", "unknown")}
    result.update(notes.get("result_fields", {}))

    contract = case.get("output_contract", {})
    problems, warnings = check_contract_subset(contract, result)
    if "case_id" not in result or result["case_id"] != case.get("case_id", result.get("case_id")):
        problems.append("case_id missing or mismatched")

    nulls = null_paths(result)
    unexplained = [p for p in nulls
                   if not notes.get("null_reasons", {}).get(p)]
    limits = list(notes.get("limits", []))
    if fidelity.get("status") == "degraded":
        limits.append("source fidelity degraded: " + json.dumps(
            {"empty_pages": fidelity.get("empty_or_image_pages"),
             "flags": fidelity.get("page_flags")}, ensure_ascii=False))
    for p in unexplained:
        limits.append("null field without reason: " + p)
        problems.append("null without reason at " + p)

    anchor_bad = bool(anchor_report and anchor_report.get("hard_failures"))
    if anchor_bad:
        limits.append("anchor_check hard failures pending repair: %d"
                      % len(anchor_report["hard_failures"]))

    status = "success" if (not problems and not anchor_bad and not unexplained) else "partial"
    result["status"] = status
    result["contract"] = {"problems": problems, "warnings": warnings}
    result["fidelity"] = {"status": fidelity.get("status"),
                          "backend": fidelity.get("backend"),
                          "sha256": fidelity.get("sha256"),
                          "empty_pages": fidelity.get("empty_or_image_pages", [])}
    if anchor_report:
        result["anchor_check"] = {"verdict": anchor_report.get("verdict"),
                                  "items_passed": anchor_report.get("items_passed"),
                                  "needs_review": len(anchor_report.get("needs_review", [])),
                                  "hard_failures": len(anchor_report.get("hard_failures", []))}
    result["sources"] = notes.get("sources", [])
    result["limits"] = limits
    result["uncertainty"] = notes.get("uncertainty", [])
    result["change_records"] = notes.get("change_records", [])
    _write(args.out, result)
    print(json.dumps({"status": status, "problems": len(problems),
                      "warnings": len(warnings)}, ensure_ascii=False))
    return 0


def _write(out_dir, result):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
