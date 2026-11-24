#!/usr/bin/env python3
"""contract_checklist.py — compile case.json's output_contract into checklist.json.

Runtime-driven: fields are read from case.json at run time, never hardcoded.
Every contract field becomes one checklist entry the agent must later fill via
a result part file (<field>.md or <field>.json in the result_parts dir).

Exit codes: 0 = checklist written; 2 = case.json unreadable / contract missing.
"""
import argparse
import json
import os
import sys

# Hints are advisory only; the authoritative rule for every field is
# references/output_contract.md. Unknown fields get a generic hint.
FIELD_HINTS = {
    "edited_chapters": "object mapping chapter name -> path of the edited chapter relative to the output dir",
    "change_record": "markdown or JSON log of every applied edit (what / where / why / acceptance)",
    "consistency_report": "cross-chapter consistency findings: terminology, references, units, numbering",
    "uncertainty": "explicit low-confidence items, unresolved questions, unverifiable claims",
    "deliverable": "main deliverable markdown the case asks for",
    "evidence": "evidence backing the edits or claims (quotes, sources, checks)",
    "sources": "list of input materials actually used",
}
GENERIC_HINT = "contract-declared field; fill per references/output_contract.md (null + problem if impossible)"

PART_CONVENTION = (
    "for each field write exactly one of <field>.md (text) or <field>.json "
    "(structured value) into the result_parts dir; reserved names: "
    "_meta.json, artifacts.json, sources.json"
)


def atomic_write_json(path, obj):
    """Write JSON atomically: temp file in same dir, then os.replace."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="Compile case.json output_contract into a field checklist.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--out", required=True, help="path to write checklist.json")
    ap.add_argument("--note", default=None, help="optional note copied into the checklist (e.g. synthetic marker)")
    args = ap.parse_args()

    try:
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: cannot read/parse case.json %s: %s" % (args.case, e), file=sys.stderr)
        return 2

    contract = case.get("output_contract")
    fields = contract.get("fields") if isinstance(contract, dict) else None
    if not isinstance(fields, list) or not fields or not all(isinstance(x, str) for x in fields):
        print("ERROR: case.json must contain output_contract.fields as a non-empty list of strings",
              file=sys.stderr)
        return 2

    checklist = {
        "case_id": case.get("case_id"),
        "task": case.get("task"),
        "generated_by": "contract_checklist.py",
        "n_fields": len(fields),
        "part_file_convention": PART_CONVENTION,
        "fields": [
            {
                "field": name,
                "required": True,
                "status": "pending",
                "hint": FIELD_HINTS.get(name, GENERIC_HINT),
            }
            for name in fields
        ],
    }
    if args.note:
        checklist["note"] = args.note

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    atomic_write_json(args.out, checklist)
    print("checklist: %d contract fields -> %s" % (len(fields), args.out))
    for name in fields:
        print("  - %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
