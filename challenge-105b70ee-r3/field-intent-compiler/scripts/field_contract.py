#!/usr/bin/env python3
"""Compile target-field intent and adjudicate evidence without selecting values.

Stdlib only. The compiler validates agent decisions; it never ranks or chooses
candidate values from paragraph text.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

UNSPECIFIED = "UNSPECIFIED_REQUIRES_CONTRACT_AMENDMENT"
FIELD_STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
CONCLUSION_MODALITIES = {
    "author_conclusion", "author_speculation", "author_limitation",
    "reported_fact", "mixed", "unclear",
}
AXES = (
    "metric_identity", "subject_entity", "expected_value_form",
    "requested_unit", "statistic", "required_condition", "comparator",
    "source_scope", "modality",
)
ALIASES = {
    "metric_identity": ("metric_identity", "metric", "metric_name", "indicator", "measure"),
    "subject_entity": ("subject_entity", "subject", "entity", "material", "system"),
    "expected_value_form": ("expected_value_form", "value_form", "answer_type", "expected_type", "type"),
    "requested_unit": ("requested_unit", "unit", "units", "requested_units"),
    "statistic": ("statistic", "stat", "aggregation", "summary_statistic"),
    "required_condition": ("required_condition", "experimental_condition", "condition", "conditions"),
    "comparator": ("comparator", "comparison", "baseline"),
    "source_scope": ("source_scope", "scope", "allowed_sources"),
    "modality": ("modality", "conclusion_modality"),
}


class ContractError(Exception):
    """An input, contract, evidence, or adjudication validation error."""


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ContractError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def display(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def first_explicit(spec: Dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in spec and spec[name] not in (None, "", [], {}):
            return copy.deepcopy(spec[name])
    return UNSPECIFIED


def raw_field_specs(document: Any) -> List[Dict[str, Any]]:
    if isinstance(document, list):
        raw = document
    elif isinstance(document, dict):
        raw = None
        for key in ("fields", "target_fields", "target-fields"):
            if key in document:
                raw = document[key]
                break
        if raw is None and "field_id" in document:
            raw = [document]
        if raw is None:
            # A mapping keyed by field ID is also accepted. Metadata keys are not fields.
            raw = []
            for key, value in document.items():
                if key in {"case_id", "version", "description", "instructions"}:
                    continue
                if isinstance(value, dict):
                    item = copy.deepcopy(value)
                    item.setdefault("field_id", key)
                    raw.append(item)
        if isinstance(raw, dict):
            raw = [dict(value, field_id=value.get("field_id", key)) if isinstance(value, dict)
                   else {"field_id": key, "question": value} for key, value in raw.items()]
    else:
        raw = None
    if not isinstance(raw, list) or not raw:
        raise ContractError("target-fields.json must contain a non-empty fields list or field mapping")
    result = []
    seen = set()
    for index, item in enumerate(raw):
        if isinstance(item, str):
            item = {"field_id": item, "question": item}
        if not isinstance(item, dict):
            raise ContractError(f"target field at index {index} is not an object")
        field_id = item.get("field_id", item.get("id"))
        if not isinstance(field_id, str) or not field_id.strip():
            raise ContractError(f"target field at index {index} lacks a non-empty field_id")
        if field_id in seen:
            raise ContractError(f"duplicate target field_id: {field_id}")
        seen.add(field_id)
        normalized = copy.deepcopy(item)
        normalized["field_id"] = field_id
        result.append(normalized)
    return result


def make_tests(field_id: str, contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    prompts = {
        "metric_identity": "The candidate is the requested metric, not a same-named or co-located different metric.",
        "subject_entity": "The candidate describes the requested subject/entity, not another arm, material, group, or time point.",
        "expected_value_form": "The candidate has the requested value form (for example scalar, range, text, or list) without silent reshaping.",
        "requested_unit": "The candidate preserves the requested unit; any conversion is explicitly requested and separately auditable.",
        "statistic": "The candidate is the requested statistic, not a raw observation, mean, SD, SE, CI, or other statistic substituted for it.",
        "required_condition": "All required conditions are satisfied together by the same candidate evidence; a same value under another condition is rejected.",
        "comparator": "The comparator/baseline/direction is the requested one, including an explicit no-comparator interpretation when applicable.",
        "source_scope": "The candidate and search are inside the permitted source scope; out-of-scope text cannot establish the answer.",
        "modality": "For a conclusion field, author conclusion, speculation, limitation, and reported fact are distinguished from the wording; otherwise modality is not applicable.",
        "verbatim_evidence": "The exact quote is present in the identified paragraph and contains the verbatim value. This is necessary but never sufficient for acceptance.",
    }
    tests = []
    for axis in AXES:
        tests.append({
            "test_id": f"{field_id}::{axis}",
            "axis": axis,
            "requirement": prompts[axis],
            "compiled_requirement": copy.deepcopy(contract[axis]),
            "evaluation": "agent_semantic_adjudication",
            "required_for": ["reported", "source_conflict"],
            "state_before_candidates": "pending",
        })
    tests.append({
        "test_id": f"{field_id}::verbatim_evidence",
        "axis": "verbatim_evidence",
        "requirement": prompts["verbatim_evidence"],
        "compiled_requirement": "exact substring in exact registered source paragraph",
        "evaluation": "compiler_plus_agent",
        "required_for": ["reported", "source_conflict"],
        "state_before_candidates": "pending",
    })
    return tests


def compile_contracts(specs: List[Dict[str, Any]], task_text: str, case_id: str, synthetic: bool) -> Dict[str, Any]:
    """Read QUESTION/SCHEMA only. No source register or candidate is an argument."""
    fields = []
    for spec in specs:
        field_id = spec["field_id"]
        field_kind = spec.get("field_kind", spec.get("kind", "value"))
        contract = {axis: first_explicit(spec, ALIASES[axis]) for axis in AXES}
        if field_kind != "conclusion" and contract["modality"] == UNSPECIFIED:
            contract["modality"] = "not_applicable"
        item = {
            "field_id": field_id,
            "field_kind": field_kind,
            "question": spec.get("question", spec.get("prompt")),
            **contract,
            "source_spec": copy.deepcopy(spec),
            "acceptance_tests": [],
        }
        item["blocking_issues"] = [f"{axis} is not explicit in target schema" for axis in AXES
                                   if item[axis] == UNSPECIFIED]
        item["acceptance_tests"] = make_tests(field_id, item)
        fields.append(item)
    core = {
        "contract_version": "field-intent-contract/v1",
        "case_id": case_id,
        "synthetic": synthetic,
        "task_sha256": hashlib.sha256(task_text.encode("utf-8")).hexdigest(),
        "compilation_order": "QUESTION/SCHEMA -> acceptance tests -> source register -> candidate adjudication",
        "literal_quote_policy": "A literal quote is evidence integrity only; it never establishes semantic correctness.",
        "fields": fields,
    }
    core["contract_sha256"] = canonical_hash(core)
    core["amendments"] = []
    return core


def empty_field(field_id: str) -> Dict[str, Any]:
    return {
        "field_id": field_id, "status": "extraction_failed", "scalar": None,
        "units": None, "statistic": None, "experimental_condition": None,
        "condition": None, "comparator": None, "paragraph_id": None,
        "quote": None, "evidence": [], "verbatim_value": None,
        "modality": None, "notes": "Conservative skeleton created before candidate adjudication; no value selected.",
        "failure_reason": "Awaiting agent-authored adjudication.",
    }


def skeleton(case_id: str, field_ids: List[str], synthetic: bool, event: str) -> Dict[str, Any]:
    fields = [empty_field(field_id) for field_id in field_ids]
    return {
        "case_id": case_id,
        "status": "insufficient_evidence" if field_ids else "input_error",
        "synthetic": synthetic,
        "label": "SYNTHETIC EXAMPLE — NOT A FORMAL TEST RESULT" if synthetic else "runtime result",
        "result": {"fields": copy.deepcopy(fields), "field_results": copy.deepcopy(fields)},
        "claims": [],
        "uncertainties": ([{"field_id": field_id, "kind": "awaiting_adjudication",
                            "message": "No candidate value has been accepted."} for field_id in field_ids]
                          if field_ids else [{"kind": "input_error", "message": "No target fields available."}]),
        "sources": [],
        "change_records": [{"sequence": 1, "event": event, "candidate_values_read": False}],
    }


def command_init(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    work = Path(args.work)
    output = Path(args.output)
    case_path = input_dir / "case.json"
    fields_path = input_dir / "target-fields.json"
    task_path = input_dir / "task.md"
    case_id = "UNKNOWN_CASE"
    field_ids: List[str] = []
    synthetic = False
    try:
        case = read_json(case_path)
        if not isinstance(case, dict):
            raise ContractError("case.json must be a JSON object")
        case_id = case.get("case_id", case_id)
        synthetic = case.get("synthetic") is True
        specs = raw_field_specs(read_json(fields_path))
        field_ids = [spec["field_id"] for spec in specs]
    except ContractError as exc:
        # A full skeleton, when IDs are available, is written even on input failure.
        write_json(output / "result.json", skeleton(case_id, field_ids, synthetic, "input_error"))
        raise exc
    # Required conservative artifact is persisted before contract compilation.
    write_json(output / "result.json", skeleton(case_id, field_ids, synthetic, "conservative_skeleton_initialized"))
    try:
        task_text = task_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failed = skeleton(case_id, field_ids, synthetic, "input_error")
        failed["status"] = "input_error"
        failed["uncertainties"] = [{"kind": "input_error", "message": f"Cannot read task.md: {exc}"}]
        write_json(output / "result.json", failed)
        raise ContractError(f"cannot read {task_path}: {exc}") from exc
    contract = compile_contracts(specs, task_text, case_id, synthetic)
    write_json(work / "acceptance-contract.json", contract)
    write_json(work / "source-register.json", {"synthetic": synthetic, "sources": [], "paragraphs": []})
    write_json(work / "runtime-events.json", {"synthetic": synthetic, "events": [
        {"sequence": 1, "event": "full_result_skeleton_written", "candidate_values_read": False},
        {"sequence": 2, "event": "acceptance_contract_and_tests_compiled", "candidate_values_read": False,
         "contract_sha256": contract["contract_sha256"]},
    ]})
    write_json(work / "adjudication-template.json", {
        "case_id": case_id,
        "synthetic": synthetic,
        "contract_sha256": contract["contract_sha256"],
        "decisions": [{"field_id": field_id, "status": "extraction_failed",
                       "failure_reason": "TODO: replace only after reading the precompiled tests."}
                      for field_id in field_ids],
    })
    return 0


def command_amend(args: argparse.Namespace) -> int:
    work = Path(args.work)
    contract = read_json(work / "acceptance-contract.json")
    amendments = read_json(Path(args.amendments))
    rows = amendments.get("amendments") if isinstance(amendments, dict) else amendments
    if not isinstance(rows, list) or not rows:
        raise ContractError("amendments must be a non-empty list or an object containing amendments")
    by_id = {field["field_id"]: field for field in contract["fields"]}
    records = []
    for row in rows:
        if not isinstance(row, dict) or row.get("field_id") not in by_id:
            raise ContractError("each amendment needs a valid field_id")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ContractError("each contract amendment needs a question/schema-based rationale")
        field = by_id[row["field_id"]]
        values = row.get("set", {})
        if not isinstance(values, dict) or not values or any(axis not in AXES for axis in values):
            raise ContractError("amendment set must contain only non-empty acceptance-contract axes")
        for axis, value in values.items():
            if value in (None, "", [], {}):
                raise ContractError(f"amendment for {row['field_id']}:{axis} is empty")
            field[axis] = copy.deepcopy(value)
        field["acceptance_tests"] = make_tests(field["field_id"], field)
        field["blocking_issues"] = [f"{axis} is not explicit in target schema" for axis in AXES
                                    if field[axis] == UNSPECIFIED]
        records.append({"field_id": row["field_id"], "set": copy.deepcopy(values),
                        "rationale": row["rationale"], "basis": "QUESTION/SCHEMA only; no candidate value"})
    prior = contract["contract_sha256"]
    contract.setdefault("amendments", []).extend(records)
    contract["contract_sha256"] = canonical_hash({key: value for key, value in contract.items()
                                                   if key not in {"contract_sha256", "amendments"}})
    write_json(work / "acceptance-contract.json", contract)
    events_path = work / "runtime-events.json"
    events = read_json(events_path)
    events["events"].append({"sequence": len(events["events"]) + 1,
                             "event": "acceptance_contract_amended_before_adjudication",
                             "prior_contract_sha256": prior,
                             "contract_sha256": contract["contract_sha256"],
                             "candidate_values_read": False})
    write_json(events_path, events)
    template_path = work / "adjudication-template.json"
    if template_path.exists():
        template = read_json(template_path)
        template["contract_sha256"] = contract["contract_sha256"]
        write_json(template_path, template)
    return 0


def index_register(register: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str], Dict[str, Any]]]:
    if not isinstance(register, dict) or not isinstance(register.get("paragraphs"), list):
        raise ContractError("source register must contain a paragraphs list")
    sources = {}
    for source in register.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise ContractError("each source needs a source_id")
        sources[source["source_id"]] = source
    paragraphs = {}
    for paragraph in register["paragraphs"]:
        if not isinstance(paragraph, dict):
            raise ContractError("each paragraph must be an object")
        source_id, paragraph_id, text = paragraph.get("source_id"), paragraph.get("paragraph_id"), paragraph.get("text")
        if not all(isinstance(value, str) and value for value in (source_id, paragraph_id, text)):
            raise ContractError("each paragraph needs non-empty source_id, paragraph_id, and text")
        key = (source_id, paragraph_id)
        if key in paragraphs:
            raise ContractError(f"duplicate source paragraph: {source_id}/{paragraph_id}")
        paragraphs[key] = paragraph
    return sources, paragraphs


def validate_evidence(evidence: Any, paragraphs: Dict[Tuple[str, str], Dict[str, Any]], label: str) -> Dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ContractError(f"{label}: evidence must be an object")
    required = ("source_id", "paragraph_id", "quote")
    if any(not isinstance(evidence.get(key), str) or not evidence.get(key) for key in required):
        raise ContractError(f"{label}: evidence requires source_id, paragraph_id, and non-empty quote")
    key = (evidence["source_id"], evidence["paragraph_id"])
    if key not in paragraphs:
        raise ContractError(f"{label}: unregistered source paragraph {key[0]}/{key[1]}")
    paragraph = paragraphs[key]
    if evidence["quote"] not in paragraph["text"]:
        raise ContractError(f"{label}: quote is not an exact substring of the registered paragraph")
    if "page" not in evidence or evidence["page"] != paragraph.get("page"):
        raise ContractError(f"{label}: evidence page must exactly match the registered paragraph page (null is valid)")
    normalized = {"source_id": evidence["source_id"], "page": evidence["page"],
                  "paragraph_id": evidence["paragraph_id"], "quote": evidence["quote"]}
    return normalized


def source_in_scope(source_id: str, scope: Any) -> bool:
    # This is a metadata scope check only, never a candidate-selection rule.
    if isinstance(scope, str):
        return scope in {"all_sources", "all_sources_in_source_register"}
    if isinstance(scope, list):
        return source_id in scope
    if isinstance(scope, dict) and isinstance(scope.get("source_ids"), list):
        return source_id in scope["source_ids"]
    return True  # Complex scopes require the agent's source_scope semantic check.


def check_id_set(contract_field: Dict[str, Any]) -> set:
    return {test["test_id"] for test in contract_field["acceptance_tests"]}


def validate_checks(decision: Dict[str, Any], contract_field: Dict[str, Any], status: str) -> List[Dict[str, Any]]:
    field_id = contract_field["field_id"]
    if status not in {"reported", "source_conflict"}:
        return []
    rows = decision.get("acceptance_checks")
    if not isinstance(rows, list):
        raise ContractError(f"{field_id}: reported/conflict decisions require every precompiled acceptance check")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("test_id"), str) or not isinstance(row.get("passed"), bool):
            raise ContractError(f"{field_id}: each acceptance check needs test_id and boolean passed")
        if row["test_id"] in by_id:
            raise ContractError(f"{field_id}: duplicate acceptance check {row['test_id']}")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ContractError(f"{field_id}: each acceptance check needs a semantic rationale")
        by_id[row["test_id"]] = row
    expected = check_id_set(contract_field)
    if set(by_id) != expected:
        raise ContractError(f"{field_id}: acceptance checks do not exactly match the precompiled test set")
    failed = [test_id for test_id, row in by_id.items() if not row["passed"]]
    if failed:
        raise ContractError(f"{field_id}: candidate rejected by acceptance tests: {', '.join(sorted(failed))}")
    return [{"test_id": test_id, "passed": True, "rationale": by_id[test_id]["rationale"]}
            for test_id in sorted(expected)]


def scalar_fields(decision: Dict[str, Any], status: str) -> Dict[str, Any]:
    return {
        "scalar": copy.deepcopy(decision.get("scalar")),
        "units": copy.deepcopy(decision.get("units")),
        "statistic": copy.deepcopy(decision.get("statistic")),
        "experimental_condition": copy.deepcopy(decision.get("experimental_condition")),
        "condition": copy.deepcopy(decision.get("experimental_condition")),
        "comparator": copy.deepcopy(decision.get("comparator")),
        "verbatim_value": copy.deepcopy(decision.get("verbatim_value")),
        "modality": copy.deepcopy(decision.get("modality", "not_applicable")),
    }


def validate_scalar_verbatim(field_id: str, scalar: Any, verbatim: Any, quote: str) -> None:
    if not isinstance(verbatim, str) or not verbatim or verbatim not in quote:
        raise ContractError(f"{field_id}: verbatim_value must be non-empty and exactly contained in quote")
    if isinstance(scalar, (dict, list)) or scalar is None:
        raise ContractError(f"{field_id}: reported scalar must be a JSON scalar")
    if isinstance(scalar, str) and scalar != verbatim:
        raise ContractError(f"{field_id}: string scalar must equal verbatim_value; put explanation in notes")
    # Numeric scalar spellings are retained separately in verbatim_value. No conversion is performed.


def validate_modality(decision: Dict[str, Any], contract_field: Dict[str, Any]) -> str:
    field_id = contract_field["field_id"]
    modality = decision.get("modality", "not_applicable")
    if contract_field["field_kind"] == "conclusion":
        if modality not in CONCLUSION_MODALITIES:
            raise ContractError(f"{field_id}: conclusion needs an allowed author modality")
        required = contract_field["modality"]
        if required not in {UNSPECIFIED, "classify_from_wording", "required"} and modality != required:
            raise ContractError(f"{field_id}: modality does not match the compiled contract")
    elif modality != "not_applicable":
        raise ContractError(f"{field_id}: non-conclusion modality must be not_applicable")
    return modality


def adjudicate_field(decision: Dict[str, Any], contract_field: Dict[str, Any],
                     paragraphs: Dict[Tuple[str, str], Dict[str, Any]]) -> Dict[str, Any]:
    field_id = contract_field["field_id"]
    if not isinstance(decision, dict) or decision.get("field_id") != field_id:
        raise ContractError(f"{field_id}: malformed or mismatched decision")
    status = decision.get("status")
    if status not in FIELD_STATUSES:
        raise ContractError(f"{field_id}: invalid field status {status!r}")
    if status in {"reported", "source_conflict"} and contract_field["blocking_issues"]:
        raise ContractError(f"{field_id}: unresolved contract axes: {'; '.join(contract_field['blocking_issues'])}")
    notes = decision.get("notes", "")
    if not isinstance(notes, str):
        raise ContractError(f"{field_id}: notes must be a string")
    result = empty_field(field_id)
    result.update({"status": status, "notes": notes, "failure_reason": None})
    checks = validate_checks(decision, contract_field, status)
    if checks:
        result["acceptance_checks"] = checks
    if status == "reported":
        evidence_rows = decision.get("evidence")
        if not isinstance(evidence_rows, list) or len(evidence_rows) != 1:
            raise ContractError(f"{field_id}: reported requires exactly one primary evidence object")
        evidence = validate_evidence(evidence_rows[0], paragraphs, field_id)
        if not source_in_scope(evidence["source_id"], contract_field["source_scope"]):
            raise ContractError(f"{field_id}: evidence source is outside compiled source scope")
        result.update(scalar_fields(decision, status))
        validate_scalar_verbatim(field_id, result["scalar"], result["verbatim_value"], evidence["quote"])
        result["modality"] = validate_modality(decision, contract_field)
        result.update({"paragraph_id": evidence["paragraph_id"], "quote": evidence["quote"], "evidence": [evidence]})
    elif status == "source_conflict":
        candidates = decision.get("conflict_candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            raise ContractError(f"{field_id}: source_conflict requires at least two conflict_candidates")
        normalized_candidates, all_evidence = [], []
        locations = set()
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ContractError(f"{field_id}: conflict candidate {index} must be an object")
            evidence = validate_evidence(candidate.get("evidence"), paragraphs, f"{field_id} conflict candidate {index}")
            if not source_in_scope(evidence["source_id"], contract_field["source_scope"]):
                raise ContractError(f"{field_id}: conflict evidence is outside compiled source scope")
            item = scalar_fields(candidate, status)
            validate_scalar_verbatim(field_id, item["scalar"], item["verbatim_value"], evidence["quote"])
            item["evidence"] = evidence
            normalized_candidates.append(item)
            all_evidence.append(evidence)
            locations.add((evidence["source_id"], evidence["paragraph_id"], evidence["quote"]))
        if len(locations) < 2:
            raise ContractError(f"{field_id}: conflict candidates need distinct evidence locations or quotes")
        result.update({"scalar": None, "units": None, "statistic": None,
                       "experimental_condition": None, "condition": None, "comparator": None,
                       "verbatim_value": None, "paragraph_id": None, "quote": None,
                       "evidence": all_evidence, "conflict_candidates": normalized_candidates,
                       "modality": validate_modality(decision, contract_field)})
    elif status == "not_reported":
        if contract_field["source_scope"] == UNSPECIFIED:
            raise ContractError(f"{field_id}: source scope must be resolved before declaring not_reported")
        search = decision.get("search_record")
        if not isinstance(search, dict) or not isinstance(search.get("paragraphs_searched"), list) or not search["paragraphs_searched"]:
            raise ContractError(f"{field_id}: not_reported requires a non-empty source-paragraph search record")
        if not isinstance(search.get("rationale"), str) or not search["rationale"].strip():
            raise ContractError(f"{field_id}: not_reported requires a search rationale")
        searched = []
        for item in search["paragraphs_searched"]:
            if not isinstance(item, dict) or not isinstance(item.get("source_id"), str) or not isinstance(item.get("paragraph_id"), str):
                raise ContractError(f"{field_id}: invalid searched paragraph reference")
            key = (item["source_id"], item["paragraph_id"])
            if key not in paragraphs:
                raise ContractError(f"{field_id}: searched paragraph is not registered: {key}")
            if not source_in_scope(key[0], contract_field["source_scope"]):
                raise ContractError(f"{field_id}: search record cites out-of-scope source {key[0]}")
            searched.append({"source_id": key[0], "paragraph_id": key[1], "page": paragraphs[key].get("page")})
        result["search_record"] = {"paragraphs_searched": searched, "rationale": search["rationale"]}
    else:  # extraction_failed
        reason = decision.get("failure_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ContractError(f"{field_id}: extraction_failed requires failure_reason")
        result["failure_reason"] = reason
        if "evidence" in decision:
            evidence_rows = decision["evidence"]
            if not isinstance(evidence_rows, list):
                raise ContractError(f"{field_id}: extraction_failed evidence must be a list")
            result["evidence"] = [validate_evidence(row, paragraphs, field_id) for row in evidence_rows]
    if "rejected_candidates" in decision:
        rejected = decision["rejected_candidates"]
        if not isinstance(rejected, list):
            raise ContractError(f"{field_id}: rejected_candidates must be a list")
        normalized_rejected = []
        for index, candidate in enumerate(rejected):
            if not isinstance(candidate, dict) or not isinstance(candidate.get("reason"), str) or not candidate["reason"].strip():
                raise ContractError(f"{field_id}: rejected candidate needs a semantic reason")
            item = {"reason": candidate["reason"], "verbatim_value": candidate.get("verbatim_value")}
            if "evidence" in candidate:
                item["evidence"] = validate_evidence(candidate["evidence"], paragraphs, f"{field_id} rejected candidate {index}")
            if "failed_test_id" in candidate:
                if candidate["failed_test_id"] not in check_id_set(contract_field):
                    raise ContractError(f"{field_id}: rejected candidate cites an unknown test")
                item["failed_test_id"] = candidate["failed_test_id"]
            normalized_rejected.append(item)
        result["rejected_candidates"] = normalized_rejected
    return result


def overall_status(fields: List[Dict[str, Any]]) -> str:
    if not fields:
        return "input_error"
    if any(field["status"] == "extraction_failed" for field in fields):
        return "partial" if any(field["status"] == "reported" for field in fields) else "insufficient_evidence"
    if all(field["status"] == "not_reported" for field in fields):
        return "insufficient_evidence"
    # Completed scoped absence and documented conflicts are adjudications.
    return "answered"


def claims_and_uncertainties(fields: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    claims, uncertainties = [], []
    for field in fields:
        field_id = field["field_id"]
        if field["status"] == "reported":
            evidence = field["evidence"][0]
            claims.append({
                "claim_id": f"claim::{field_id}", "field_id": field_id,
                "kind": field["modality"] if field["modality"] != "not_applicable" else "reported_field",
                "statement": field["verbatim_value"], "evidence": field["evidence"],
                "source_id": evidence["source_id"],
                "location": {"page": evidence["page"], "paragraph_id": evidence["paragraph_id"]},
            })
        else:
            kind = field["status"]
            message = field.get("failure_reason") or field.get("notes") or kind
            item = {"field_id": field_id, "kind": kind, "message": message}
            if field.get("search_record"):
                item["search_record"] = field["search_record"]
            if field.get("conflict_candidates"):
                item["candidate_count"] = len(field["conflict_candidates"])
            uncertainties.append(item)
    return claims, uncertainties


def markdown_report(result: Dict[str, Any], contract: Dict[str, Any], register: Dict[str, Any]) -> str:
    synthetic = result.get("synthetic") is True
    lines = [
        "# SYNTHETIC Field Acceptance Contract and Audit" if synthetic else "# Field Acceptance Contract and Audit",
        "",
        "**SYNTHETIC EXAMPLE — NOT A FORMAL TEST RESULT.**" if synthetic else "**Runtime input audit.**",
        "",
        f"- case_id: `{result['case_id']}`",
        f"- overall status: `{result['status']}`",
        f"- contract SHA-256: `{contract['contract_sha256']}`",
        "- compilation order: QUESTION/SCHEMA and tests precede source paragraph adjudication.",
        "- quote policy: exact quotation is necessary evidence integrity, never sufficient semantic proof.",
        "- selection policy: all values and semantic check rationales are agent-authored; the compiler does not keyword-rank candidates.",
        "",
        "## Pre-candidate acceptance contracts",
        "",
    ]
    for field in contract["fields"]:
        lines.extend([f"### `{field['field_id']}`", "", f"- field kind: `{field['field_kind']}`"])
        for axis in AXES:
            lines.append(f"- {axis}: `{display(field[axis])}`")
        if field["blocking_issues"]:
            lines.append(f"- blocking issues: {display(field['blocking_issues'])}")
        lines.extend(["", "Tests compiled before candidates:", ""])
        for test in field["acceptance_tests"]:
            lines.append(f"- `{test['test_id']}` ({test['evaluation']}): {test['requirement']}")
        lines.append("")
    lines.extend(["## Field adjudication audit", ""])
    for field in result["result"]["fields"]:
        lines.extend([f"### `{field['field_id']}` — `{field['status']}`", "",
                      f"- scalar: `{display(field['scalar'])}`; verbatim: `{display(field.get('verbatim_value'))}`",
                      f"- units: `{display(field['units'])}`; statistic: `{display(field['statistic'])}`",
                      f"- condition: `{display(field['experimental_condition'])}`; comparator: `{display(field['comparator'])}`",
                      f"- modality: `{display(field.get('modality'))}`",
                      f"- notes: {field.get('notes') or '(none)'}"])
        for check in field.get("acceptance_checks", []):
            lines.append(f"- PASS `{check['test_id']}`: {check['rationale']}")
        for rejected in field.get("rejected_candidates", []):
            lines.append(f"- REJECTED `{display(rejected.get('verbatim_value'))}` via `{rejected.get('failed_test_id', 'semantic review')}`: {rejected['reason']}")
        for candidate in field.get("conflict_candidates", []):
            evidence = candidate["evidence"]
            lines.append(f"- CONFLICT CANDIDATE `{display(candidate['verbatim_value'])}` at `{evidence['source_id']}/{evidence['paragraph_id']}` page `{display(evidence['page'])}`")
        for evidence in field.get("evidence", []):
            lines.append(f"- EVIDENCE `{evidence['source_id']}/{evidence['paragraph_id']}` page `{display(evidence['page'])}`: “{evidence['quote']}”")
        if field.get("search_record"):
            lines.append(f"- SEARCH RECORD: `{display(field['search_record']['paragraphs_searched'])}`; {field['search_record']['rationale']}")
        if field.get("failure_reason"):
            lines.append(f"- FAILURE: {field['failure_reason']}")
        lines.append("")
    lines.extend(["## Uncertainties", ""])
    if result["uncertainties"]:
        for item in result["uncertainties"]:
            lines.append(f"- `{display(item.get('field_id'))}` `{item['kind']}`: {item['message']}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Registered sources used for validation", ""])
    for source in register.get("sources", []):
        lines.append(f"- `{source['source_id']}`: {source.get('title', '(untitled)')}")
    lines.append("")
    return "\n".join(lines)


def command_finalize(args: argparse.Namespace) -> int:
    work, output = Path(args.work), Path(args.output)
    contract = read_json(work / "acceptance-contract.json")
    register = read_json(Path(args.source_register))
    adjudication = read_json(Path(args.decisions))
    if not isinstance(adjudication, dict) or adjudication.get("case_id") != contract["case_id"]:
        raise ContractError("adjudication case_id does not match contract")
    if adjudication.get("contract_sha256") != contract["contract_sha256"]:
        raise ContractError("adjudication is not bound to the current precompiled contract hash")
    sources, paragraphs = index_register(register)
    decisions = adjudication.get("decisions")
    if not isinstance(decisions, list):
        raise ContractError("adjudication requires a decisions list")
    by_id = {}
    for decision in decisions:
        if isinstance(decision, dict) and isinstance(decision.get("field_id"), str):
            if decision["field_id"] in by_id:
                raise ContractError(f"duplicate adjudication for {decision['field_id']}")
            by_id[decision["field_id"]] = decision
    expected_ids = [field["field_id"] for field in contract["fields"]]
    if set(by_id) != set(expected_ids) or len(by_id) != len(expected_ids):
        raise ContractError("adjudication must contain exactly one decision per target field_id")
    # Validate every field before replacing the conservative result.
    final_fields = [adjudicate_field(by_id[field["field_id"]], field, paragraphs) for field in contract["fields"]]
    claims, uncertainties = claims_and_uncertainties(final_fields)
    cited_ids = {row["source_id"] for field in final_fields for row in field.get("evidence", [])}
    cited_ids.update(row["source_id"] for field in final_fields
                     for row in field.get("search_record", {}).get("paragraphs_searched", []))
    source_rows = [copy.deepcopy(sources[source_id]) if source_id in sources else {"source_id": source_id}
                   for source_id in sorted(cited_ids)]
    result = {
        "case_id": contract["case_id"], "status": overall_status(final_fields),
        "synthetic": contract["synthetic"],
        "label": "SYNTHETIC EXAMPLE — NOT A FORMAL TEST RESULT" if contract["synthetic"] else "runtime result",
        "result": {"fields": copy.deepcopy(final_fields), "field_results": copy.deepcopy(final_fields)},
        "claims": claims, "uncertainties": uncertainties, "sources": source_rows,
        "change_records": [
            {"sequence": 1, "event": "conservative_skeleton_initialized", "candidate_values_read": False},
            {"sequence": 2, "event": "contract_compiled_before_candidate_adjudication",
             "contract_sha256": contract["contract_sha256"], "candidate_values_read": False},
            {"sequence": 3, "event": "agent_adjudication_validated_and_compiled",
             "decision_contract_sha256": adjudication["contract_sha256"],
             "source_register_sha256": canonical_hash(register)},
        ],
    }
    write_json(output / "result.json", result)
    report_path = output / "contract-audit.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown_report(result, contract, register))
    events_path = work / "runtime-events.json"
    if events_path.exists():
        events = read_json(events_path)
        events["events"].append({"sequence": len(events["events"]) + 1,
                                 "event": "source_register_and_agent_decisions_validated",
                                 "contract_sha256": contract["contract_sha256"],
                                 "candidate_values_read": True})
        write_json(events_path, events)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a full skeleton, then compile acceptance tests from question/schema")
    init.add_argument("--input-dir", default="/input")
    init.add_argument("--work", default="/app/work")
    init.add_argument("--output", default="/app/output")
    init.set_defaults(func=command_init)
    amend = sub.add_parser("amend-contract", help="resolve missing semantic axes using question/schema only")
    amend.add_argument("--work", default="/app/work")
    amend.add_argument("--amendments", required=True)
    amend.set_defaults(func=command_amend)
    final = sub.add_parser("finalize", help="validate exact evidence and agent decisions, then emit result and audit")
    final.add_argument("--work", default="/app/work")
    final.add_argument("--output", default="/app/output")
    final.add_argument("--source-register", required=True)
    final.add_argument("--decisions", required=True)
    final.set_defaults(func=command_finalize)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ContractError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
