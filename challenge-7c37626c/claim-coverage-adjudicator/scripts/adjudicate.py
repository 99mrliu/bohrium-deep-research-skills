#!/usr/bin/env python3
"""Fail-closed task-atom -> claim -> quote -> output-field adjudicator."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from coverage_common import (
    CLAIM_TYPES, COMPLETION_STATUSES, ORIGINS, RELATIONS, SCHEMA_VERSION,
    SYSTEM_FIELDS, contract_fields, issue, is_placeholder, normalize_answer,
    placeholder_paths, read_json, status_enum, validate_contract_shape, write_json,
)
from final_result import assemble_result


def top_output_field(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if value.startswith("/"):
        value = value[1:]
    return re_split_field(value)


def re_split_field(value: str) -> str:
    for separator in (".", "/"):
        value = value.split(separator, 1)[0]
    return value


def named_gaps(claim: Dict[str, Any]) -> bool:
    for field in ("missing_objects", "uncertainty"):
        values = claim.get(field)
        if isinstance(values, str) and not is_placeholder(values):
            return True
        if isinstance(values, list) and any(isinstance(v, str) and not is_placeholder(v) for v in values):
            return True
        if isinstance(values, dict) and any(isinstance(v, str) and not is_placeholder(v) for v in values.values()):
            return True
    return False


def adjudicate(case: Dict[str, Any], sources: Dict[str, Any],
               claims: Dict[str, Any], draft: Dict[str, Any], work: Path) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    excerpts = sources.get("excerpts")
    if not isinstance(excerpts, list):
        excerpts = []
        issues.append(issue("source_ledger_invalid", "source ledger excerpts must be an array"))
    excerpt_index = {
        excerpt.get("excerpt_id"): excerpt for excerpt in excerpts
        if isinstance(excerpt, dict) and isinstance(excerpt.get("excerpt_id"), str)
    }
    if sources.get("case_id") != case.get("case_id"):
        issues.append(issue("source_case_id_mismatch", "source ledger belongs to a different case"))
    if claims.get("case_id") != case.get("case_id"):
        issues.append(issue("claims_case_id_mismatch", "claims ledger belongs to a different case"))
    if draft.get("case_id") != case.get("case_id"):
        issues.append(issue("draft_case_id_mismatch", "result draft belongs to a different case"))

    verified_evidence_keys: Set[Tuple[Any, ...]] = set()

    def check_evidence(record: Any, owner: str) -> Tuple[List[Dict[str, Any]], bool]:
        local: List[Dict[str, Any]] = []
        if not isinstance(record, dict):
            return [issue("evidence_not_object", "evidence record must be an object", owner=owner)], False
        for field in ("excerpt_id", "source_file", "locator", "quote"):
            if not isinstance(record.get(field), str) or not record.get(field):
                local.append(issue("missing_evidence_field", "evidence requires nonempty " + field,
                                   owner=owner, field=field))
        relation = record.get("relation")
        if relation not in RELATIONS:
            local.append(issue("evidence_relation_invalid", "relation must be supports, refutes, or context",
                               owner=owner))
        excerpt_id = record.get("excerpt_id")
        excerpt = excerpt_index.get(excerpt_id)
        if not isinstance(excerpt_id, str) or not excerpt_id:
            local.append(issue("missing_source_id", "evidence must name a source excerpt_id", owner=owner))
        elif excerpt is None:
            local.append(issue("unknown_source_excerpt", "excerpt_id is absent from the normalized ledger",
                               owner=owner, excerpt_id=excerpt_id))
        if excerpt is not None:
            if record.get("source_file") != excerpt.get("source_file"):
                local.append(issue("evidence_source_mismatch",
                                   "source_file does not equal the claimed excerpt source", owner=owner))
            if record.get("locator") != excerpt.get("locator"):
                local.append(issue("evidence_locator_mismatch",
                                   "locator does not equal the claimed excerpt locator", owner=owner))
            quote = record.get("quote")
            if not isinstance(quote, str) or quote not in excerpt.get("text", ""):
                local.append(issue("quote_not_in_excerpt",
                                   "quote must occur verbatim, case-sensitively, in the claimed excerpt",
                                   owner=owner, excerpt_id=excerpt_id))
            excerpt_formula_id = excerpt.get("formula_source_id")
            record_formula_id = record.get("formula_source_id")
            if excerpt_formula_id and not record_formula_id:
                local.append(issue("missing_formula_source_id",
                                   "MathML evidence must copy the excerpt formula_source_id", owner=owner))
            elif excerpt_formula_id and record_formula_id != excerpt_formula_id:
                local.append(issue("formula_source_id_mismatch",
                                   "formula_source_id does not match the claimed MathML excerpt", owner=owner))
        if local:
            return local, False
        verified_evidence_keys.add((owner, record.get("excerpt_id"), record.get("quote"),
                                    record.get("relation")))
        return [], True

    atoms = claims.get("task_atoms")
    if not isinstance(atoms, list) or not atoms:
        issues.append(issue("no_task_atoms", "agent must author at least one exact task atom"))
        atoms = []
    atom_ids: Set[str] = set()
    claim_ids: Set[str] = set()
    supported_formula_ids: Set[str] = set()
    output_targets: Set[str] = set()
    substantive_central_claims = 0
    completed_atoms: Set[str] = set()
    contradiction_groups: Dict[Tuple[str, str], List[Tuple[str, str]]] = collections.defaultdict(list)
    missing_objects = {
        value for value in sources.get("missing_objects") or [] if isinstance(value, str)
    }

    for atom_index, atom in enumerate(atoms):
        owner = "task_atoms[%d]" % atom_index
        if not isinstance(atom, dict):
            issues.append(issue("task_atom_not_object", "task atom must be an object", owner=owner))
            continue
        atom_id = atom.get("atom_id")
        owner = "atom:%s" % atom_id
        if not isinstance(atom_id, str) or not atom_id:
            issues.append(issue("missing_atom_id", "every task atom needs atom_id", owner=owner))
            continue
        if atom_id in atom_ids:
            issues.append(issue("duplicate_atom_id", "atom_id must be unique", atom_id=atom_id))
        atom_ids.add(atom_id)
        if not isinstance(atom.get("exact_requirement"), str) or is_placeholder(atom.get("exact_requirement")):
            issues.append(issue("inexact_requirement", "task atom needs its exact, nonempty requirement",
                                atom_id=atom_id))
        atom_outputs = atom.get("output_fields")
        if not isinstance(atom_outputs, list) or not atom_outputs:
            issues.append(issue("atom_output_fields_missing", "task atom must target output_fields",
                                atom_id=atom_id))
            atom_outputs = []
        for target in atom_outputs:
            if top_output_field(target):
                output_targets.add(top_output_field(target))
            else:
                issues.append(issue("invalid_output_field_target",
                                    "atom output_fields entries must be nonempty field paths",
                                    atom_id=atom_id))
        atom_claims = atom.get("claims")
        if not isinstance(atom_claims, list) or not atom_claims:
            issues.append(issue("atom_has_no_claims", "task atom has no authored claims", atom_id=atom_id))
            continue

        for claim_index, claim in enumerate(atom_claims):
            claim_owner = "%s.claims[%d]" % (owner, claim_index)
            if not isinstance(claim, dict):
                issues.append(issue("claim_not_object", "claim must be an object", owner=claim_owner))
                continue
            claim_id = claim.get("claim_id")
            claim_owner = "claim:%s" % claim_id
            central_value = claim.get("central", True)
            if isinstance(central_value, bool):
                central = central_value
            else:
                central = True
                issues.append(issue("central_flag_invalid", "central must be a boolean; failing closed",
                                    claim_id=claim_id))
            if not isinstance(claim_id, str) or not claim_id:
                issues.append(issue("missing_claim_id", "every claim needs claim_id", atom_id=atom_id))
                continue
            if claim_id in claim_ids:
                issues.append(issue("duplicate_claim_id", "claim_id must be globally unique", claim_id=claim_id))
            claim_ids.add(claim_id)
            answer = claim.get("answer")
            substantive = not is_placeholder(answer) and not (
                isinstance(answer, (dict, list)) and not answer
            ) and not placeholder_paths(answer, "answer")
            if central and substantive:
                substantive_central_claims += 1
            claim_type = claim.get("claim_type")
            completion = claim.get("completion_status")
            origin = claim.get("origin")
            if claim_type not in CLAIM_TYPES:
                issues.append(issue("claim_type_invalid", "unknown claim_type", claim_id=claim_id))
            if completion not in COMPLETION_STATUSES:
                issues.append(issue("completion_status_invalid", "unknown completion_status", claim_id=claim_id))
            if origin not in ORIGINS:
                issues.append(issue("origin_invalid", "origin must be reported or inference", claim_id=claim_id))
            if central and not substantive:
                issues.append(issue("placeholder_claim_answer", "central answer is empty or placeholder text",
                                    claim_id=claim_id, atom_id=atom_id))
            claim_outputs = claim.get("output_fields")
            if not isinstance(claim_outputs, list) or not claim_outputs:
                issues.append(issue("claim_output_fields_missing", "claim must target output_fields",
                                    claim_id=claim_id))
                claim_outputs = []
            for target in claim_outputs:
                if top_output_field(target):
                    output_targets.add(top_output_field(target))
                else:
                    issues.append(issue("invalid_output_field_target",
                                        "claim output_fields entries must be nonempty field paths",
                                        claim_id=claim_id))

            evidence_records = claim.get("evidence")
            if not isinstance(evidence_records, list):
                evidence_records = []
                issues.append(issue("evidence_array_missing", "claim evidence must be an array",
                                    claim_id=claim_id))
            valid_supports: List[Dict[str, Any]] = []
            valid_refutes: List[Dict[str, Any]] = []
            for evidence_index, record in enumerate(evidence_records):
                record_owner = "%s.evidence[%d]" % (claim_owner, evidence_index)
                evidence_issues, valid = check_evidence(record, record_owner)
                issues.extend(evidence_issues)
                if valid and record.get("relation") == "supports":
                    valid_supports.append(record)
                if valid and record.get("relation") == "refutes":
                    valid_refutes.append(record)
            if valid_refutes and central:
                issues.append(issue("refuted_central_claim",
                                    "central claim has verbatim refuting evidence; do not silently collapse it",
                                    claim_id=claim_id, atom_id=atom_id))
            if central and completion == "refuted":
                issues.append(issue("refuted_central_claim", "central claim is marked refuted",
                                    claim_id=claim_id, atom_id=atom_id))

            transparent_inference = True
            if origin == "inference":
                inference = claim.get("inference") if isinstance(claim.get("inference"), dict) else {}
                prerequisites = claim.get("inference_prerequisites", inference.get("prerequisites"))
                rationale = claim.get("inference_rationale", inference.get("rationale"))
                transparent_inference = (
                    isinstance(prerequisites, list) and bool(prerequisites)
                    and all(isinstance(item, str) and not is_placeholder(item) for item in prerequisites)
                    and isinstance(rationale, str) and not is_placeholder(rationale)
                )
                if substantive and not transparent_inference:
                    issues.append(issue("opaque_inference",
                                        "inference needs explicit prerequisites and inference_rationale",
                                        claim_id=claim_id))
            supported = bool(valid_supports) and (origin != "inference" or transparent_inference)
            if substantive and completion not in {"refuted", "insufficient_evidence", "not_started"} and not supported:
                issues.append(issue("unsupported_substantive_claim",
                                    "substantive answer lacks direct verified support or transparent supported inference",
                                    claim_id=claim_id, atom_id=atom_id))
            if central and completion != "completed":
                issues.append(issue("incomplete_central_claim", "central claim is not completed",
                                    claim_id=claim_id, atom_id=atom_id, completion_status=completion))
                if not named_gaps(claim):
                    issues.append(issue("unnamed_completion_gap",
                                        "partial/insufficient central claim must name uncertainty or missing objects",
                                        claim_id=claim_id, atom_id=atom_id))
            if central and completion == "completed" and substantive and supported:
                completed_atoms.add(atom_id)

            formula_id = claim.get("formula_source_id")
            if claim_type == "formula":
                if not isinstance(formula_id, str) or not formula_id:
                    issues.append(issue("missing_formula_source_id", "formula claim needs formula_source_id",
                                        claim_id=claim_id))
                else:
                    matching_support = any(
                        record.get("formula_source_id") == formula_id
                        and excerpt_index.get(record.get("excerpt_id"), {}).get("formula_source_id") == formula_id
                        for record in valid_supports
                    )
                    if completion == "completed" and supported and matching_support:
                        supported_formula_ids.add(formula_id)
                    elif substantive and completion == "completed":
                        issues.append(issue("formula_evidence_id_mismatch",
                                            "formula answer needs MathML support with the same source ID",
                                            claim_id=claim_id, formula_source_id=formula_id))
                if completion == "completed" and "formula representation" in missing_objects:
                    issues.append(issue("formula_object_missing",
                                        "cannot complete formula transcription when formula representation is missing",
                                        claim_id=claim_id))
            if claim_type == "derivation" and completion == "completed" and any(
                    gap.startswith("derivation objects") for gap in missing_objects):
                issues.append(issue("derivation_object_missing",
                                    "cannot complete requested derivation without derivation objects",
                                    claim_id=claim_id))
            if (claim_type == "numeric" and origin == "inference" and completion == "completed"
                    and "recalculable raw data or explicit numeric inputs" in missing_objects):
                issues.append(issue("numeric_recalculation_impossible",
                                    "metrics-only evidence cannot support a derived recalculation",
                                    claim_id=claim_id))

            group = claim.get("contradiction_group")
            if central and completion == "completed" and substantive and isinstance(group, str) and group:
                contradiction_groups[(atom_id, group)].append((claim_id, normalize_answer(answer)))

    for atom_id in atom_ids:
        if atom_id not in completed_atoms:
            issues.append(issue("task_atom_not_completed",
                                "no completed, substantive, supported central claim closes this task atom",
                                atom_id=atom_id))

    requested_ids = sources.get("requested_formula_ids") or []
    discovered_ids = set(sources.get("formula_source_ids") or [])
    for formula_id in requested_ids:
        if formula_id not in discovered_ids:
            issues.append(issue("requested_formula_source_missing",
                                "requested formula ID is absent from actual MathML excerpts",
                                formula_source_id=formula_id))
        if formula_id not in supported_formula_ids:
            issues.append(issue("requested_formula_uncovered_or_unsupported",
                                "every requested formula needs a completed, supported formula claim",
                                formula_source_id=formula_id))

    contradictions = claims.get("contradictions")
    if not isinstance(contradictions, list):
        issues.append(issue("contradictions_not_array", "contradictions must be an array"))
        contradictions = []
    for index, contradiction in enumerate(contradictions):
        owner = "contradictions[%d]" % index
        if not isinstance(contradiction, dict):
            issues.append(issue("contradiction_not_object", "contradiction must be an object", owner=owner))
            continue
        state = contradiction.get("status", "unresolved")
        if state == "unresolved":
            issues.append(issue("unresolved_contradiction",
                                contradiction.get("description") or "declared contradiction remains unresolved",
                                contradiction_id=contradiction.get("contradiction_id")))
        elif state == "resolved":
            if is_placeholder(contradiction.get("resolution")):
                issues.append(issue("invalid_contradiction_resolution",
                                    "resolved contradiction needs a substantive resolution",
                                    contradiction_id=contradiction.get("contradiction_id")))
            records = contradiction.get("resolution_evidence")
            valid_resolution = False
            if isinstance(records, list):
                for evidence_index, record in enumerate(records):
                    evidence_issues, valid = check_evidence(
                        record, "%s.resolution_evidence[%d]" % (owner, evidence_index))
                    issues.extend(evidence_issues)
                    valid_resolution = valid_resolution or (valid and record.get("relation") == "supports")
            if not valid_resolution:
                issues.append(issue("unsupported_contradiction_resolution",
                                    "resolution needs at least one verified supports quote",
                                    contradiction_id=contradiction.get("contradiction_id")))
        else:
            issues.append(issue("contradiction_status_invalid", "status must be unresolved or resolved",
                                contradiction_id=contradiction.get("contradiction_id")))

    for (atom_id, group), members in contradiction_groups.items():
        answers = {answer for _, answer in members}
        if len(answers) > 1:
            issues.append(issue("unresolved_contradiction",
                                "completed central claims in the same contradiction_group have different answers",
                                atom_id=atom_id, contradiction_group=group,
                                claim_ids=[claim_id for claim_id, _ in members]))

    no_objects = substantive_central_claims == 0
    proposed_status = "insufficient_evidence" if no_objects else "success"
    candidate = assemble_result(case, draft, claims, proposed_status, issues, work)
    issues.extend(validate_contract_shape(candidate, case))
    required = contract_fields(case)
    for field in required:
        if field in SYSTEM_FIELDS:
            continue
        value = candidate.get(field)
        if value is None or value == "" or value == {} or value == []:
            issues.append(issue("empty_output_field", "required content output field is empty", field=field))
        paths = placeholder_paths(value, field)
        if paths:
            issues.append(issue("placeholder_output_value",
                                "placeholder/null text does not count as substantive output",
                                field=field, paths=paths))
        if field not in output_targets:
            issues.append(issue("uncovered_output_field",
                                "no task atom or claim targets this content output field", field=field))

    if issues and not no_objects:
        final_status = "partial"
    else:
        final_status = proposed_status
    allowed = status_enum(case)
    if "success" not in allowed and final_status == "success":
        issues.append(issue("success_not_in_status_enum", "contract does not permit success"))
        final_status = "partial" if "partial" in allowed else allowed[0]
    report = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.get("case_id"),
        "recommended_status": final_status,
        "success": final_status == "success" and not issues,
        "task_atom_count": len(atom_ids),
        "completed_task_atoms": sorted(completed_atoms),
        "substantive_central_claim_count": substantive_central_claims,
        "requested_formula_ids": requested_ids,
        "supported_formula_ids": sorted(supported_formula_ids),
        "covered_output_fields": sorted(output_targets),
        "verified_evidence_record_count": len(verified_evidence_keys),
        "issue_count": len(issues),
        "issues": issues,
        "manual_review_required": [
            "Does each quote semantically entail its claim, rather than merely share words?",
            "Do the authored atoms cover every clause of the actual task beyond automatic formula-ID checks?",
            "Are derivations, calculations, units, and any contradiction resolutions scientifically correct?",
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--sources")
    parser.add_argument("--claims")
    parser.add_argument("--draft")
    parser.add_argument("--report")
    args = parser.parse_args()
    work = Path(args.work)
    paths = {
        "case": Path(args.case),
        "source ledger": Path(args.sources) if args.sources else work / "source_excerpts.json",
        "claims ledger": Path(args.claims) if args.claims else work / "claims.json",
        "result draft": Path(args.draft) if args.draft else work / "result.draft.json",
    }
    try:
        case, sources, claims, draft = (read_json(paths[name]) for name in
                                        ("case", "source ledger", "claims ledger", "result draft"))
        if not all(isinstance(value, dict) for value in (case, sources, claims, draft)):
            raise ValueError("case, source ledger, claims ledger, and result draft must be JSON objects")
    except Exception as exc:
        print("adjudicate: input error: %s" % exc, file=sys.stderr)
        return 2
    report = adjudicate(case, sources, claims, draft, work)
    report_path = Path(args.report) if args.report else work / "adjudication.json"
    write_json(report_path, report)
    print("adjudicate: status=%s issues=%d report=%s" % (
        report["recommended_status"], report["issue_count"], report_path))
    for item in report["issues"]:
        print("- %s: %s" % (item["code"], item["message"]))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
