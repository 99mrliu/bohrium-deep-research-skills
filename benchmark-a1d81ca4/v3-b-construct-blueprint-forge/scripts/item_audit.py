#!/usr/bin/env python3
"""Audit source-conditioned items against an authored construct blueprint."""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from common import (
    HEDGE_MARKERS, OPERATIONS, Report, answer_tokens, contains_placeholder,
    content_sha256, fail_message, load_json, normalized_question,
    question_similarity, scope_pairs, scope_source_ids, source_ids_from_case,
    task_tokens, text_is_blank, vague_phrase, write_json,
)

REQUIRED_ITEM_FIELDS = (
    "item_id", "task", "task_intent", "cognitive_operation", "input_material",
    "reference_answer", "rubric", "difficulty", "data_license", "evidence",
    "unique_answer_rationale", "source_scope", "uncertainty", "arithmetic",
)


def _meaningful_text(report: Report, value: Any, path: str, item_id: str, minimum: int = 8) -> None:
    if text_is_blank(value) or len(value.strip()) < minimum:
        report.error("INSUFFICIENT_TEXT", path, "Expected a specific string of at least %d characters." % minimum, item_id)
        return
    vague = vague_phrase(value)
    if vague:
        report.error("VAGUE_CATCH_ALL", path, "Catch-all phrase %r is not an operational criterion." % vague, item_id)


def _numeric_answer(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, dict):
        candidate = value.get("value")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and math.isfinite(float(candidate)):
            return float(candidate)
    return None


