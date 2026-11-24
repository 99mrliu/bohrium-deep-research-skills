#!/usr/bin/env python3
"""result.py - result.json skeleton generation and validation against the
case's real output_contract.

Subcommands
-----------
result-skeleton   Read the case file (--case, e.g. /input/case.json), mirror
                  its output_contract (field names, nesting, declared types)
                  into a result skeleton, and prefill what can be mapped from
                  real pipeline artifacts (--artifacts dir) through an alias
                  table. Fields that cannot be mapped are set to null and
                  recorded in "notes". Nothing is fabricated.
validate-result   Validate a filled result.json: case_id must match the case,
                  every output_contract field must be present, non-null values
                  must match the declared type, null values must be explained
                  in "notes", and status must be one of
                  success / partial / blocked.

Python 3 standard library only. Deterministic output.
"""
import argparse
import json
import os
import sys

# Alias table: contract field name (lowercased) -> artifact file in --artifacts.
TEXT_ALIASES = {
    "polished.md": {
        "polished_text", "polished", "final_text", "revised_text",
        "edited_text", "polished_manuscript", "polished_md",
    },
    "terminology-report.md": {
        "report_markdown", "markdown_report", "terminology_report_md",
        "consistency_report_md", "report_md",
    },
}
JSON_ALIASES = {
    "changes.json": {
        "changes", "change_log", "change_records", "edits", "revision_log",
        "modifications", "modification_log", "edit_log",
    },
    "termbase.json": {
        "glossary", "termbase", "term_base", "term_table", "locked_termbase",
        "terminology",
    },
    "term-lint.json": {
        "consistency_report", "terminology_report", "term_lint", "lint_report",
        "consistency", "term_lint_report",
    },
    "audit.json": {"audit", "audit_log", "audit_json", "audit_record"},
}
STATUS_KEYS = {"status"}
COUNT_KEYS = {"finding_count", "findings_count", "num_findings",
              "error_count", "lint_finding_count"}
UNCERTAINTY_KEYS = {"uncertainty", "limitations", "caveats"}

TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}
STATUS_VALUES = {"success", "partial", "blocked"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def contract_type(spec):
    """Return (type_name, nested_spec_or_None) for one contract field spec."""
    if isinstance(spec, str):
        return spec.rstrip("?"), None
    if isinstance(spec, dict):
        if "type" in spec:
            t = spec["type"]
            if t == "object" and "properties" in spec:
                return "object", spec["properties"]
            return t, None
        return "object", spec  # plain nested field->type mapping
    return "string", None


def lint_counts(artifacts):
    path = os.path.join(artifacts, "term-lint.json")
    if os.path.exists(path):
        doc = load_json(path)
        return doc.get("summary", {}).get("errors", 0), len(doc.get("findings", []))
    return None, None


def fill_value(key, tname, nested, case, artifacts, notes, path=""):
    k = key.lower()
    full = (path + "." + k) if path else k

    if nested is not None:
        val = {}
        for sub_key, sub_spec in nested.items():
            st, sn = contract_type(sub_spec)
            val[sub_key] = fill_value(sub_key, st, sn, case, artifacts, notes, full)
        return val

    if k in ("case_id", "id", "caseid"):
        return case.get("case_id")
    if k in STATUS_KEYS:
        errors, _ = lint_counts(artifacts)
        if errors is None:
            notes.append("%s: no term-lint artifact; status left for the agent" % full)
            return None
        return "success" if errors == 0 else "partial"
    if k in COUNT_KEYS:
        _, n = lint_counts(artifacts)
        if n is None:
            notes.append("%s: no term-lint artifact to count findings from" % full)
            return None
        return n
    if k in UNCERTAINTY_KEYS:
        notes.append("%s: uncertainty must be written by the agent, not fabricated" % full)
        return None

    for fname, keys in TEXT_ALIASES.items():
        if k in keys:
            fpath = os.path.join(artifacts, fname)
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as fh:
                    return fh.read()
            notes.append("%s: alias maps to %s but the artifact is missing" % (full, fname))
            return None
    for fname, keys in JSON_ALIASES.items():
        if k in keys:
            fpath = os.path.join(artifacts, fname)
            if os.path.exists(fpath):
                data = load_json(fpath)
                if tname == "array" and isinstance(data, dict):
                    for wrap in ("changes", "edits", "items", "records"):
                        if isinstance(data.get(wrap), list):
                            return data[wrap]
                return data
            notes.append("%s: alias maps to %s but the artifact is missing" % (full, fname))
            return None

    notes.append("%s: no artifact mapping for declared type %r; left null" % (full, tname))
    return None


def cmd_skeleton(args):
    case = load_json(args.case)
    contract = case.get("output_contract") or {}
    if not isinstance(contract, dict) or not contract:
        print("result-skeleton: case has no usable output_contract", file=sys.stderr)
        return 1
    notes = []
    result = {"case_id": case.get("case_id")}
    for key, spec in contract.items():
        tname, nested = contract_type(spec)
        result[key] = fill_value(key, tname, nested, case, args.artifacts, notes)
    # honest-delivery envelope required by the Harbor contract
    materials = case.get("materials") or {}
    sources = []
    for key in sorted(materials):
        if key.endswith("_file") or key == "source_file":
            sources.append("%s (case material: %s)" % (materials[key], key))
    if materials.get("glossary"):
        sources.append("case.json materials.glossary (case-provided term glossary)")
    result.setdefault("sources", sources)
    if result.get("status") not in STATUS_VALUES:
        result["status"] = result.get("status") or "partial"
        notes.append("status: defaulted to 'partial' until the agent confirms completion")
    result["notes"] = notes
    write_json(args.result, result)
    print("result-skeleton: %d contract fields mirrored (%d prefilled, %d null+noted) -> %s"
          % (len(contract),
             sum(1 for k in contract if result.get(k) is not None),
             sum(1 for k in contract if result.get(k) is None),
             args.result))
    return 0


def check_type(value, tname):
    py = TYPE_MAP.get(tname)
    if py is None:
        return True  # unknown declared type: cannot check, accept
    if tname == "integer" and isinstance(value, bool):
        return False
    if tname == "number" and isinstance(value, bool):
        return False
    return isinstance(value, py)


def validate_fields(contract, result, notes_text, errors, path=""):
    for key, spec in contract.items():
        tname, nested = contract_type(spec)
        full = (path + "." + key) if path else key
        if key not in result:
            errors.append("missing required field: %s" % full)
            continue
        value = result[key]
        if value is None:
            if full not in notes_text and key not in notes_text:
                errors.append("field %s is null but not explained in notes" % full)
            continue
        if not check_type(value, tname):
            errors.append("field %s: expected type %s, got %s"
                          % (full, tname, type(value).__name__))
            continue
        if nested is not None and isinstance(value, dict):
            validate_fields(nested, value, notes_text, errors, full)


def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    contract = case.get("output_contract") or {}
    errors = []

    if result.get("case_id") != case.get("case_id"):
        errors.append("case_id mismatch: result has %r, case declares %r"
                      % (result.get("case_id"), case.get("case_id")))
    notes_text = "\n".join(str(n) for n in result.get("notes", []))
    validate_fields(contract, result, notes_text, errors)

    status = result.get("status")
    if status not in STATUS_VALUES:
        errors.append("status must be one of success/partial/blocked, got %r" % status)
    if "sources" not in result or not isinstance(result.get("sources"), list):
        errors.append("sources must be present as a list")
    if "uncertainty" in contract and result.get("uncertainty") is None \
            and "uncertainty" not in notes_text:
        errors.append("uncertainty is null but not explained in notes")
    if status == "blocked":
        for key in contract:
            tname, _ = contract_type(contract[key])
            if tname == "string" and key in ("polished_text", "polished") \
                    and result.get(key):
                errors.append("status is blocked but polished text was produced; "
                              "blocked runs must not fabricate body text")

    report = {
        "tool": "result.py validate-result",
        "case_id": case.get("case_id"),
        "valid": not errors,
        "errors": errors,
        "checked_fields": sorted(contract.keys()),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="result.py",
        description="Generate and validate result.json against the case "
                    "output_contract.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("result-skeleton",
                       help="mirror output_contract into a prefilled skeleton")
    p.add_argument("--case", required=True, help="case.json path")
    p.add_argument("--artifacts", default=".",
                   help="directory containing pipeline artifacts for prefill")
    p.add_argument("--result", required=True, help="skeleton output path")
    p.set_defaults(fn=cmd_skeleton)

    p = sub.add_parser("validate-result", help="validate a filled result.json")
    p.add_argument("--case", required=True, help="case.json path")
    p.add_argument("--result", required=True, help="result.json to validate")
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
