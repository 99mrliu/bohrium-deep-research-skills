#!/usr/bin/env python3
"""Validate an agent-authored four-construct measurement blueprint."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

from common import (
    OPERATIONS, Report, contains_placeholder, fail_message, load_json,
    normalized_question, scope_source_ids, text_is_blank, vague_phrase,
    validate_scope, write_json,
)

REQUIRED_ITEM_FIELDS = (
    "item_id", "task_intent", "cognitive_operation", "source_scope",
    "answer_invariant", "difficulty_rationale", "license_basis", "rubric_plan",
)
OPERATION_ORDER = (
    "locate_extract", "table_relation_calculation",
    "comparison_boundary", "synthesis_conflict",
)


def skeleton() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for index, operation in enumerate(OPERATION_ORDER, start=1):
        items.append({
            "item_id": "item-%d" % index,
            "task_intent": "<TASK_INTENT_%d>" % index,
            "cognitive_operation": operation,
            "source_scope": [{"source_id": "<SOURCE_ID>", "locator": "<EXACT_LOCATOR>"}],
            "answer_invariant": {
                "required_claims": ["<CLAIM_A>", "<CLAIM_B>"],
                "value_form": "<EXPECTED_ANSWER_STRUCTURE>",
                "acceptance_rule": "<EXACT_AND_BOUNDARY_RULE>",
            },
            "difficulty_rationale": "<DISCRIMINATION_AND_DEMAND_RATIONALE>",
            "license_basis": {
                "basis": "<CASE_LICENSE_BASIS>",
                "source_ids": ["<SOURCE_ID>"],
            },
            "rubric_plan": {
                "0": "<ZERO_CREDIT_WITH_CLAIM_IDS>",
                "1": "<PARTIAL_CREDIT_WITH_CLAIM_IDS>",
                "2": "<FULL_CREDIT_WITH_ALL_CLAIM_IDS>",
            },
        })
    return {
        "schema_version": "1.0",
        "task_intent": "<OVERARCHING_CASE_TASK_INTENT>",
        "items": items,
    }


def _meaningful_text(report: Report, value: Any, path: str, item_id: str = None, minimum: int = 8) -> None:
    if text_is_blank(value) or len(str(value).strip()) < minimum:
        report.error("INSUFFICIENT_TEXT", path, "Provide at least %d non-whitespace characters; a bare label is insufficient." % minimum, item_id)
    vague = vague_phrase(value)
    if vague:
        report.error("VAGUE_CATCH_ALL", path, "Catch-all phrase %r does not define an auditable construct." % vague, item_id)


def audit_blueprint(blueprint: Any, case: Dict[str, Any] = None) -> Dict[str, Any]:
    report = Report("blueprint.py", blueprint)
    if not isinstance(blueprint, dict):
        report.error("BLUEPRINT_TYPE", "$", "Blueprint root must be an object.")
        return report.as_dict({"checked_items": 0, "operation_coverage": []})
    if contains_placeholder(blueprint):
        report.error("UNRESOLVED_PLACEHOLDER", "$", "Placeholders are structure-only and can never validate as scientific content.")
    _meaningful_text(report, blueprint.get("task_intent"), "$.task_intent", minimum=12)
    items = blueprint.get("items")
    if not isinstance(items, list):
        report.error("ITEMS_TYPE", "$.items", "items must be a list.")
        return report.as_dict({"checked_items": 0, "operation_coverage": []})
    if len(items) != 4:
        report.error("ITEM_COUNT", "$.items", "Exactly four blueprint items are required; found %d." % len(items))

    seen_ids = set()
    seen_intents = set()
    operations = []
    valid_claims: Dict[str, List[str]] = {}
    for index, item in enumerate(items):
        path = "$.items[%d]" % index
        if not isinstance(item, dict):
            report.error("ITEM_TYPE", path, "Blueprint item must be an object.")
            continue
        candidate_id = item.get("item_id")
        item_id = candidate_id if isinstance(candidate_id, str) and candidate_id else "index-%d" % index
        for field in REQUIRED_ITEM_FIELDS:
            if field not in item:
                report.error("MISSING_FIELD", path, "Missing required field %s." % field, item_id)
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            report.error("ITEM_ID", path + ".item_id", "item_id must be a non-empty string.", item_id)
        elif candidate_id in seen_ids:
            report.error("DUPLICATE_ITEM_ID", path + ".item_id", "Duplicate item_id %r." % candidate_id, item_id)
        else:
            seen_ids.add(candidate_id)
        _meaningful_text(report, item.get("task_intent"), path + ".task_intent", item_id, minimum=12)
        intent_key = normalized_question(item.get("task_intent", ""))
        if intent_key:
            if intent_key in seen_intents:
                report.error("DUPLICATE_CONSTRUCT", path + ".task_intent", "Two blueprint items use the same normalized task intent.", item_id)
            seen_intents.add(intent_key)
        operation = item.get("cognitive_operation")
        if operation not in OPERATIONS:
            report.error("COGNITIVE_OPERATION", path + ".cognitive_operation", "Use exactly one declared operation: %s." % ", ".join(OPERATION_ORDER), item_id)
        else:
            operations.append(operation)
        validate_scope(report, item.get("source_scope"), path + ".source_scope", item_id)

        invariant = item.get("answer_invariant")
        claims: List[str] = []
        if not isinstance(invariant, dict):
            report.error("ANSWER_INVARIANT", path + ".answer_invariant", "answer_invariant must be an object.", item_id)
        else:
            for field in ("required_claims", "value_form", "acceptance_rule"):
                if field not in invariant:
                    report.error("MISSING_FIELD", path + ".answer_invariant", "Missing %s." % field, item_id)
            raw_claims = invariant.get("required_claims")
            if not isinstance(raw_claims, list) or len(raw_claims) < 2:
                report.error("REQUIRED_CLAIMS", path + ".answer_invariant.required_claims", "Name at least two separately checkable answer claims; one quote is not semantic validation.", item_id)
            elif any(not isinstance(claim, str) or not claim.strip() for claim in raw_claims):
                report.error("REQUIRED_CLAIMS", path + ".answer_invariant.required_claims", "Every claim_id must be a non-empty string.", item_id)
            elif len(set(raw_claims)) != len(raw_claims):
                report.error("REQUIRED_CLAIMS", path + ".answer_invariant.required_claims", "Claim identifiers must be unique within an item.", item_id)
            else:
                claims = raw_claims
                valid_claims[item_id] = claims
            _meaningful_text(report, invariant.get("value_form"), path + ".answer_invariant.value_form", item_id, minimum=6)
            _meaningful_text(report, invariant.get("acceptance_rule"), path + ".answer_invariant.acceptance_rule", item_id, minimum=10)

        _meaningful_text(report, item.get("difficulty_rationale"), path + ".difficulty_rationale", item_id, minimum=12)
        license_basis = item.get("license_basis")
        if not isinstance(license_basis, dict):
            report.error("LICENSE_BASIS", path + ".license_basis", "license_basis must be an object with basis and source_ids.", item_id)
        else:
            _meaningful_text(report, license_basis.get("basis"), path + ".license_basis.basis", item_id, minimum=6)
            source_ids = license_basis.get("source_ids")
            if not isinstance(source_ids, list) or not source_ids or any(not isinstance(value, str) or not value for value in source_ids):
                report.error("LICENSE_SOURCES", path + ".license_basis.source_ids", "List the actual licensed source_ids used by this item.", item_id)
            elif set(source_ids) != scope_source_ids(item.get("source_scope")):
                report.error("LICENSE_SCOPE_MISMATCH", path + ".license_basis.source_ids", "License source_ids must match source_scope source_ids.", item_id)

        rubric_plan = item.get("rubric_plan")
        if not isinstance(rubric_plan, dict) or set(rubric_plan) != {"0", "1", "2"}:
            report.error("RUBRIC_PLAN", path + ".rubric_plan", "Rubric plan must have exactly the string keys 0, 1 and 2.", item_id)
        else:
            for score in ("0", "1", "2"):
                _meaningful_text(report, rubric_plan.get(score), path + ".rubric_plan." + score, item_id, minimum=8)
            full_credit = rubric_plan.get("2", "")
            if isinstance(full_credit, str):
                for claim in claims:
                    if claim not in full_credit:
                        report.error("RUBRIC_CLAIM_GAP", path + ".rubric_plan.2", "Full-credit plan must name required claim_id %r explicitly." % claim, item_id)

    counts = {operation: operations.count(operation) for operation in OPERATION_ORDER}
    for operation in OPERATION_ORDER:
        if counts[operation] != 1:
            report.error("OPERATION_COVERAGE", "$.items", "Operation %s must occur exactly once; found %d." % (operation, counts[operation]))
    if case is not None and isinstance(case, dict) and isinstance(case.get("task_intent"), str):
        if normalized_question(case.get("task_intent")) != normalized_question(blueprint.get("task_intent", "")):
            report.error("TASK_INTENT_MISMATCH", "$.task_intent", "Blueprint task_intent must preserve the explicit task_intent in case.json.")

    return report.as_dict({
        "checked_items": len(items),
        "operation_coverage": {operation: counts[operation] for operation in OPERATION_ORDER},
        "item_ids": list(seen_ids),
        "claim_counts": {item_id: len(claims) for item_id, claims in valid_claims.items()},
        "semantic_validation_scope": "Construct structure and claim/rubric coverage are checked; source meaning still requires reading the actual materials.",
    })


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint", nargs="?", help="Agent-authored blueprint JSON")
    parser.add_argument("--case", help="case.json for explicit task-intent alignment")
    parser.add_argument("--output", help="Audit JSON destination; defaults to stdout")
    parser.add_argument("--skeleton", metavar="PATH", help="Write structure-only placeholders to PATH; they will fail validation")
    args = parser.parse_args(argv)
    try:
        if args.skeleton:
            if args.blueprint or args.case or args.output:
                parser.error("--skeleton cannot be combined with blueprint, --case or --output")
            write_json(args.skeleton, skeleton())
            sys.stdout.write("Wrote structure-only skeleton to %s; validate only after authoring real content.\n" % args.skeleton)
            return 0
        if not args.blueprint:
            parser.error("blueprint is required unless --skeleton is used")
        blueprint = load_json(args.blueprint)
        case = load_json(args.case) if args.case else None
        result = audit_blueprint(blueprint, case)
        if args.output:
            write_json(args.output, result)
        else:
            import json
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        return 2 if result["status"] == "fail" else 0
    except ValueError as exc:
        fail_message(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
