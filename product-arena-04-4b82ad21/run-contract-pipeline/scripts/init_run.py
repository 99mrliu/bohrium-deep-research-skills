#!/usr/bin/env python3
"""init_run.py -- initialise a contract-driven writing run.

Reads a case.json (and the task text), creates the working directory, and
writes three artefacts:

  WORK/plan.json             milestone plan, extracted constraints,
                             deliverables, output_contract field names and a
                             next_actions checklist.
  WORK/contract_map.json     recursive, typed parse of every descriptor
                             string in the case's output_contract.
  WORK/skeleton_result.json  a result.json skeleton: case_id filled from the
                             input case, every other field a typed empty
                             placeholder.

DESCRIPTOR PARSING RULES (output_contract values are descriptive strings)
-------------------------------------------------------------------------
Applied recursively, maximum nesting depth 3:

* leading "str"                      -> placeholder "" (empty string)
* leading "int" / "num"              -> placeholder 0
* "object: f1, f2[], f3{}"           -> object; each comma-separated token is
                                        a subfield. A trailing "[]" means
                                        array-of, a trailing "{}" means a
                                        free-form object. Subfields are
                                        parsed recursively (a bare token
                                        defaults to a string field).
* "array of X objects (f1, f2, ...)" -> placeholder [] (empty array); the
                                        parsed item shape is recorded as
                                        "item_skeleton" in contract_map.json.
* "enum: a | b | c"                  -> placeholder = first enum value; all
                                        allowed values recorded as "allowed".
* anything else / unparseable        -> placeholder null plus a
                                        "needs_manual_review" note in
                                        contract_map.json. Individual object
                                        subfields that are not clean
                                        identifiers (e.g. free prose such as
                                        "pass/fail/not_verifiable counts")
                                        get the same treatment: kept as
                                        null-valued keys with a review note,
                                        so downstream tooling treats them as
                                        not_verifiable instead of failing.

Exit codes: 0 ok, 2 usage error.
Pure Python 3 standard library; no hardcoded harness paths.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

MAX_DEPTH = 3

# Milestone plan: (stage name, fraction of the time budget, goal)
MILESTONES = [
    ("read", 0.15, "Read case.json, task.md and all declared material; build the contract map."),
    ("scaffold_evidence", 0.25, "Skeleton result.json, evidence table, citation order, section outline."),
    ("draft", 0.35, "Write the manuscript draft; save editable partials early; checkpoint each milestone."),
    ("audit_assemble", 0.25, "Self-audit vs constraints, assemble result.json, run contract_check, deliver."),
]

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARRAY_OF_RE = re.compile(r"array\s+of\s+(.+?)\s+objects?\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL)


def _note(node, msg):
    node.setdefault("notes", []).append(msg)


def parse_field_token(token, depth):
    """Parse one comma-separated subfield token of an object: descriptor.

    Returns (key, node). A trailing [] means array-of, {} means free-form
    object. Tokens that are not clean identifiers are kept verbatim with a
    needs_manual_review note so checks degrade to not_verifiable.
    """
    token = token.strip()
    if not token:
        return None, None
    suffix = None
    base = token
    if token.endswith("[]"):
        base, suffix = token[:-2].strip(), "[]"
    elif token.endswith("{}"):
        base, suffix = token[:-2].strip(), "{}"
    if not _IDENT_RE.match(base):
        # Free prose inside a field list (e.g. "pass/fail/not_verifiable counts").
        node = {"raw": token, "type": "unknown", "placeholder": None}
        _note(node, "needs_manual_review: subfield token is not a clean identifier; "
                    "treat as descriptive prose, verify by hand")
        return token, node
    if suffix == "[]":
        return base, {"raw": token, "type": "array", "placeholder": [],
                      "item_skeleton": None}
    if suffix == "{}":
        return base, {"raw": token, "type": "object", "placeholder": {},
                      "subfields": None}
    return base, {"raw": token, "type": "str", "placeholder": ""}


def parse_descriptor(desc, depth=0):
    """Parse one output_contract descriptor string into a typed node."""
    node = {"raw": desc}
    if not isinstance(desc, str):
        node.update({"type": "unknown", "placeholder": None})
        _note(node, "needs_manual_review: descriptor is not a string")
        return node
    if depth >= MAX_DEPTH:
        node.update({"type": "unknown", "placeholder": None})
        _note(node, "needs_manual_review: maximum descriptor nesting depth "
                    "(%d) exceeded" % MAX_DEPTH)
        return node
    text = desc.strip()
    lower = text.lower()

    if lower.startswith("enum:"):
        values = [v.strip() for v in text.split(":", 1)[1].split("|") if v.strip()]
        node.update({"type": "enum", "allowed": values,
                     "placeholder": values[0] if values else None})
        if not values:
            _note(node, "needs_manual_review: enum descriptor has no values")
        return node

    if lower.startswith("array of"):
        m = _ARRAY_OF_RE.search(text)
        if m:
            item_desc = m.group(1).strip()
            field_list = m.group(2)
            item_skeleton = {}
            subfields = {}
            for tok in field_list.split(","):
                key, sub = parse_field_token(tok, depth + 1)
                if key is not None:
                    subfields[key] = sub
                    item_skeleton[key] = sub["placeholder"]
            node.update({"type": "array", "item_kind": item_desc,
                         "placeholder": [], "item_skeleton": item_skeleton,
                         "subfields": subfields})
        else:
            node.update({"type": "array", "placeholder": [], "item_skeleton": None})
            _note(node, "needs_manual_review: 'array of' descriptor without a "
                        "parseable item field list")
        return node

    if lower.startswith("object:"):
        field_list = text.split(":", 1)[1]
        subfields = {}
        placeholder = {}
        for tok in field_list.split(","):
            key, sub = parse_field_token(tok, depth + 1)
            if key is not None:
                subfields[key] = sub
                placeholder[key] = sub["placeholder"]
        node.update({"type": "object", "placeholder": placeholder,
                     "subfields": subfields})
        return node

    if lower.startswith("str"):
        node.update({"type": "str", "placeholder": ""})
        return node

    if lower.startswith("int") or lower.startswith("num"):
        node.update({"type": "number", "placeholder": 0})
        return node

    node.update({"type": "unknown", "placeholder": None})
    _note(node, "needs_manual_review: descriptor does not match any known "
                "pattern (str / object: / array of / enum:)")
    return node


def build_contract_map(case, case_path):
    contract = case.get("output_contract") or {}
    fields = {}
    for name, desc in contract.items():
        fields[name] = parse_descriptor(desc)
    return {
        "case_id": case.get("case_id"),
        "parsed_from": os.path.abspath(case_path),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "max_depth": MAX_DEPTH,
        "fields": fields,
    }


def skeleton_from_map(contract_map):
    skeleton = {}
    for name, node in contract_map["fields"].items():
        if name == "case_id":
            skeleton[name] = contract_map.get("case_id")
        else:
            # deep-copy placeholders via JSON round-trip
            skeleton[name] = json.loads(json.dumps(node["placeholder"]))
    return skeleton


def build_plan(case, contract_map):
    constraints = case.get("constraints") or {}
    milestones = [
        {"stage": s, "time_fraction": f, "budget_note": "fraction of the total wall-clock budget",
         "goal": g}
        for s, f, g in MILESTONES
    ]
    next_actions = [
        "Read task.md in full, then every material file declared in case.material.",
        "Review work/contract_map.json; resolve any needs_manual_review notes by hand.",
        "Draft work/open_items.json (list or {changes, open_items, material_gaps}) and keep it updated.",
        "Build an evidence table: one row per claim you may make, with its source quote.",
        "Fix the citation order (first appearance) before drafting prose.",
        "Write an editable partial draft EARLY; checkpoint after each milestone.",
        "Audit the draft against constraints (word limits, citations, required parts, topics).",
        "Run assemble_result.py, then contract_check.py; deliver only what the contract allows.",
    ]
    return {
        "case_id": case.get("case_id"),
        "task_type": case.get("task_type"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "milestones": milestones,
        "constraints": constraints,
        "deliverables": case.get("deliverables") or [],
        "output_contract_fields": list(contract_map["fields"].keys()),
        "budget_policy": {
            "reserve_final_fraction_for_assembly": 0.20,
            "spend_model_requests_on": ["reading sources", "writing prose"],
            "delegate_to_scripts": ["word counts", "citation counts", "contract checks",
                                    "result.json assembly", "checkpoint snapshots"],
            "do_not_rerun": "scripts that already passed on unchanged inputs",
        },
        "next_actions": next_actions,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Initialise a contract-driven writing run.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--task", required=True, help="path to task.md")
    ap.add_argument("--work", required=True, help="working directory to create/use")
    ap.add_argument("--output", required=True, help="final output directory to create/use")
    args = ap.parse_args(argv)

    for p, what in ((args.case, "case.json"), (args.task, "task.md")):
        if not os.path.isfile(p):
            print("ERROR: %s not found: %s" % (what, p), file=sys.stderr)
            return 2

    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR: cannot parse case.json: %s" % exc, file=sys.stderr)
        return 2
    if not isinstance(case.get("output_contract"), dict):
        print("ERROR: case.json has no object-valued output_contract", file=sys.stderr)
        return 2

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    contract_map = build_contract_map(case, args.case)
    skeleton = skeleton_from_map(contract_map)
    plan = build_plan(case, contract_map)

    def dump(name, obj):
        path = os.path.join(args.work, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return path

    p_plan = dump("plan.json", plan)
    p_map = dump("contract_map.json", contract_map)
    p_skel = dump("skeleton_result.json", skeleton)

    review = [name for name, node in contract_map["fields"].items()
              if any("needs_manual_review" in n for n in node.get("notes", []))]
    print("init_run: initialised case '%s'" % case.get("case_id"))
    print("  wrote %s" % p_plan)
    print("  wrote %s" % p_map)
    print("  wrote %s" % p_skel)
    print("  contract fields: %s" % ", ".join(contract_map["fields"].keys()))
    if review:
        print("  WARNING: fields needing manual review: %s" % ", ".join(review))
    print("next: read task.md + material, then start milestone 'read' "
          "(checkpoint it with checkpoint.py --stage read).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
