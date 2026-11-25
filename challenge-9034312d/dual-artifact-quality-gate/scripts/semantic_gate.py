#!/usr/bin/env python3
"""Reconcile independent expectations and observations; structural QC only.

Scientific correctness is never inferred from these comparisons. Required agent/human
source and visual review records are audited separately.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REQUIRED_GATES = [
    "coverage", "source_support", "direction_marker_semantics", "numbering_order",
    "legend_style", "chart_data_values", "editable_layers", "export_validity",
    "result_contract", "source_preserving_edit_diff",
]
OBSERVATION_GATES = set(REQUIRED_GATES) - {"export_validity", "result_contract", "source_preserving_edit_diff"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def lookup(record: Any, path: str) -> tuple[bool, Any]:
    """Longest-key lookup permits filenames containing dots in dotted paths."""
    segments = path.split(".") if path else []
    current = record
    index = 0
    while index < len(segments):
        if isinstance(current, dict):
            found = False
            for end in range(len(segments), index, -1):
                key = ".".join(segments[index:end])
                if key in current:
                    current = current[key]
                    index = end
                    found = True
                    break
            if not found:
                return False, None
        elif isinstance(current, list):
            try:
                item_index = int(segments[index])
                current = current[item_index]
            except (ValueError, IndexError):
                return False, None
            index += 1
        else:
            return False, None
    return True, current


def frozen(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare(op: str, observed: Any, expected: Any, tolerance: float = 1e-9) -> tuple[bool, str]:
    try:
        if op == "exists":
            return observed is not None, "value exists" if observed is not None else "value is null"
        if op == "eq":
            if isinstance(observed, bool) or isinstance(expected, bool):
                return type(observed) is type(expected) and observed == expected, "strict equality"
            return observed == expected, "equality"
        if op == "neq":
            return observed != expected, "inequality"
        if op == "contains":
            return expected in observed, "membership/substring"
        if op == "includes_all":
            actual = {frozen(item) for item in observed}
            wanted = {frozen(item) for item in expected}
            return wanted.issubset(actual), f"missing {sorted(wanted - actual)}"
        if op == "set_eq":
            return {frozen(item) for item in observed} == {frozen(item) for item in expected}, "set equality"
        if op in {"lt", "lte", "gt", "gte"}:
            operations = {"lt": observed < expected, "lte": observed <= expected,
                          "gt": observed > expected, "gte": observed >= expected}
            return operations[op], op
        if op == "approx":
            actual_number = float(observed)
            expected_number = float(expected)
            if not math.isfinite(actual_number) or not math.isfinite(expected_number):
                return False, "non-finite numeric value"
            return abs(actual_number - expected_number) <= float(tolerance), f"absolute tolerance {tolerance}"
        return False, f"unsupported operator {op}"
    except (TypeError, ValueError, OverflowError) as exc:
        return False, f"comparison type error: {exc}"


def mismatch_code(expectation: dict[str, Any], missing: bool = False) -> str:
    if missing:
        return "MISSING_OBSERVATION"
    gate = expectation.get("gate")
    path = expectation.get("path", "")
    if gate == "source_support" or (gate == "coverage" and path.endswith(".label")):
        return "LABEL_MISMATCH"
    if gate == "direction_marker_semantics":
        return "MARKER_MISMATCH" if "marker" in path else "DIRECTION_MISMATCH"
    if gate == "numbering_order":
        return "ORDER_MISMATCH"
    if gate == "legend_style":
        return "LEGEND_STYLE_MISMATCH"
    if gate == "chart_data_values":
        return "CHART_VALUE_MISMATCH"
    if gate == "coverage":
        return "COVERAGE_GAP"
    if gate == "editable_layers":
        return "EDITABILITY_MISMATCH"
    return "VALUE_MISMATCH"


def evaluate_matrix(matrix: dict[str, Any], observations: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    seen_ids = set()
    for expectation in matrix.get("expectations", []):
        check_id = expectation.get("check_id", "<missing>")
        base = {key: expectation.get(key) for key in ("check_id", "gate", "truth_ids", "path", "op", "expected", "severity")}
        if check_id in seen_ids:
            checks.append({**base, "status": "fail", "code": "DUPLICATE_CHECK_ID", "message": check_id})
            continue
        seen_ids.add(check_id)
        if expectation.get("op", "eq") == "exists":
            found, observed = lookup(observations, expectation.get("path", ""))
            passed = found and observed is not None
        else:
            found, observed = lookup(observations, expectation.get("path", ""))
            if "expected" not in expectation:
                checks.append({**base, "status": "fail", "code": "EXPECTED_VALUE_MISSING",
                               "message": "All operators except exists require expected."})
                continue
            passed = False
        if expectation.get("op", "eq") != "exists" and found:
            passed, detail = compare(expectation.get("op", "eq"), observed, expectation.get("expected"),
                                     expectation.get("tolerance", 1e-9))
        else:
            detail = "observation path exists" if found else "observation path not found"
        status = "pass" if passed else ("warning" if expectation.get("severity") == "warning" else "fail")
        checks.append({**base, "observed": observed, "observation_found": found, "status": status,
                       "code": "PASS" if passed else mismatch_code(expectation, not found), "message": detail})
    return checks


def error(code: str, message: str, gate: str | None = None, evidence: Any = None) -> dict[str, Any]:
    result = {"code": code, "message": message, "status": "residual_error"}
    if gate:
        result["gate"] = gate
    if evidence is not None:
        result["evidence"] = evidence
    return result


def audit_checklist(checklist: dict[str, Any], truth: dict[str, Any], matrix: dict[str, Any],
                    observations: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], dict[str, bool]]:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    gate_entries = [entry for entry in checklist.get("gates", []) if isinstance(entry, dict)]
    entries = {entry.get("id"): entry for entry in gate_entries}
    if len(entries) != len(gate_entries):
        errors.append(error("CHECKLIST_GATE_DUPLICATE", "Checklist gate IDs must be unique.", "coverage"))
    required: dict[str, bool] = {}
    for gate in REQUIRED_GATES:
        entry = entries.get(gate)
        if not entry:
            errors.append(error("CHECKLIST_GATE_MISSING", gate, gate))
            required[gate] = True
            continue
        if not isinstance(entry.get("required"), bool):
            errors.append(error("CHECKLIST_REQUIRED_FLAG_INVALID", gate, gate))
            required[gate] = True
        else:
            required[gate] = entry["required"]
        if not entry.get("criterion") or not entry.get("review_question"):
            errors.append(error("CHECKLIST_CRITERION_MISSING", gate, gate))
        if entry.get("required") is False and not entry.get("reason"):
            errors.append(error("CHECKLIST_NA_REASON_MISSING", gate, gate))
    extra = set(entries) - set(REQUIRED_GATES)
    if extra:
        warnings.append(f"Additional custom gates are informational to this script: {sorted(extra)}")
    case_id = checklist.get("case_id")
    for name, evidence in (("truth", truth), ("matrix", matrix)):
        if evidence.get("case_id") != case_id:
            errors.append(error("CASE_ID_MISMATCH", f"checklist/{name}: {case_id!r}/{evidence.get('case_id')!r}"))
    if observations.get("schema") != "dual-artifact-quality-gate/observations-v1" or observations.get("observer") != "artifact_observer.py":
        errors.append(error("OBSERVER_INDEPENDENCE_INVALID", "Use unmodified artifact_observer.py output."))
    basis = matrix.get("basis", [])
    if not basis or not any("task" in str(item).lower() for item in basis) or not any("truth" in str(item).lower() for item in basis):
        errors.append(error("EXPECTATION_BASIS_MISSING", "Matrix basis must identify the task and extraction truth table."))
    for item in basis:
        lower = str(item).lower().replace("\\", "/")
        if lower.endswith(".svg") or "figure_ir" in lower or "scene.json" in lower or "render_spec" in lower:
            errors.append(error("EXPECTATION_INDEPENDENCE_VIOLATION", f"Matrix basis includes artifact/render specification: {item}"))
    if "agent" not in str(truth.get("derived_by", "")).lower():
        errors.append(error("TRUTH_DERIVATION_UNDECLARED", "Truth table must declare agent derivation from actual sources."))
    if checklist.get("synthetic", False) != truth.get("synthetic", False) or checklist.get("synthetic", False) != matrix.get("synthetic", False):
        errors.append(error("SYNTHETIC_LABEL_INCONSISTENT", "Checklist, truth and matrix synthetic flags differ."))
    return errors, warnings, required


def audit_truth(truth: dict[str, Any], matrix: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    facts: dict[str, dict[str, Any]] = {}
    for fact in truth.get("facts", []):
        truth_id = fact.get("truth_id")
        if not truth_id:
            errors.append(error("TRUTH_ID_MISSING", "A fact has no truth_id", "coverage"))
            continue
        if truth_id in facts:
            errors.append(error("TRUTH_ID_DUPLICATE", truth_id, "coverage"))
        facts[truth_id] = fact
        source = fact.get("source", {})
        for key in ("path", "locator", "quote"):
            if not source.get(key):
                errors.append(error("SOURCE_EVIDENCE_MISSING", f"{truth_id}: {key}", "source_support"))
        if "required" not in fact or "value" not in fact or not all(fact.get(key) for key in ("kind", "subject", "predicate")):
            errors.append(error("TRUTH_FACT_INCOMPLETE", truth_id, "coverage"))
    referenced = {truth_id for row in matrix.get("expectations", []) for truth_id in row.get("truth_ids", [])}
    for truth_id, fact in facts.items():
        if fact.get("required", True) and truth_id not in referenced:
            errors.append(error("COVERAGE_GAP", f"Required fact has no expectation: {truth_id}", "coverage", truth_id))
    for truth_id in sorted(referenced - set(facts)):
        errors.append(error("UNKNOWN_TRUTH_REFERENCE", truth_id, "coverage"))
    return errors, facts


def audit_visual(review: dict[str, Any] | None, required: dict[str, bool],
                 checklist: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not isinstance(review, dict):
        return {"status": "fail"}, [error("VISUAL_REVIEW_MISSING", "Agent/human actual-render review is required.", "coverage")], warnings
    if review.get("case_id") != checklist.get("case_id"):
        errors.append(error("VISUAL_REVIEW_CASE_MISMATCH", str(review.get("case_id")), "coverage"))
    if review.get("schema") != "dual-artifact-quality-gate/visual-review-v1":
        errors.append(error("VISUAL_REVIEW_SCHEMA_INVALID", str(review.get("schema")), "coverage"))
    if review.get("reviewer", {}).get("type") not in {"agent", "human"} or not review.get("reviewer", {}).get("identity"):
        errors.append(error("VISUAL_REVIEWER_INVALID", "Reviewer type must be agent or human and identity is required.", "coverage"))
    if not review.get("images_inspected"):
        errors.append(error("VISUAL_REVIEW_IMAGES_MISSING", "No rendered images recorded.", "coverage"))
    reviews = {item.get("gate"): item for item in review.get("gate_reviews", []) if isinstance(item, dict)}
    for gate, is_required in required.items():
        if not is_required:
            continue
        item = reviews.get(gate)
        if not item:
            errors.append(error("VISUAL_GATE_REVIEW_MISSING", gate, gate))
            continue
        status = item.get("status")
        if status != "pass":
            errors.append(error("VISUAL_REVIEW_FAIL", f"{gate}: {status}; {item.get('defects', item.get('reason', 'not passed'))}", gate))
        if status == "pass" and not item.get("observations"):
            errors.append(error("VISUAL_REVIEW_OBSERVATION_MISSING", gate, gate))
    requirements = checklist.get("source_review_requirements", {})
    figure03 = requirements.get("figure03_primary_biological_source", {})
    comparisons = review.get("source_comparisons", [])
    if figure03.get("required"):
        for role in ("original_figure03", "primary_biological_source"):
            matches = [item for item in comparisons if item.get("role") == role]
            if not matches:
                errors.append(error("ORIGINAL_BIOLOGICAL_SOURCE_REVIEW_MISSING", role, "source_support"))
            for item in matches:
                if not item.get("inspected") or not item.get("source") or not item.get("locator") or not item.get("observations"):
                    errors.append(error("ORIGINAL_BIOLOGICAL_SOURCE_REVIEW_INCOMPLETE", role, "source_support"))
                if item.get("status", "pass") != "pass":
                    errors.append(error("ORIGINAL_BIOLOGICAL_SOURCE_MISMATCH", role, "source_support"))
    chart_requirement = requirements.get("actual_chart_comparison", {})
    chart_comparisons = review.get("chart_comparisons", [])
    if chart_requirement.get("required"):
        if not chart_comparisons:
            errors.append(error("ACTUAL_CHART_REVIEW_MISSING", "No actual chart/source comparison recorded.", "chart_data_values"))
        for item in chart_comparisons:
            if not item.get("source") or not item.get("rows_compared") or not item.get("observations") or not item.get("inspected", True):
                errors.append(error("ACTUAL_CHART_REVIEW_INCOMPLETE", str(item.get("chart", "unknown")), "chart_data_values"))
            if item.get("status") != "pass":
                errors.append(error("ACTUAL_CHART_REVIEW_FAIL", str(item.get("chart", "unknown")), "chart_data_values"))
    for defect in review.get("residual_defects", []):
        if isinstance(defect, dict) and defect.get("status", "residual_error") in {"residual_error", "error", "failed"}:
            errors.append(error(defect.get("code", "VISUAL_RESIDUAL_ERROR"), str(defect), defect.get("gate")))
        else:
            warnings.append(f"Visual review note: {defect}")
    return {"status": "pass" if not errors else "fail", "reviewer": review.get("reviewer"),
            "images_inspected": review.get("images_inspected", [])}, errors, warnings


def auxiliary_audits(required: dict[str, bool], export_report: Any, contract_report: Any,
                     edit_diff: Any, visual_diff: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    specs = [
        ("export_validity", "export_report", export_report, "EXPORT_INVALID"),
        ("result_contract", "contract_report", contract_report, "CONTRACT_INVALID"),
    ]
    for gate, name, report, code in specs:
        if not required[gate]:
            summaries[name] = {"status": "not_applicable"}
            continue
        if not isinstance(report, dict):
            errors.append(error(code, f"Required {name} is absent.", gate))
            summaries[name] = {"status": "missing"}
            continue
        summaries[name] = {"status": report.get("status"), "errors": report.get("errors", [])}
        if report.get("status") != "pass" or report.get("errors"):
            errors.append(error(code, report.get("errors", "status not pass"), gate))
    edit_required = required["source_preserving_edit_diff"]
    if edit_required:
        if not isinstance(edit_diff, dict):
            errors.append(error("SOURCE_PRESERVATION_FAIL", "Required source edit diff is absent.", "source_preserving_edit_diff"))
        else:
            if edit_diff.get("status") != "pass" or edit_diff.get("errors") or edit_diff.get("unauthorized_changes"):
                errors.append(error("SOURCE_PRESERVATION_FAIL", edit_diff.get("errors", edit_diff.get("unauthorized_changes")), "source_preserving_edit_diff"))
            if not edit_diff.get("changed_ids"):
                errors.append(error("SOURCE_EDIT_EMPTY", "No actual source element changed.", "source_preserving_edit_diff"))
        if not isinstance(visual_diff, dict):
            errors.append(error("VISUAL_DIFF_MISSING", "Before/after visual diff is required for edits.", "source_preserving_edit_diff"))
        else:
            if visual_diff.get("status") != "pass" or visual_diff.get("errors"):
                errors.append(error("VISUAL_DIFF_INVALID", visual_diff.get("errors"), "source_preserving_edit_diff"))
            if not visual_diff.get("difference_detected"):
                errors.append(error("VISUAL_DIFF_EMPTY", "No pixels changed; improvement claim unsupported.", "source_preserving_edit_diff"))
    summaries["source_edit_diff"] = {"status": edit_diff.get("status") if isinstance(edit_diff, dict) else ("required" if edit_required else "not_applicable")}
    summaries["visual_diff"] = {"status": visual_diff.get("status") if isinstance(visual_diff, dict) else ("required" if edit_required else "not_applicable")}
    return summaries, errors


def build_report(checklist: dict[str, Any], truth: dict[str, Any], matrix: dict[str, Any],
                 observations: dict[str, Any], visual_review: dict[str, Any] | None,
                 visual_diff: dict[str, Any] | None, export_report: dict[str, Any] | None,
                 contract_report: dict[str, Any] | None, edit_diff: dict[str, Any] | None) -> dict[str, Any]:
    residuals: list[dict[str, Any]] = []
    warnings: list[str] = []
    found_errors, found_warnings, required = audit_checklist(checklist, truth, matrix, observations)
    residuals.extend(found_errors)
    warnings.extend(found_warnings)
    truth_errors, _ = audit_truth(truth, matrix)
    residuals.extend(truth_errors)
    for row in matrix.get("expectations", []):
        gate = row.get("gate")
        check_id = row.get("check_id")
        if gate not in REQUIRED_GATES:
            residuals.append(error("EXPECTATION_GATE_UNKNOWN", f"{check_id}: {gate}", "coverage"))
        if row.get("severity") not in {"error", "warning"}:
            residuals.append(error("EXPECTATION_SEVERITY_INVALID", str(check_id), gate if gate in REQUIRED_GATES else "coverage"))
        if not check_id or not row.get("path"):
            residuals.append(error("EXPECTATION_ID_PATH_MISSING", str(check_id), gate if gate in REQUIRED_GATES else "coverage"))
        if not row.get("truth_ids") and not row.get("task_basis"):
            residuals.append(error("TASK_BASIS_MISSING", f"Expectation without truth IDs needs task_basis: {check_id}", gate if gate in REQUIRED_GATES else "coverage"))
    checks = evaluate_matrix(matrix, observations)
    for gate, is_required in required.items():
        if is_required and gate in OBSERVATION_GATES:
            rows = [row for row in matrix.get("expectations", []) if row.get("gate") == gate and row.get("severity", "error") == "error"]
            if not rows:
                residuals.append(error("GATE_EXPECTATIONS_MISSING", f"Required gate has no error-severity matrix rows: {gate}", gate))
    for check in checks:
        if check["status"] == "fail":
            residuals.append(error(check["code"], check.get("message", "Expectation failed"), check.get("gate"), check.get("check_id")))
        elif check["status"] == "warning":
            warnings.append(f"{check['check_id']}: {check['code']}")
    for parser_error in observations.get("errors", []):
        residuals.append(error("OBSERVATION_PARSE_ERROR", str(parser_error), "coverage"))
    warnings.extend(str(item) for item in observations.get("parser_limitations", []))
    visual_summary, visual_errors, visual_warnings = audit_visual(visual_review, required, checklist)
    residuals.extend(visual_errors)
    warnings.extend(visual_warnings)
    aux_summary, aux_errors = auxiliary_audits(required, export_report, contract_report, edit_diff, visual_diff)
    residuals.extend(aux_errors)
    gate_summaries: dict[str, Any] = {}
    for gate in REQUIRED_GATES:
        if not required.get(gate, True):
            gate_summaries[gate] = {"status": "not_applicable", "reason": next((item.get("reason") for item in checklist.get("gates", []) if item.get("id") == gate), "")}
            continue
        gate_residuals = [item for item in residuals if item.get("gate") == gate]
        gate_warnings = [check for check in checks if check.get("gate") == gate and check.get("status") == "warning"]
        gate_summaries[gate] = {
            "status": "fail" if gate_residuals else "warning" if gate_warnings else "pass",
            "errors": gate_residuals,
            "structural_consistency_only": True,
        }
    unique_residuals = []
    seen_residuals = set()
    for item in residuals:
        key = frozen(item)
        if key not in seen_residuals:
            seen_residuals.add(key)
            unique_residuals.append(item)
    return {
        "schema": "dual-artifact-quality-gate/qc-report-v1",
        "case_id": checklist.get("case_id"),
        "synthetic": checklist.get("synthetic", False),
        "scientific_correctness": "not established by this structural/consistency report",
        "status": "pass" if not unique_residuals else "fail",
        "checks": checks,
        "gate_summaries": gate_summaries,
        "evidence_audits": {"visual_review": visual_summary, **aux_summary},
        "residual_errors": unique_residuals,
        "warnings": sorted(set(warnings)),
        "parser_limitations": observations.get("parser_limitations", []),
        "repair_round_limit": 2,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("checklist", "truth", "matrix", "observations", "visual-review", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--visual-diff", type=Path)
    parser.add_argument("--export-report", type=Path)
    parser.add_argument("--contract-report", type=Path)
    parser.add_argument("--edit-diff", type=Path)
    args = parser.parse_args(argv)
    try:
        optional = {}
        for key, path in (("visual_diff", args.visual_diff), ("export_report", args.export_report),
                          ("contract_report", args.contract_report), ("edit_diff", args.edit_diff)):
            optional[key] = load(path) if path else None
        report = build_report(load(args.checklist), load(args.truth), load(args.matrix), load(args.observations),
                              load(args.visual_review), optional["visual_diff"], optional["export_report"],
                              optional["contract_report"], optional["edit_diff"])
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        report = {"schema": "dual-artifact-quality-gate/qc-report-v1", "status": "fail",
                  "scientific_correctness": "not established",
                  "residual_errors": [error("QC_INPUT_INVALID", str(exc))], "checks": [], "warnings": []}
    dump(args.report, report)
    return 2 if report.get("residual_errors") else 0


if __name__ == "__main__":
    sys.exit(main())
