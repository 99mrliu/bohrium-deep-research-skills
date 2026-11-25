#!/usr/bin/env python3
"""Question-first coverage validator; Python 3.9+ standard library only.

This tool audits a task-customized coverage JSON. Its manifest describes the
case schema; no official nanopublication output fields are hard-coded.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MISSING = object()


class InputError(Exception):
    pass


def load_json(path: str) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Cannot read JSON {path}: {exc}") from exc


def save_json(path: str, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def pointer_get(document: Any, pointer: str, default: Any = MISSING) -> Any:
    if pointer in ("", None):
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise InputError(f"Invalid JSON Pointer: {pointer!r}")
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return default
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
                if index < 0:
                    return default
                current = current[index]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return current


def present(value: Any) -> bool:
    if value is MISSING or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def path_join(base: str, key: Any) -> str:
    escaped = str(key).replace("~", "~0").replace("/", "~1")
    return f"{base}/{escaped}"


class Audit:
    def __init__(self) -> None:
        self.gaps: List[Dict[str, str]] = []

    def gap(self, code: str, path: str, message: str, fix: str) -> None:
        self.gaps.append({"code": code, "path": path, "message": message, "fix": fix})

    @property
    def errors(self) -> List[Dict[str, str]]:
        return [gap for gap in self.gaps if not gap["code"].startswith("warning.")]


def contract_fields(contract: Any) -> Tuple[List[str], Dict[str, Dict[str, Any]], bool]:
    fields: List[str] = []
    specs: Dict[str, Dict[str, Any]] = {}
    exact = False
    if isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields.append(item)
                specs[item] = {}
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                name = item["name"]
                fields.append(name)
                specs[name] = item
    elif isinstance(contract, dict):
        exact = (
            str(contract.get("mode", "")).upper() == "EXACT"
            or contract.get("exact_top_level") is True
            or contract.get("EXACT") is True
            or contract.get("additionalProperties") is False
        )
        raw = contract.get("fields", MISSING)
        if isinstance(raw, list):
            return (*contract_fields(raw), exact)  # type: ignore[misc]
        if isinstance(raw, dict):
            for name, spec in raw.items():
                fields.append(name)
                specs[name] = spec if isinstance(spec, dict) else {}
        properties = contract.get("properties")
        if isinstance(properties, dict):
            for name, spec in properties.items():
                if name not in fields:
                    fields.append(name)
                specs[name] = spec if isinstance(spec, dict) else {}
        required = contract.get("required")
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name not in fields:
                    fields.append(name)
                    specs[name] = {}
    if not fields:
        raise InputError("output_contract has no declarable fields")
    return fields, specs, exact


def find_task_contract(task_path: str, pointer: str) -> Tuple[Any, bool]:
    try:
        text = Path(task_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Cannot read task {task_path}: {exc}") from exc
    candidates: List[Any] = []
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            candidates.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    for match in re.finditer(r"```(?:json|JSON)\s*\n(.*?)```", text, re.DOTALL):
        try:
            candidates.append(json.loads(match.group(1)))
        except json.JSONDecodeError as exc:
            raise InputError(f"Invalid JSON code block in {task_path}: {exc}") from exc
    for candidate in candidates:
        value = pointer_get(candidate, pointer, MISSING)
        if value is not MISSING:
            return value, True
    return None, False


def load_contract(task_path: str, case: Any, manifest: Dict[str, Any]) -> Dict[str, Any]:
    pointer = manifest.get("task_output_contract_pointer", "/output_contract")
    contract, found = find_task_contract(task_path, pointer)
    source = "task.md"
    if not found:
        contract = pointer_get(case, manifest.get("case_output_contract_pointer", "/output_contract"), MISSING)
        found = contract is not MISSING
        source = "case.json"
    if not found:
        raise InputError("No output_contract in task.md or fallback case.json")
    fields, specs, exact = contract_fields(contract)
    return {"source": source, "fields": fields, "field_specs": specs, "exact_top_level": exact}


def skeleton_value(spec: Dict[str, Any]) -> Any:
    if "default" in spec:
        return copy.deepcopy(spec["default"])
    kind = spec.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), None)
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if kind == "string":
        return ""
    if kind == "number":
        return 0
    if kind == "integer":
        return 0
    if kind == "boolean":
        return False
    return None


def make_skeleton(case: Any, contract: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    case_pointer = manifest.get("case_id_pointer", "/case_id")
    case_key = manifest.get("case_id_output_key", "case_id")
    case_id = pointer_get(case, case_pointer, MISSING)
    if case_id is MISSING:
        raise InputError(f"Missing original case ID at {case_pointer}")
    result: Dict[str, Any] = {case_key: copy.deepcopy(case_id)}
    for name in contract["fields"]:
        if name != case_key:
            result[name] = skeleton_value(contract["field_specs"].get(name, {}))
    return result


def unique_registry(
    audit: Audit,
    raw: Any,
    path: str,
    id_key: str,
    label: str,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    registry: Dict[str, Dict[str, Any]] = {}
    duplicates: List[str] = []
    if not isinstance(raw, list):
        audit.gap("registry.type", path, f"{label} registry must be an array.", "Provide an array of registered objects.")
        return registry, duplicates
    for index, item in enumerate(raw):
        item_path = path_join(path, index)
        if not isinstance(item, dict):
            audit.gap("registry.item_type", item_path, f"{label} entry must be an object.", "Replace the entry with an object.")
            continue
        identifier = item.get(id_key)
        if not isinstance(identifier, str) or not identifier.strip():
            audit.gap("id.missing", path_join(item_path, id_key), f"Missing nonempty {id_key}.", "Assign a stable unique ID.")
            continue
        if identifier in registry:
            duplicates.append(identifier)
            audit.gap("id.duplicate", path_join(item_path, id_key), f"Duplicate {label} ID {identifier!r}.", "Rename it and update all links.")
        else:
            registry[identifier] = item
    return registry, duplicates


def validate_string_array(audit: Audit, value: Any, path: str, label: str) -> List[str]:
    if not isinstance(value, list):
        audit.gap("links.type", path, f"{label} must be an array.", "Use an array of IDs, including an empty array when appropriate.")
        return []
    result: List[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            audit.gap("links.item_type", path_join(path, index), f"{label} entries must be nonempty strings.", "Use a registered ID string.")
        else:
            result.append(item)
    repeated = sorted(key for key, count in Counter(result).items() if count > 1)
    for identifier in repeated:
        audit.gap("links.repeated", path, f"{identifier!r} occurs more than once in {label}.", "Keep one link per target.")
    return result


def validate_coverage(coverage: Any, manifest: Dict[str, Any]) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    audit = Audit()
    if not isinstance(coverage, dict):
        audit.gap("coverage.type", "", "Coverage root must be an object.", "Create an object described by the manifest.")
        return audit.gaps, {"coverage_units": 0}

    questions_raw = pointer_get(coverage, manifest.get("questions_pointer", "/questions"), MISSING)
    claims_raw = pointer_get(coverage, manifest.get("claims_pointer", "/claims"), MISSING)
    evidence_raw = pointer_get(coverage, manifest.get("evidence_pointer", "/evidence"), MISSING)
    sources_raw = pointer_get(coverage, manifest.get("sources_pointer", "/sources"), MISSING)
    claims_pointer = manifest.get("claims_pointer", "/claims")
    evidence_pointer = manifest.get("evidence_pointer", "/evidence")
    sources_pointer = manifest.get("sources_pointer", "/sources")
    claims, duplicate_claims = unique_registry(audit, claims_raw, claims_pointer, manifest.get("claim_id_key", "claim_id"), "claim")
    evidence, duplicate_evidence = unique_registry(audit, evidence_raw, evidence_pointer, manifest.get("evidence_id_key", "evidence_id"), "evidence")
    sources, duplicate_sources = unique_registry(audit, sources_raw, sources_pointer, manifest.get("source_id_key", "source_id"), "source")

    claim_text_key = manifest.get("claim_text_key", "text")
    claim_evidence_key = manifest.get("claim_evidence_ids_key", "evidence_ids")
    for claim_id, claim in claims.items():
        base = f"{claims_pointer}/{claim_id}"
        if not present(claim.get(claim_text_key, MISSING)):
            audit.gap("claim.text_missing", path_join(base, claim_text_key), f"Claim {claim_id} has no atomic text.", "Write an independently checkable assertion.")
        claim_evidence_ids = validate_string_array(audit, claim.get(claim_evidence_key, MISSING), path_join(base, claim_evidence_key), "claim evidence_ids")
        if not claim_evidence_ids:
            audit.gap("claim.evidence_empty", path_join(base, claim_evidence_key), f"Claim {claim_id} has no evidence.", "Link at least one registered evidence ID.")
        for evidence_id in claim_evidence_ids:
            if evidence_id not in evidence:
                audit.gap("id.dangling", path_join(base, claim_evidence_key), f"Claim {claim_id} links missing evidence {evidence_id!r}.", "Register the evidence or remove the stale link.")

    evidence_source_key = manifest.get("evidence_source_id_key", "source_id")
    locator_key = manifest.get("evidence_locator_key", "locator")
    quote_key = manifest.get("evidence_quote_key", "quote")
    support_key = manifest.get("evidence_support_key", "support")
    derivation_key = manifest.get("evidence_derivation_key", "derivation")
    rationale_key = manifest.get("evidence_rationale_key", "rationale")
    support_values = set(manifest.get("evidence_support_values", ["direct", "computed", "inferred"]))
    for evidence_id, record in evidence.items():
        base = f"{evidence_pointer}/{evidence_id}"
        source_id = record.get(evidence_source_key)
        if source_id not in sources:
            audit.gap("id.dangling", path_join(base, evidence_source_key), f"Evidence {evidence_id} links missing source {source_id!r}.", "Register the source or correct the source ID.")
        for key in (locator_key, quote_key):
            if not present(record.get(key, MISSING)):
                audit.gap("evidence.locator_incomplete", path_join(base, key), f"Evidence {evidence_id} lacks {key}.", "Add a precise locator and source excerpt/data.")
        support = record.get(support_key)
        if support not in support_values:
            audit.gap("evidence.support_invalid", path_join(base, support_key), f"Evidence {evidence_id} has invalid support {support!r}.", f"Use one of {sorted(support_values)}.")
        if support == "computed" and not present(record.get(derivation_key, MISSING)):
            audit.gap("derivation.missing", path_join(base, derivation_key), f"Computed evidence {evidence_id} has no derivation.", "Record formula, inputs, and units.")
        if support == "inferred" and not present(record.get(rationale_key, MISSING)):
            audit.gap("rationale.missing", path_join(base, rationale_key), f"Inferred evidence {evidence_id} has no rationale.", "Record the reasoning and its boundary.")

    source_uncertainty_key = manifest.get("source_uncertainty_key", "uncertainty")
    for source_id, source in sources.items():
        if not present(source.get(source_uncertainty_key, MISSING)):
            audit.gap("source.uncertainty_missing", f"{sources_pointer}/{source_id}/{source_uncertainty_key}", f"Source {source_id} has no uncertainty statement.", "State limitations explicitly, including why none are apparent.")

    uncertainty = pointer_get(coverage, manifest.get("uncertainty_pointer", "/uncertainty"), MISSING)
    if not present(uncertainty):
        audit.gap("uncertainty.missing", manifest.get("uncertainty_pointer", "/uncertainty"), "Coverage-level uncertainty is absent or empty.", "Record answer-level and cross-source uncertainties.")
    changes = pointer_get(coverage, manifest.get("change_records_pointer", "/change_records"), MISSING)
    if not isinstance(changes, list):
        audit.gap("change_records.type", manifest.get("change_records_pointer", "/change_records"), "change_records must be an array.", "Use an array; record every substantial correction.")

    if not isinstance(questions_raw, list) or not questions_raw:
        audit.gap("questions.empty", manifest.get("questions_pointer", "/questions"), "Questions must be a nonempty array.", "Build the requirement matrix before validation.")
        questions_raw = []

    required_question = set(manifest.get("required_question_keys", []))
    required_subquestion = set(manifest.get("required_subquestion_keys", []))
    answer_key = manifest.get("answer_key", "answer")
    mode_key = manifest.get("answer_mode_key", "answer_mode")
    status_key = manifest.get("status_key", "status")
    progress_key = manifest.get("progress_key", "progress_percent")
    confidence_key = manifest.get("confidence_key", "confidence")
    question_claim_key = manifest.get("claim_ids_key", "claim_ids")
    question_evidence_key = manifest.get("evidence_ids_key", "evidence_ids")
    requirement_key = manifest.get("requirement_key", "requirement")
    evidence_kinds_key = manifest.get("evidence_kinds_key", "evidence_kinds")
    assertion_links_key = manifest.get("assertion_links_key", "assertion_links")
    id_key_default = manifest.get("question_id_key", "question_id")
    text_key = manifest.get("question_text_key", "question")
    sub_id_key = manifest.get("subquestion_id_key", "subquestion_id")
    sub_pointer = manifest.get("subquestions_pointer", "/subquestions")
    modes = set(manifest.get("answer_modes", ["direct_report", "computed", "inferred", "unreported"]))
    unreported_modes = set(manifest.get("unreported_modes", ["unreported"]))
    status_caps = manifest.get("status_ceiling_percent", {})
    required_support = manifest.get("mode_required_support", {})
    seen_units: Dict[str, str] = {}
    duplicate_units: List[str] = []
    unit_count = 0
    sub_count = 0
    mode_counts: Counter = Counter()
    status_counts: Counter = Counter()

    def validate_unit(unit: Any, base: str, is_sub: bool, child_statuses: Optional[List[str]] = None) -> None:
        nonlocal unit_count, sub_count
        unit_count += 1
        sub_count += int(is_sub)
        if not isinstance(unit, dict):
            audit.gap("question.type", base, "Question/subquestion must be an object.", "Create a matrix row object.")
            return
        identifier_key = sub_id_key if is_sub else id_key_default
        required = required_subquestion if is_sub else required_question
        for key in sorted(required):
            if key not in unit:
                audit.gap("question.required_missing", path_join(base, key), f"Required key {key!r} is missing.", "Add the field required by this case manifest.")
        identifier = unit.get(identifier_key)
        if not isinstance(identifier, str) or not identifier.strip():
            audit.gap("id.missing", path_join(base, identifier_key), "Question/subquestion ID is missing.", "Assign a stable unique ID.")
        else:
            if identifier in seen_units:
                duplicate_units.append(identifier)
                audit.gap("id.duplicate", path_join(base, identifier_key), f"Question ID {identifier!r} duplicates {seen_units[identifier]}.", "Rename it and update all references.")
            else:
                seen_units[identifier] = base
        if not present(unit.get(text_key, MISSING)):
            audit.gap("question.text_missing", path_join(base, text_key), "Question text is empty.", "Preserve the asked question or minimal subquestion.")
        answer = unit.get(answer_key, MISSING)
        if not present(answer):
            audit.gap("answer.missing", path_join(base, answer_key), f"Unit {identifier!r} has no answer.", "Answer directly, or explicitly state unreported with searched scope.")

        mode = unit.get(mode_key)
        if mode not in modes:
            audit.gap("answer_mode.invalid", path_join(base, mode_key), f"Invalid answer mode {mode!r}.", f"Use one of {sorted(modes)}; split mixed-mode answers.")
        else:
            mode_counts[mode] += 1
        status = unit.get(status_key)
        if status not in status_caps:
            audit.gap("status.invalid", path_join(base, status_key), f"Invalid status {status!r}.", f"Use one of {sorted(status_caps)}.")
        else:
            status_counts[status] += 1
        progress = unit.get(progress_key)
        if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not 0 <= progress <= 100:
            audit.gap("progress.range", path_join(base, progress_key), "Progress must be numeric and within 0–100.", "Set a bounded numeric percentage.")
        elif status in status_caps and progress > status_caps[status]:
            audit.gap("status.ceiling_exceeded", path_join(base, progress_key), f"Progress {progress} exceeds {status} cap {status_caps[status]}.", "Lower progress or complete the missing closure requirements before upgrading status.")
        confidence = unit.get(confidence_key)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            audit.gap("confidence.range", path_join(base, confidence_key), "Confidence must be numeric and within 0–1.", "Use an honest bounded confidence.")

        requirement = unit.get(requirement_key, MISSING)
        if not isinstance(requirement, dict):
            audit.gap("requirement.missing", path_join(base, requirement_key), "Requirement matrix row is absent.", "Pre-register evidence kinds and assertion links.")
        else:
            if not present(requirement.get(evidence_kinds_key, MISSING)):
                audit.gap("requirement.evidence_kinds", path_join(path_join(base, requirement_key), evidence_kinds_key), "Required evidence kinds are empty.", "List the evidence needed to close this question.")
            links = requirement.get(assertion_links_key, MISSING)
            validate_string_array(audit, links, path_join(path_join(base, requirement_key), assertion_links_key), "requirement assertion_links")
            if not present(links):
                audit.gap("requirement.assertion_links", path_join(path_join(base, requirement_key), assertion_links_key), "Assertion links are empty.", "Link the task/assertions this row must answer.")

        claim_ids = validate_string_array(audit, unit.get(question_claim_key, MISSING), path_join(base, question_claim_key), "question claim_ids")
        evidence_ids = validate_string_array(audit, unit.get(question_evidence_key, MISSING), path_join(base, question_evidence_key), "question evidence_ids")
        if mode in unreported_modes:
            if claim_ids or evidence_ids:
                audit.gap("unreported.factual_links", base, "Unreported row has factual claim/evidence links.", "Remove unsupported factual links; represent disclosure checks inside searched_scope.")
            if present(answer) and isinstance(answer, str) and not any(term in answer.lower() for term in ("unreported", "not reported", "未报告")):
                audit.gap("unreported.answer_unclear", path_join(base, answer_key), "Unreported answer does not explicitly say unreported/not reported/未报告.", "State the limitation directly.")
            scope = pointer_get(unit, manifest.get("searched_scope_pointer", "/unreported/searched_scope"), MISSING)
            scope_path = base + manifest.get("searched_scope_pointer", "/unreported/searched_scope")
            if not isinstance(scope, list) or not scope:
                audit.gap("unreported.searched_scope", scope_path, "Unreported row needs nonempty searched_scope.", "Record sources, regions, keywords, figures and supplements checked.")
            else:
                for index, item in enumerate(scope):
                    item_path = path_join(scope_path, index)
                    if isinstance(item, dict):
                        source_id = item.get(evidence_source_key)
                        if source_id is not None and source_id not in sources:
                            audit.gap("id.dangling", path_join(item_path, evidence_source_key), f"Searched scope links unknown source {source_id!r}.", "Register this source or correct the ID.")
                        if not present(item.get("regions", MISSING)) and not present(item.get("actions", MISSING)):
                            audit.gap("unreported.scope_detail", item_path, "Structured searched scope needs regions or actions.", "Describe where and how the source was searched.")
                    elif not present(item):
                        audit.gap("unreported.scope_detail", item_path, "Searched scope entry is empty.", "Describe the searched source and region.")
        else:
            if not claim_ids:
                audit.gap("claims.empty", path_join(base, question_claim_key), "Non-unreported row needs claim IDs.", "Register and link atomic claims.")
            if not evidence_ids:
                audit.gap("evidence.empty", path_join(base, question_evidence_key), "Non-unreported row needs evidence IDs.", "Link evidence supporting this answer.")
            expected_support = required_support.get(mode)
            supports = {record.get(support_key) for eid, record in evidence.items() if eid in evidence_ids}
            if expected_support and expected_support not in supports:
                audit.gap("answer_mode.support_mismatch", path_join(base, mode_key), f"Mode {mode} lacks {expected_support} evidence among its own evidence IDs.", "Link appropriate evidence or downgrade/split the answer mode.")

        for claim_id in claim_ids:
            if claim_id not in claims:
                audit.gap("id.dangling", path_join(base, question_claim_key), f"Unit {identifier!r} links unknown claim {claim_id!r}.", "Register the claim or remove the link.")
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                audit.gap("id.dangling", path_join(base, question_evidence_key), f"Unit {identifier!r} links unknown evidence {evidence_id!r}.", "Register the evidence or remove the link.")
        if child_statuses and status == "answered" and any(item in ("unanswered", "partial") for item in child_statuses):
            audit.gap("status.child_mismatch", path_join(base, status_key), "Parent is answered despite partial/unanswered child.", "Lower parent status or close the child gaps before upgrading.")

    for q_index, question in enumerate(questions_raw):
        q_path = path_join(manifest.get("questions_pointer", "/questions"), q_index)
        children = pointer_get(question, sub_pointer, []) if isinstance(question, dict) else []
        child_statuses: List[str] = []
        if not isinstance(children, list):
            audit.gap("subquestions.type", q_path + sub_pointer, "Subquestions must be an array.", "Use an array of subquestion matrix rows.")
            children = []
        for child_index, child in enumerate(children):
            child_path = path_join(q_path + sub_pointer, child_index)
            child_statuses.append(child.get(status_key) if isinstance(child, dict) else "invalid")
            validate_unit(child, child_path, True)
        validate_unit(question, q_path, False, child_statuses)

    summary = {
        "coverage_units": unit_count,
        "root_questions": len(questions_raw),
        "subquestions": sub_count,
        "claims": len(claims),
        "evidence": len(evidence),
        "sources": len(sources),
        "answer_modes": dict(sorted(mode_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "duplicate_ids": len(duplicate_claims) + len(duplicate_evidence) + len(duplicate_sources) + len(duplicate_units),
        "dangling_ids": sum(1 for gap in audit.gaps if gap["code"] == "id.dangling"),
    }
    return audit.gaps, summary


def validate_result(
    result: Any,
    coverage: Any,
    case: Any,
    contract: Dict[str, Any],
    manifest: Dict[str, Any],
) -> List[Dict[str, str]]:
    audit = Audit()
    if not isinstance(result, dict):
        audit.gap("result.type", "", "result.json must be an object.", "Write a top-level JSON object.")
        return audit.gaps
    case_key = manifest.get("case_id_output_key", "case_id")
    case_pointer = manifest.get("case_id_pointer", "/case_id")
    expected_id = pointer_get(case, case_pointer, MISSING)
    if case_key not in result:
        audit.gap("result.case_id_missing", "/" + case_key, "Original case ID is missing.", f"Copy {case_pointer} from case.json unchanged.")
    elif expected_id is not MISSING and result[case_key] != expected_id:
        audit.gap("result.case_id_changed", "/" + case_key, "Result case ID differs from the original.", "Restore the exact original value and type.")
    required_set = set(contract["fields"]) | {case_key}
    for name in contract["fields"]:
        if name not in result:
            audit.gap("result.field_missing", "/" + name, f"Output contract field {name!r} is missing.", "Restore every field declared by the task contract, even in a partial result.")
            continue
        expected_type = contract["field_specs"].get(name, {}).get("type")
        type_map = {"array": list, "object": dict, "string": str, "number": (int, float), "integer": int, "boolean": bool}
        python_type = type_map.get(expected_type)
        boolean_as_number = expected_type in ("number", "integer") and isinstance(result[name], bool)
        if python_type is not None and (not isinstance(result[name], python_type) or boolean_as_number):
            audit.gap("result.field_type", "/" + name, f"Field {name!r} should be {expected_type}.", "Match the declared field type; do not replace arrays/objects with prose.")
    if contract["exact_top_level"]:
        for name in sorted(set(result) - required_set):
            audit.gap("result.unexpected_field", "/" + name, f"EXACT contract forbids extra top-level field {name!r}.", "Remove it or place it only if the task explicitly changes the contract.")
    for name in manifest.get("result_nonempty_fields", []):
        if name in result and not present(result[name]):
            audit.gap("result.field_empty", "/" + name, f"Field {name!r} is required to be nonempty by this manifest.", "Provide the audited content or use an honest partial only when the task permits empty fields.")
    output_map = manifest.get("output_map", {})
    if isinstance(output_map, dict):
        for name, pointer in output_map.items():
            if name not in result or name not in contract["fields"]:
                continue
            expected = pointer_get(coverage, pointer, MISSING)
            if expected is MISSING:
                audit.gap("result.output_map_missing", "/" + name, f"Coverage has no mapped value at {pointer}.", "Populate the mapped coverage field or adapt the manifest.")
            elif result[name] != expected:
                audit.gap("result.stale_payload", "/" + name, f"Result field differs from coverage pointer {pointer}.", "Regenerate result from the validated current coverage.")
    return audit.gaps


def report_document(
    case: Any,
    contract: Dict[str, Any],
    manifest: Dict[str, Any],
    gaps: List[Dict[str, str]],
    summary: Dict[str, Any],
    result_checked: bool,
) -> Dict[str, Any]:
    codes = Counter(gap["code"] for gap in gaps)
    return {
        "ok": not gaps,
        "case_id": pointer_get(case, manifest.get("case_id_pointer", "/case_id"), None),
        "contract": {"source": contract["source"], "exact_top_level": contract["exact_top_level"], "fields": contract["fields"]},
        "result_checked": result_checked,
        "summary": dict(summary, error_count=len(gaps), gap_codes=dict(sorted(codes.items()))),
        "gaps": gaps,
        "next_action": "All structural checks passed; scientific correctness still needs domain review." if not gaps else "Repair gaps in JSON-pointer order, regenerate result from coverage, then rerun audit.",
    }


def run(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    case = load_json(args.case)
    contract = load_contract(args.task, case, manifest)
    if args.command == "skeleton":
        save_json(args.output, make_skeleton(case, contract, manifest))
        print(f"Skeleton written: {args.output}")
        return 0

    coverage = load_json(args.coverage)
    coverage_gaps, summary = validate_coverage(coverage, manifest)
    if args.command == "validate":
        gaps = coverage_gaps
        result_checked = False
    else:
        result_gaps = validate_result(load_json(args.result), coverage, case, contract, manifest)
        gaps = coverage_gaps + result_gaps
        result_checked = True
    if hasattr(args, "skeleton") and args.skeleton:
        save_json(args.skeleton, make_skeleton(case, contract, manifest))
    report = report_document(case, contract, manifest, gaps, summary, result_checked)
    save_json(args.report, report)
    print(json.dumps({"ok": report["ok"], "errors": len(gaps), "report": args.report}, ensure_ascii=False))
    return 0 if not gaps else 1


def build_result(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    case = load_json(args.case)
    contract = load_contract(args.task, case, manifest)
    coverage = load_json(args.coverage)
    gaps, summary = validate_coverage(coverage, manifest)
    if gaps:
        if args.report:
            save_json(args.report, report_document(case, contract, manifest, gaps, summary, False))
        print(f"Refusing to build result: {len(gaps)} coverage gaps", file=sys.stderr)
        return 1
    result = make_skeleton(case, contract, manifest)
    output_map = manifest.get("output_map", {})
    if not isinstance(output_map, dict):
        raise InputError("output_map must be an object")
    result_gaps: List[Dict[str, str]] = []
    result_audit = Audit()
    for name in contract["fields"]:
        if name == manifest.get("case_id_output_key", "case_id"):
            continue
        pointer = output_map.get(name)
        if not isinstance(pointer, str):
            result_audit.gap("result.output_map_missing", "/" + name, f"No output_map pointer for {name}.", "Map every actual contract field explicitly in the case manifest.")
            continue
        value = pointer_get(coverage, pointer, MISSING)
        if value is MISSING:
            result_audit.gap("result.output_map_missing", "/" + name, f"No coverage value at {pointer}.", "Populate it or correct the manifest.")
        else:
            result[name] = copy.deepcopy(value)
    result_gaps = result_audit.gaps + validate_result(result, coverage, case, contract, manifest)
    if result_gaps:
        if args.report:
            save_json(args.report, report_document(case, contract, manifest, result_gaps, summary, True))
        print(f"Refusing to build result: {len(result_gaps)} result gaps", file=sys.stderr)
        return 1
    save_json(args.output, result)
    if args.report:
        save_json(args.report, report_document(case, contract, manifest, [], summary, True))
    print(f"Validated result written: {args.output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--task", required=True)
    common.add_argument("--case", required=True)
    common.add_argument("--manifest", required=True)

    skel = sub.add_parser("skeleton", parents=[common], help="Write a fillable result skeleton from the actual contract")
    skel.add_argument("--output", required=True)

    val = sub.add_parser("validate", parents=[common], help="Validate coverage and always emit a gap report")
    val.add_argument("--coverage", required=True)
    val.add_argument("--report", required=True)
    val.add_argument("--skeleton")

    aud = sub.add_parser("audit", parents=[common], help="Validate coverage and final result, including EXACT fields")
    aud.add_argument("--coverage", required=True)
    aud.add_argument("--result", required=True)
    aud.add_argument("--report", required=True)
    aud.add_argument("--skeleton")

    build = sub.add_parser("build-result", parents=[common], help="Build final result only from valid coverage")
    build.add_argument("--coverage", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--report", required=True)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        return build_result(args) if args.command == "build-result" else run(args)
    except InputError as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    except (TypeError, AttributeError) as exc:
        print(f"MANIFEST/INPUT SHAPE ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