def _safe_node(node: ast.AST, bindings: Dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_node(node.body, bindings)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only finite numeric constants are permitted")
        value = float(node.value)
        if not math.isfinite(value) or abs(value) > 1e150:
            raise ValueError("numeric constant is non-finite or too large")
        return value
    if isinstance(node, ast.Name):
        if node.id not in bindings:
            raise ValueError("unbound variable %s" % node.id)
        return bindings[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _safe_node(node.operand, bindings)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _safe_node(node.left, bindings)
        right = _safe_node(node.right, bindings)
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        else:
            if right == 0:
                raise ValueError("division by zero")
            result = left / right
        if not math.isfinite(result):
            raise ValueError("arithmetic result is non-finite")
        return result
    raise ValueError("disallowed syntax %s; only names, numbers, parentheses, unary +/- and binary + - * / are allowed" % type(node).__name__)


def safe_arithmetic(expression: str, bindings: Dict[str, Any]) -> float:
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 500:
        raise ValueError("expression must be a non-empty string of at most 500 characters")
    if not isinstance(bindings, dict):
        raise ValueError("bindings must be an object")
    numeric_bindings: Dict[str, float] = {}
    for name, value in bindings.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("invalid binding name %r" % name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("binding %s must be a finite number" % name)
        numeric_bindings[name] = float(value)
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("expression exceeds the 64-node safety limit")
    value = _safe_node(tree, numeric_bindings)
    if not math.isfinite(value):
        raise ValueError("arithmetic result is non-finite")
    return value


def _source_number_set(item: Dict[str, Any]) -> Set[float]:
    texts: List[str] = []
    for field in ("input_material", "evidence"):
        entries = item.get(field, [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    for key in ("content", "quote"):
                        if isinstance(entry.get(key), str):
                            texts.append(entry[key])
    number_pattern = r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    numbers: Set[float] = set()
    for token in re.findall(number_pattern, "\n".join(texts)):
        try:
            value = float(token)
            if math.isfinite(value):
                numbers.add(value)
        except ValueError:
            pass
    return numbers


def _audit_arithmetic(report: Report, item: Dict[str, Any], path: str, item_id: str) -> None:
    arithmetic = item.get("arithmetic")
    if arithmetic is None:
        return
    if not isinstance(arithmetic, dict):
        report.error("ARITHMETIC_TYPE", path, "arithmetic must be null or an object with expression, bindings and expected.", item_id)
        return
    required = {"expression", "bindings", "expected"}
    if not required.issubset(arithmetic):
        report.error("ARITHMETIC_FIELDS", path, "Arithmetic requires expression, bindings and expected.", item_id)
        return
    try:
        computed = safe_arithmetic(arithmetic["expression"], arithmetic["bindings"])
    except (ValueError, SyntaxError, TypeError, OverflowError) as exc:
        report.error("ARITHMETIC_UNSAFE_OR_INVALID", path + ".expression", str(exc), item_id)
        return
    expected = arithmetic.get("expected")
    if isinstance(expected, bool) or not isinstance(expected, (int, float)) or not math.isfinite(float(expected)):
        report.error("ARITHMETIC_EXPECTED", path + ".expected", "expected must be a finite independently calculated result.", item_id)
    else:
        tolerance = arithmetic.get("evaluation_tolerance", 1e-9)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
            report.error("ARITHMETIC_TOLERANCE", path + ".evaluation_tolerance", "evaluation_tolerance must be a non-negative number.", item_id)
        elif not math.isclose(computed, float(expected), rel_tol=1e-12, abs_tol=float(tolerance)):
            report.error("ARITHMETIC_RECOMPUTE_MISMATCH", path + ".expected", "Safe AST recomputation produced %.17g, not declared expected %.17g." % (computed, float(expected)), item_id)
    reference_value = _numeric_answer(item.get("reference_answer"))
    if reference_value is None:
        report.error("ARITHMETIC_REFERENCE_MISSING", "$.reference_answer", "Arithmetic items need a numeric reference answer or a numeric reference_answer.value.", item_id)
    else:
        tolerance = arithmetic.get("answer_tolerance", 1e-9)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
            report.error("ARITHMETIC_TOLERANCE", path + ".answer_tolerance", "answer_tolerance must be a non-negative number.", item_id)
        elif not math.isclose(computed, reference_value, rel_tol=0.0, abs_tol=float(tolerance)):
            report.error("ARITHMETIC_REFERENCE_MISMATCH", "$.reference_answer", "Reference numeric value %.17g differs from recomputed %.17g beyond tolerance %s." % (reference_value, computed, tolerance), item_id)
    source_numbers = _source_number_set(item)
    for name, binding in arithmetic.get("bindings", {}).items() if isinstance(arithmetic.get("bindings"), dict) else []:
        if isinstance(binding, (int, float)) and not isinstance(binding, bool):
            if not any(math.isclose(float(binding), candidate, rel_tol=0.0, abs_tol=1e-12) for candidate in source_numbers):
                report.error("ARITHMETIC_BINDING_UNSOURCED", path + ".bindings." + name, "Binding %r does not occur as a numeric value in declared input material or evidence." % binding, item_id)


def _uncertainty_statements(value: Any) -> List[str]:
    statements: List[str] = []
    if not isinstance(value, list):
        return statements
    for entry in value:
        if isinstance(entry, str):
            statements.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("statement"), str):
            statements.append(entry["statement"])
    return statements


def _audit_uncertainty(report: Report, item: Dict[str, Any], item_id: str) -> None:
    uncertainty = item.get("uncertainty")
    if not isinstance(uncertainty, list):
        report.error("UNCERTAINTY_TYPE", "$.uncertainty", "uncertainty must be a list (empty when there is no residual uncertainty).", item_id)
        return
    for index, entry in enumerate(uncertainty):
        if not isinstance(entry, (str, dict)):
            report.error("UNCERTAINTY_ENTRY", "$.uncertainty[%d]" % index, "Use a statement string or an object with statement/status.", item_id)
    answer = item.get("reference_answer")
    answer_text = json.dumps(answer, ensure_ascii=False, sort_keys=True).casefold()
    hedged = any(marker in answer_text for marker in HEDGE_MARKERS)
    answer_token_set = answer_tokens(answer)
    for index, statement in enumerate(_uncertainty_statements(uncertainty)):
        statement_tokens = answer_tokens(statement)
        normalized_statement = normalized_question(statement)
        normalized_answer = normalized_question(answer)
        repeated_verbatim = len(normalized_statement) >= 8 and normalized_statement in normalized_answer
        repeated_by_tokens = len(statement_tokens) >= 2 and statement_tokens.issubset(answer_token_set)
        if (repeated_verbatim or repeated_by_tokens) and not hedged:
            report.error(
                "UNCERTAINTY_ASSERTED_AS_FACT", "$.reference_answer",
                "Residual uncertainty %d is restated as an unhedged reference answer; preserve an explicit unknown/uncertain status or resolve it from sources." % index,
                item_id,
            )


def _audit_leakage(report: Report, item: Dict[str, Any], item_id: str) -> None:
    task = item.get("task")
    if not isinstance(task, str):
        return
    informative_answer_tokens = answer_tokens(item.get("reference_answer"))
    leaked = sorted(informative_answer_tokens & task_tokens(task))
    if leaked:
        report.error(
            "ANSWER_LEAKAGE", "$.task",
            "Task repeats non-trivial answer-value token(s): %s. Numbers, field names, stopwords and units alone are not treated as leaks." % ", ".join(leaked[:12]),
            item_id,
        )


def audit_items(bank: Any, blueprint: Any, case: Dict[str, Any] = None) -> Dict[str, Any]:
    report = Report("item_audit.py", bank)
    blueprint_items: Dict[str, Dict[str, Any]] = {}
    if isinstance(blueprint, dict) and isinstance(blueprint.get("items"), list):
        for entry in blueprint["items"]:
            if isinstance(entry, dict) and isinstance(entry.get("item_id"), str):
                blueprint_items[entry["item_id"]] = entry
    else:
        report.error("BLUEPRINT_INVALID", "$.blueprint", "A parsed blueprint with an items list is required for alignment.")

    if not isinstance(bank, dict):
        report.error("BANK_TYPE", "$", "Item bank root must be an object.")
        return report.as_dict({"checked_items": 0, "blueprint_sha256": content_sha256(blueprint)})
    if contains_placeholder(bank):
        report.error("UNRESOLVED_PLACEHOLDER", "$", "The item bank contains unresolved placeholders.")
    items = bank.get("items")
    if not isinstance(items, list):
        report.error("ITEMS_TYPE", "$.items", "items must be a list.")
        return report.as_dict({"checked_items": 0, "blueprint_sha256": content_sha256(blueprint)})
    if len(items) != 4:
        report.error("ITEM_COUNT", "$.items", "Exactly four items are required for a complete bank; found %d." % len(items))
    declared_case_sources = source_ids_from_case(case) if isinstance(case, dict) else set()
    seen_ids = set()
    normalized_tasks: Dict[str, str] = {}
    operations: List[str] = []
    construct_signatures = set()

    for index, item in enumerate(items):
        path = "$.items[%d]" % index
        if not isinstance(item, dict):
            report.error("ITEM_TYPE", path, "Item must be an object.")
            continue
        candidate_id = item.get("item_id")
        item_id = candidate_id if isinstance(candidate_id, str) and candidate_id else "index-%d" % index
        prefix = path
        for field in REQUIRED_ITEM_FIELDS:
            if field not in item:
                report.error("MISSING_FIELD", prefix, "Missing required field %s." % field, item_id)
        if not isinstance(candidate_id, str) or not candidate_id:
            report.error("ITEM_ID", prefix + ".item_id", "item_id must be a non-empty string.", item_id)
        elif candidate_id in seen_ids:
            report.error("DUPLICATE_ITEM_ID", prefix + ".item_id", "Duplicate item_id %r." % candidate_id, item_id)
        else:
            seen_ids.add(candidate_id)
        planned = blueprint_items.get(item_id)
        if planned is None:
            report.error("BLUEPRINT_ITEM_MISSING", prefix + ".item_id", "No blueprint item has this item_id.", item_id)
            planned = {}
        _meaningful_text(report, item.get("task"), prefix + ".task", item_id, minimum=12)
        reference = item.get("reference_answer")
        if reference is None or reference == "" or reference == [] or reference == {}:
            report.error("REFERENCE_ANSWER_EMPTY", prefix + ".reference_answer", "A source-derived reference_answer is required.", item_id)
        _meaningful_text(report, item.get("unique_answer_rationale"), prefix + ".unique_answer_rationale", item_id, minimum=12)
        _audit_leakage(report, item, item_id)
        _audit_uncertainty(report, item, item_id)

        task_key = normalized_question(item.get("task", ""))
        if task_key:
            if task_key in normalized_tasks:
                report.error("DUPLICATE_QUESTION", prefix + ".task", "Normalized question duplicates item %s." % normalized_tasks[task_key], item_id)
            else:
                normalized_tasks[task_key] = item_id
        operation = item.get("cognitive_operation")
        if operation not in OPERATIONS:
            report.error("COGNITIVE_OPERATION", prefix + ".cognitive_operation", "Unknown cognitive operation.", item_id)
        else:
            operations.append(operation)
        if operation != planned.get("cognitive_operation"):
            report.error("CONSTRUCT_OPERATION_MISMATCH", prefix + ".cognitive_operation", "Operation does not match the blueprint item.", item_id)
        if normalized_question(item.get("task_intent", "")) != normalized_question(planned.get("task_intent", "")):
            report.error("CONSTRUCT_INTENT_MISMATCH", prefix + ".task_intent", "task_intent must preserve the blueprint item's task intent.", item_id)
        own_scope = scope_pairs(item.get("source_scope"))
        planned_scope = scope_pairs(planned.get("source_scope"))
        if not own_scope:
            report.error("SOURCE_SCOPE_REQUIRED", prefix + ".source_scope", "Declare concrete {source_id, locator} source_scope entries copied from the blueprint.", item_id)
        if own_scope != planned_scope:
            report.error("CONSTRUCT_SCOPE_MISMATCH", prefix + ".source_scope", "Item source_scope must match the blueprint scope exactly.", item_id)
        if declared_case_sources:
            unknown = scope_source_ids(item.get("source_scope")) - declared_case_sources
            if unknown:
                report.error("UNDECLARED_CASE_SOURCE", prefix + ".source_scope", "Sources absent from case.json: %s." % ", ".join(sorted(unknown)), item_id)

        required_claims: List[str] = []
        invariant = planned.get("answer_invariant", {})
        if isinstance(invariant, dict) and isinstance(invariant.get("required_claims"), list):
            required_claims = [claim for claim in invariant["required_claims"] if isinstance(claim, str)]
        signature = (operation, normalized_question(item.get("task_intent", "")), tuple(sorted(required_claims)))
        if signature in construct_signatures:
            report.error("DUPLICATE_CONSTRUCT", prefix, "Another item uses the same operation, normalized intent and answer-claim construct.", item_id)
        construct_signatures.add(signature)

        inputs = item.get("input_material")
        input_pairs = set()
        if not isinstance(inputs, list) or not inputs:
            report.error("INPUT_MATERIAL_REQUIRED", prefix + ".input_material", "Provide actual source-conditioned input_material entries.", item_id)
        else:
            for input_index, entry in enumerate(inputs):
                input_path = "%s.input_material[%d]" % (prefix, input_index)
                if not isinstance(entry, dict):
                    report.error("INPUT_MATERIAL_ENTRY", input_path, "Each input material must be an object.", item_id)
                    continue
                for field in ("source_id", "locator", "content"):
                    if text_is_blank(entry.get(field)):
                        report.error("INPUT_MATERIAL_FIELD", input_path, "Missing non-empty %s." % field, item_id)
                pair = (str(entry.get("source_id", "")), str(entry.get("locator", "")))
                input_pairs.add(pair)
                if own_scope and pair not in own_scope:
                    report.error("INPUT_OUTSIDE_SCOPE", input_path, "Input material was not declared in source_scope.", item_id)
            missing_inputs = planned_scope - input_pairs
            if missing_inputs:
                report.error("INPUT_SCOPE_INCOMPLETE", prefix + ".input_material", "Blueprint scope is not fully supplied to the solver: %r." % sorted(missing_inputs), item_id)

        evidence = item.get("evidence")
        supported_claims = set()
        evidence_keys = set()
        if not isinstance(evidence, list) or len(evidence) < 2:
            report.error("EVIDENCE_INDEPENDENCE", prefix + ".evidence", "Provide at least two distinct evidence spans/records; one passing quote is not semantic correctness validation.", item_id)
        elif not isinstance(evidence, list):
            evidence = []
        if isinstance(evidence, list):
            for evidence_index, entry in enumerate(evidence):
                evidence_path = "%s.evidence[%d]" % (prefix, evidence_index)
                if not isinstance(entry, dict):
                    report.error("EVIDENCE_ENTRY", evidence_path, "Each evidence entry must be an object.", item_id)
                    continue
                for field in ("source_id", "locator", "quote", "supports"):
                    if field not in entry:
                        report.error("EVIDENCE_FIELD", evidence_path, "Missing %s." % field, item_id)
                if text_is_blank(entry.get("quote")):
                    report.error("EVIDENCE_QUOTE", evidence_path + ".quote", "Evidence quote must be a non-empty source span.", item_id)
                pair = (str(entry.get("source_id", "")), str(entry.get("locator", "")))
                if own_scope and pair not in own_scope:
                    report.error("EVIDENCE_OUTSIDE_SCOPE", evidence_path, "Evidence source/locator was not declared in source_scope.", item_id)
                if input_pairs and pair not in input_pairs:
                    report.error("EVIDENCE_NOT_IN_INPUT", evidence_path, "Evidence source/locator must be present in solver input_material.", item_id)
                supports = entry.get("supports")
                if not isinstance(supports, list) or not supports or any(not isinstance(claim, str) or not claim for claim in supports):
                    report.error("EVIDENCE_CLAIMS", evidence_path + ".supports", "supports must list blueprint claim_ids touched by this evidence.", item_id)
                else:
                    unknown = set(supports) - set(required_claims)
                    if unknown:
                        report.error("EVIDENCE_UNKNOWN_CLAIM", evidence_path + ".supports", "Unknown blueprint claim_ids: %s." % ", ".join(sorted(unknown)), item_id)
                    supported_claims.update(supports)
                evidence_key = (pair, str(entry.get("quote", "")))
                if evidence_key in evidence_keys:
                    report.error("EVIDENCE_DUPLICATE", evidence_path, "Duplicate evidence quote/locator does not add independent claim coverage.", item_id)
                evidence_keys.add(evidence_key)
        missing_claims = set(required_claims) - supported_claims
        if missing_claims:
            report.error("EVIDENCE_CLAIM_GAP", prefix + ".evidence", "No evidence supports required claim_ids: %s." % ", ".join(sorted(missing_claims)), item_id)

        rubric = item.get("rubric")
        if not isinstance(rubric, dict) or set(rubric) != {"0", "1", "2"}:
            report.error("RUBRIC_LEVELS", prefix + ".rubric", "Rubric must contain exactly keys 0, 1 and 2.", item_id)
        else:
            normalized_rubric = set()
            for score in ("0", "1", "2"):
                _meaningful_text(report, rubric.get(score), prefix + ".rubric." + score, item_id, minimum=8)
                normalized_rubric.add(normalized_question(rubric.get(score, "")))
            if len(normalized_rubric) != 3:
                report.error("RUBRIC_COLLAPSE", prefix + ".rubric", "The 0/1/2 criteria must not collapse to the same normalized text.", item_id)
            full_credit = rubric.get("2", "")
            if isinstance(full_credit, str):
                for claim in required_claims:
                    if claim not in full_credit:
                        report.error("RUBRIC_REFERENCE_GAP", prefix + ".rubric.2", "Full credit must consistently name reference claim_id %r." % claim, item_id)
            partial = rubric.get("1", "")
            if isinstance(partial, str) and not any(marker in partial.casefold() for marker in ("partial", "only", "one", "部分", "仅", "一项", "其一")):
                report.error("RUBRIC_PARTIAL_UNDEFINED", prefix + ".rubric.1", "Score 1 must define a genuinely partial subset, not repeat full or zero credit.", item_id)

        difficulty = item.get("difficulty")
        if isinstance(difficulty, str):
            if difficulty not in {"easy", "medium", "hard"}:
                report.error("DIFFICULTY", prefix + ".difficulty", "String difficulty must be easy, medium or hard.", item_id)
        elif isinstance(difficulty, dict):
            if difficulty.get("level") not in {"easy", "medium", "hard"}:
                report.error("DIFFICULTY", prefix + ".difficulty.level", "Difficulty level must be easy, medium or hard.", item_id)
            _meaningful_text(report, difficulty.get("rationale"), prefix + ".difficulty.rationale", item_id, minimum=12)
            if normalized_question(difficulty.get("rationale", "")) != normalized_question(planned.get("difficulty_rationale", "")):
                report.error("DIFFICULTY_ALIGNMENT", prefix + ".difficulty.rationale", "Object-form difficulty rationale must match the blueprint rationale.", item_id)
        else:
            report.error("DIFFICULTY", prefix + ".difficulty", "Difficulty must be a level string or {level, rationale} object.", item_id)

        data_license = item.get("data_license")
        if not isinstance(data_license, dict):
            report.error("DATA_LICENSE", prefix + ".data_license", "data_license must state basis and source_ids.", item_id)
        else:
            _meaningful_text(report, data_license.get("basis"), prefix + ".data_license.basis", item_id, minimum=6)
            if not isinstance(data_license.get("source_ids"), list) or set(data_license.get("source_ids", [])) != scope_source_ids(item.get("source_scope")):
                report.error("DATA_LICENSE_SCOPE", prefix + ".data_license.source_ids", "License source_ids must match declared source_scope.", item_id)
            planned_license = planned.get("license_basis", {})
            if isinstance(planned_license, dict) and normalized_question(data_license.get("basis", "")) != normalized_question(planned_license.get("basis", "")):
                report.error("LICENSE_ALIGNMENT", prefix + ".data_license.basis", "Item license basis must match the blueprint license basis.", item_id)
        _audit_arithmetic(report, item, prefix + ".arithmetic", item_id)

    task_entries = list(normalized_tasks.items())
    for left_index, (left_key, left_id) in enumerate(task_entries):
        for right_key, right_id in task_entries[left_index + 1:]:
            if left_key == right_key:
                continue
            similarity = question_similarity(left_key, right_key)
            if similarity >= 0.92:
                report.error("NEAR_DUPLICATE_QUESTION", "$.items", "Questions %s and %s have normalized 5-gram similarity %.3f; differentiate the construct or stimulus." % (left_id, right_id, similarity), right_id)
    operation_counts = {operation: operations.count(operation) for operation in sorted(OPERATIONS)}
    for operation, count in operation_counts.items():
        if count != 1:
            report.error("OPERATION_COVERAGE", "$.items", "Operation %s must occur exactly once; found %d." % (operation, count))
    if blueprint_items:
        missing_blueprint_items = set(blueprint_items) - seen_ids
        if missing_blueprint_items:
            report.error("BLUEPRINT_ITEMS_UNIMPLEMENTED", "$.items", "Blueprint item_ids missing from bank: %s." % ", ".join(sorted(missing_blueprint_items)))
    report.warning(
        "MANUAL_SOURCE_REVIEW_REQUIRED", "$",
        "Passing structural/claim/arithmetic audits does not prove scientific semantic correctness; independently read the material, input excerpts, answer and rubric as a whole.",
    )
    return report.as_dict({
        "checked_items": len(items),
        "blueprint_sha256": content_sha256(blueprint),
        "operation_coverage": operation_counts,
        "semantic_validation_scope": "No answer is accepted merely because a quote exists; claim coverage, complete stimuli, construct boundaries, rubric levels, arithmetic and manual source review remain distinct requirements.",
    })


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("item_bank", help="Agent-authored item_bank.json")
    parser.add_argument("--blueprint", required=True, help="Corresponding authored blueprint.json")
    parser.add_argument("--case", help="case.json to constrain declared source_ids")
    parser.add_argument("--output", help="Audit JSON destination; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        bank = load_json(args.item_bank)
        blueprint = load_json(args.blueprint)
        case = load_json(args.case) if args.case else None
        result = audit_items(bank, blueprint, case)
        if args.output:
            write_json(args.output, result)
        else:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        return 2 if result["status"] == "fail" else 0
    except ValueError as exc:
        fail_message(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
