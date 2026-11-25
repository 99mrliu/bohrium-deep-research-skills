#!/usr/bin/env python3
"""Finalize the four-item primary task, with optional real-review diagnostics.

The case.json output_contract is authoritative. Human verdicts are never required
for a successful four-item benchmark-DRAFT delivery and are never synthesized.
"""

import argparse
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "1.1"
REVIEW_NOT_CONDUCTED = "not_conducted_no_human_verdicts"
REVIEW_ARGUMENTS = ("adjudication", "agreement", "failures", "targeted_probes")


class InputError(ValueError):
    pass


def load_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"Cannot read valid JSON from {path}: {exc}") from exc


def dump_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def parse_field_list(values, label):
    fields = []
    for position, value in enumerate(values, 1):
        if isinstance(value, str):
            field = value
        elif isinstance(value, dict):
            field = value.get("name")
        else:
            raise InputError(f"{label}[{position}] must be a string or an object with name")
        if not isinstance(field, str) or not field.strip():
            raise InputError(f"{label}[{position}] has an empty or non-string name")
        fields.append(field)
    return fields


def contract_fields(case):
    """Read every supported case.output_contract shape, never task prose/metadata."""
    contract = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(contract, list):
        fields = parse_field_list(contract, "case.output_contract")
    elif isinstance(contract, dict) and isinstance(contract.get("fields"), list):
        fields = parse_field_list(contract["fields"], "case.output_contract.fields")
    elif isinstance(contract, dict) and isinstance(contract.get("required_top_level_fields"), list):
        fields = parse_field_list(
            contract["required_top_level_fields"],
            "case.output_contract.required_top_level_fields",
        )
    elif isinstance(contract, dict) and isinstance(contract.get("properties"), dict):
        fields = list(contract["properties"])
    elif isinstance(contract, dict):
        # A direct field -> description/schema map.
        fields = list(contract)
    else:
        raise InputError(
            "case.output_contract must be a field list, a fields/required_top_level_fields "
            "object, a properties object, or a direct field map"
        )
    if not fields or any(not isinstance(field, str) or not field for field in fields):
        raise InputError("Every output_contract field must be a nonempty string")
    if len(fields) != len(set(fields)):
        raise InputError("output_contract has duplicate top-level fields")
    # The runtime requires case_id and status even when the contract does not
    # redundantly declare them. They are appended at export, not treated as
    # missing user-authored contract content.
    return fields


def minimal_review_artifact(case_id, kind, review_status=REVIEW_NOT_CONDUCTED):
    status = "not_applicable" if review_status == REVIEW_NOT_CONDUCTED else "partial"
    reason = (
        "No actual human reviewer verdict artifacts were supplied; optional review was not conducted."
        if review_status == REVIEW_NOT_CONDUCTED
        else "The optional review artifact set is incomplete; no completion or calibration is claimed."
    )
    if kind == "adjudication":
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "status": status,
            "review_status": review_status,
            "reason": reason,
            "expected_verdict_count": 0,
            "accepted_verdict_count": 0,
            "human_verdicts": [],
            "pairwise_disagreements": [],
            "per_item": [],
            "adjudications": [],
            "missing_verdicts": [],
            "duplicate_verdicts": [],
            "late_verdicts": [],
            "malformed_verdicts": [],
            "unknown_id_records": [],
            "duplicate_adjudications": [],
            "unresolved_items": [],
        }
    if kind == "agreement":
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "status": status,
            "review_status": review_status,
            "reason": reason,
            "counts": {
                "total_items": 4,
                "comparable_items": 0,
                "unresolved_or_missing_finals": 0,
                "matches": 0,
                "mismatches": 0,
            },
            "raw_agreement": {
                "status": "not_applicable",
                "value": None,
                "numerator": 0,
                "denominator": 0,
                "reason": reason,
            },
            "cohen_kappa_unweighted": {
                "status": "not_computed_no_human_verdicts" if status == "not_applicable" else "not_computed_review_incomplete",
                "value": None,
                "reason": reason,
            },
            "per_item": [],
            "unresolved_missing": [],
        }
    if kind == "failures":
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "status": status,
            "review_status": review_status,
            "reason": reason,
            "failures": [],
        }
    if kind == "targeted_probes":
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "status": status,
            "review_status": review_status,
            "reason": reason,
            "probes": [],
        }
    raise ValueError(f"Unknown review artifact kind: {kind}")


def initial_partial(fields, case_id, reason):
    result = {field: None for field in fields}
    result["case_id"] = case_id
    result["status"] = "partial"
    if "main_task_status" in result:
        result["main_task_status"] = "partial"
    if "review_status" in result:
        result["review_status"] = REVIEW_NOT_CONDUCTED
    if "adjudication" in result:
        result["adjudication"] = minimal_review_artifact(case_id, "adjudication")
    if "agreement" in result:
        result["agreement"] = minimal_review_artifact(case_id, "agreement")
    if "uncertainty" in result:
        result["uncertainty"] = [
            {"type": "workflow_incomplete", "statement": reason},
            {"type": "human_review_unavailable", "review_status": REVIEW_NOT_CONDUCTED,
             "statement": "No actual reviewer verdicts have been supplied at initialization; none will be invented."},
        ]
    if "change_records" in result:
        result["change_records"] = [{
            "stage": "initialization",
            "status": "partial",
            "review_status": REVIEW_NOT_CONDUCTED,
            "change": "Created every required top-level case.output_contract field before item derivation or optional review; placeholders are not claimed findings.",
        }]
    if "summary" in result:
        result["summary"] = {
            "status": "partial",
            "main_task_status": "partial",
            "review_status": REVIEW_NOT_CONDUCTED,
            "reason": reason,
            "items_completed": 0,
        }
    if "diagnostics" in result:
        result["diagnostics"] = {
            "main_task_status": "partial",
            "review_status": REVIEW_NOT_CONDUCTED,
            "items_completed": 0,
            "human_verdicts_supplied": False,
            "reason": reason,
        }
    return result


def require_object(document, label):
    if not isinstance(document, dict):
        raise InputError(f"{label} must be a JSON object")


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be nonempty text")


def validate_primary_documents(item_bank, sources, case_id):
    """Validate, but never rewrite or invent, the four scientific draft items."""
    require_object(item_bank, "item bank")
    require_object(sources, "source evidence")
    items = item_bank.get("items")
    source_rows = sources.get("sources")
    if not isinstance(items, list) or len(items) != 4:
        raise InputError("Primary finalization requires exactly four item-bank items")
    if not isinstance(source_rows, list) or not source_rows:
        raise InputError("Primary finalization requires a nonempty sources list")
    for document, label in ((item_bank, "item bank"), (sources, "source evidence")):
        document_case_id = document.get("case_id")
        if document_case_id is not None and document_case_id != case_id:
            raise InputError(f"{label} case_id does not match case.json")
    if item_bank.get("benchmark_item_stage") not in (None, "benchmark-DRAFT"):
        raise InputError("item bank must identify its stage as benchmark-DRAFT")

    source_index = {}
    for position, source in enumerate(source_rows, 1):
        require_object(source, f"source row {position}")
        source_id = source.get("source_id")
        require_text(source_id, f"source row {position} source_id")
        if source_id in source_index:
            raise InputError(f"Duplicate source ID: {source_id}")
        require_text(source.get("title"), f"Source {source_id} title")
        excerpts = source.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts:
            raise InputError(f"Source {source_id} requires a nonempty excerpts list")
        excerpt_index = {}
        for excerpt in excerpts:
            require_object(excerpt, f"Source {source_id} excerpt")
            locator = excerpt.get("locator")
            require_text(locator, f"Source {source_id} excerpt locator")
            require_text(excerpt.get("text"), f"Source {source_id} / {locator} text")
            if locator in excerpt_index:
                raise InputError(f"Duplicate locator {source_id} / {locator}")
            excerpt_index[locator] = excerpt
        source_index[source_id] = excerpt_index

    item_ids = []
    for position, item in enumerate(items, 1):
        require_object(item, f"item row {position}")
        item_id = item.get("item_id")
        require_text(item_id, f"item row {position} item_id")
        if item_id in item_ids:
            raise InputError(f"Duplicate item ID: {item_id}")
        item_ids.append(item_id)
        require_text(item.get("prompt"), f"Item {item_id} prompt")
        require_text(item.get("reference_answer"), f"Item {item_id} reference_answer")
        rubric = item.get("rubric")
        require_object(rubric, f"Item {item_id} rubric")
        for level in ("0", "1", "2"):
            require_text(rubric.get(level), f"Item {item_id} rubric level {level}")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise InputError(f"Item {item_id} requires nonempty evidence_refs")
        for ref in refs:
            require_object(ref, f"Item {item_id} evidence ref")
            source_id, locator = ref.get("source_id"), ref.get("locator")
            if source_id not in source_index or locator not in source_index.get(source_id, {}):
                raise InputError(f"Item {item_id} has unknown evidence ref {source_id} / {locator}")
    return item_ids


def validate_review_document(document, label, list_key=None):
    require_object(document, label)
    if list_key is not None and not isinstance(document.get(list_key), list):
        raise InputError(f"{label} lacks a {list_key} list")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Authoritative /input/case.json; task.md is prose only")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--early-partial", action="store_true", help="Write contract-complete initialization partial and exit")
    parser.add_argument("--item-bank")
    parser.add_argument("--source-evidence")
    parser.add_argument("--adjudication", help="Optional artifact produced from actual human verdicts")
    parser.add_argument("--agreement", help="Optional automatic/final comparison artifact")
    parser.add_argument("--failures", help="Optional mismatch failure artifact")
    parser.add_argument("--targeted-probes", help="Optional targeted probe artifact")
    args = parser.parse_args()

    try:
        case = load_json(args.case)
        require_object(case, "case.json")
        fields = contract_fields(case)
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise InputError("case.case_id must be a nonempty string")
        if case.get("fixed_case_count") not in (None, 4):
            raise InputError("case.fixed_case_count must be four for this skill")
        output_path = Path(args.output_dir) / "result.json"
        if args.early_partial:
            result = initial_partial(
                fields,
                case_id,
                "Four-item source derivation/export has not completed; optional human review has not been supplied.",
            )
            dump_json(output_path, result)
            print(json.dumps({
                "status": "partial",
                "main_task_status": "partial",
                "review_status": REVIEW_NOT_CONDUCTED,
                "early_partial": True,
                "top_level_fields": fields,
            }, ensure_ascii=False))
            return 0

        primary_absent = [name for name in ("item_bank", "source_evidence") if not getattr(args, name)]
        if primary_absent:
            raise InputError(f"Primary finalization requires arguments: {primary_absent}")
        item_bank = load_json(args.item_bank)
        sources = load_json(args.source_evidence)
        item_ids = validate_primary_documents(item_bank, sources, case_id)

        supplied_paths = {name: getattr(args, name) for name in REVIEW_ARGUMENTS}
        review_supplied = any(supplied_paths.values())
        documents = {}
        for name in REVIEW_ARGUMENTS:
            if supplied_paths[name]:
                documents[name] = load_json(supplied_paths[name])
            else:
                documents[name] = minimal_review_artifact(
                    case_id,
                    name,
                    "partial" if review_supplied else REVIEW_NOT_CONDUCTED,
                )
        adjudication = documents["adjudication"]
        agreement = documents["agreement"]
        failures = documents["failures"]
        probes = documents["targeted_probes"]
        validate_review_document(adjudication, "adjudication.json", "per_item")
        validate_review_document(agreement, "agreement.json", "per_item")
        validate_review_document(failures, "failures.json", "failures")
        validate_review_document(probes, "targeted_probes.json", "probes")

        review_limitations = []
        if not review_supplied:
            review_status = REVIEW_NOT_CONDUCTED
        else:
            missing_artifacts = [name for name in REVIEW_ARGUMENTS if not supplied_paths[name]]
            if missing_artifacts:
                review_limitations.append(f"Optional review artifact set is incomplete; missing: {missing_artifacts}.")
            if supplied_paths["adjudication"]:
                if adjudication.get("status") != "success":
                    review_limitations.append("Independent review/adjudication is incomplete or unresolved.")
                unresolved = adjudication.get("unresolved_items") or []
                if unresolved:
                    review_limitations.append(
                        f"Unresolved adjudications: {[row.get('item_id') for row in unresolved]}"
                    )
                for field in (
                    "missing_verdicts", "duplicate_verdicts", "late_verdicts",
                    "malformed_verdicts", "unknown_id_records", "duplicate_adjudications",
                ):
                    if adjudication.get(field):
                        review_limitations.append(f"Review data-quality issue requires correction: {field}.")
                per_item = adjudication.get("per_item", [])
                if len(per_item) != 4 or any(
                    row.get("status") != "resolved" or row.get("final_score") not in (0, 1, 2)
                    for row in per_item
                ):
                    review_limitations.append("The optional review does not contain exactly four resolved final scores in {0,1,2}.")
                for final in per_item:
                    if final.get("adjudication_required") and not isinstance(final.get("adjudication"), dict):
                        review_limitations.append(f"Missing explicit adjudication artifact for {final.get('item_id')}.")
            if supplied_paths["agreement"] and agreement.get("status") != "success":
                review_limitations.append("Automatic-final comparison has unresolved or missing finals.")
            if all(supplied_paths.values()):
                mismatch_count = agreement.get("counts", {}).get("mismatches", 0)
                if mismatch_count != len(failures["failures"]) or mismatch_count != len(probes["probes"]):
                    review_limitations.append(
                        "Every automatic-final mismatch must have exactly one failure case and targeted probe before review is complete."
                    )
            review_status = "partial" if review_limitations else "conducted"

        per_item = adjudication.get("per_item", [])
        finals = {
            row.get("item_id"): row for row in per_item
            if isinstance(row, dict) and isinstance(row.get("item_id"), str)
        }
        complete_items = []
        for item in item_bank["items"]:
            enriched = dict(item)
            review = finals.get(item.get("item_id"), {})
            enriched["adjudicated_final_score"] = review.get("final_score")
            enriched["adjudication_status"] = (
                review.get("status", "unresolved") if review_supplied else "not_applicable_no_human_verdicts"
            )
            complete_items.append(enriched)

        raw_agreements = agreement.get("per_item", [])
        if not review_supplied and not raw_agreements:
            raw_agreements = [{
                "item_id": item_id,
                "comparison_status": "not_applicable_no_human_verdicts",
                "automatic_score": None,
                "adjudicated_final_score": None,
                "raw_agreement_match": None,
                "reason": "No actual human final exists; no agreement, disagreement, or kappa is claimed.",
            } for item_id in item_ids]
            agreement["per_item"] = raw_agreements

        synthetic = any(source.get("synthetic") is True for source in sources["sources"])
        uncertainty = [{
            "type": "reference_provenance",
            "statement": "The four prompts, agent-derived reference answers, 0/1/2 rubrics, and source locators were validated and preserved from the supplied item bank; finalization does not invent or alter scientific content.",
        }]
        if review_supplied:
            uncertainty.append({
                "type": "small_synthetic_example" if synthetic else "small_sample",
                "statement": "Any supplied four-item human comparison is descriptive only; raw agreement and kappa are not population reliability estimates or proof of truth.",
            })
        else:
            uncertainty.append({
                "type": "human_review_unavailable",
                "review_status": REVIEW_NOT_CONDUCTED,
                "statement": "No actual human reviewer verdicts were supplied. Optional blind adjudication, automatic-final agreement, and human kappa were not conducted; this does not block the complete four-item bank.",
            })
        if review_limitations:
            uncertainty.append({
                "type": "optional_review_limitations",
                "review_status": review_status,
                "statements": sorted(set(review_limitations)),
                "statement": "Review remains partial/uncertain; no completed adjudication or calibration is claimed. Main item-bank status is determined separately.",
            })
        if agreement.get("unresolved_missing"):
            uncertainty.append({"type": "unresolved_missing_agreement", "items": agreement["unresolved_missing"]})

        # Main status is deliberately independent of optional human-review status.
        status = "success"
        mismatch_count = agreement.get("counts", {}).get("mismatches") if review_supplied else None
        summary = {
            "status": status,
            "main_task_status": status,
            "review_status": review_status,
            "total_items": 4,
            "items_completed": 4,
            "benchmark_item_stage": "benchmark-DRAFT",
            "required_item_components": {
                "questions": True,
                "reference_answers": True,
                "rubrics_0_1_2": True,
                "evidence_refs": True,
                "sources": True,
                "uncertainty": True,
                "change_records": True,
            },
            "resolved_items": sum(1 for row in per_item if row.get("status") == "resolved"),
            "unresolved_items": len(adjudication.get("unresolved_items") or []),
            "pairwise_disagreements": len(adjudication.get("pairwise_disagreements", [])),
            "automatic_final_matches": agreement.get("counts", {}).get("matches") if review_supplied else None,
            "automatic_final_mismatches": mismatch_count,
            "failure_cases": len(failures["failures"]),
            "targeted_probes": len(probes["probes"]),
            "human_kappa_status": agreement.get("cohen_kappa_unweighted", {}).get("status"),
            "success_rule": "success requires exactly four valid source-conditioned benchmark-DRAFT items and bindings for every case.output_contract field; optional human review never blocks this primary status",
            "blocking_reasons": [],
            "review_limitations": sorted(set(review_limitations)),
        }
        change_records = [
            {
                "stage": "derive_item_bank",
                "status": "success",
                "change": "Validated and preserved exactly four supplied source-conditioned benchmark-DRAFT items, reference answers, 0/1/2 rubrics, evidence locators, sources, and uncertainties.",
            },
            {
                "stage": "blind_adjudication",
                "status": "not_applicable" if not review_supplied else adjudication.get("status"),
                "review_status": review_status,
                "change": (
                    "No actual human verdicts were supplied; review was not conducted and no human labels or kappa were fabricated."
                    if not review_supplied else
                    f"Processed only supplied actual-review artifacts; resolved {summary['resolved_items']}/4 review items. Review limitations do not alter primary item-bank success."
                ),
            },
            {
                "stage": "agreement",
                "status": "not_applicable" if not review_supplied else agreement.get("status"),
                "review_status": review_status,
                "change": (
                    "No automatic-final comparison or human kappa was calculated without actual human finals."
                    if not review_supplied else
                    f"Preserved supplied raw comparisons, {len(failures['failures'])} mismatch failures, and {len(probes['probes'])} targeted probes without imputing unresolved finals."
                ),
            },
            {
                "stage": "finalize",
                "status": status,
                "main_task_status": status,
                "review_status": review_status,
                "change": "Exported the primary four-item bank under every original case.output_contract top-level field; optional review availability is reported separately.",
                "blocking_reasons": [],
                "review_limitations": sorted(set(review_limitations)),
            },
        ]
        diagnostics = {
            "main_task_status": status,
            "review_status": review_status,
            "items_completed": 4,
            "human_verdicts_supplied": review_supplied,
            "adjudication_status": adjudication.get("status"),
            "agreement_status": agreement.get("status"),
            "comparable_review_items": agreement.get("counts", {}).get("comparable_items", 0),
            "human_kappa_status": summary["human_kappa_status"],
            "primary_success_independent_of_review": True,
            "review_limitations": sorted(set(review_limitations)),
            "blocking_reasons": [],
        }
        reference_answers = [{
            "item_id": item["item_id"],
            "reference_answer": item["reference_answer"],
            "evidence_refs": item["evidence_refs"],
        } for item in item_bank["items"]]
        rubrics = [{"item_id": item["item_id"], "rubric": item["rubric"]} for item in item_bank["items"]]
        kappa = agreement.get("cohen_kappa_unweighted", {
            "status": "not_computed_review_incomplete", "value": None,
        })
        available = {
            "case_id": case_id,
            "status": status,
            "main_task_status": status,
            "review_status": review_status,
            "item_bank": item_bank,
            "draft_item_bank": item_bank,
            "benchmark_draft": item_bank,
            "benchmark_item_bank": item_bank,
            "items": complete_items,
            "benchmark_items": complete_items,
            "draft_items": complete_items,
            "questions": complete_items,
            "prompts": complete_items,
            "reference_answers": reference_answers,
            "rubrics": rubrics,
            "adjudication": adjudication,
            "review": adjudication,
            "human_review": adjudication,
            "blind_adjudication": adjudication,
            "human_verdicts": adjudication.get("human_verdicts", []),
            "agreement": agreement,
            "raw_agreements": raw_agreements,
            "cohen_kappa": kappa,
            "kappa": kappa,
            "failures": failures["failures"],
            "failure_artifact": failures,
            "targeted_probes": probes["probes"],
            "probe_artifact": probes,
            "sources": sources,
            "source_evidence": sources,
            "evidence": sources,
            "uncertainty": uncertainty,
            "change_records": change_records,
            "summary": summary,
            "diagnostics": diagnostics,
            "review_diagnostics": diagnostics,
        }
        unbound = [field for field in fields if field not in available]
        if unbound:
            status = "partial"
            available["status"] = status
            available["main_task_status"] = status
            message = f"No artifact binding for contract field(s): {unbound}; values retained as null."
            summary["status"] = status
            summary["main_task_status"] = status
            summary["blocking_reasons"] = [message]
            diagnostics["main_task_status"] = status
            diagnostics["blocking_reasons"] = [message]
            uncertainty.append({"type": "unbound_contract_fields", "statement": message})
            change_records[-1]["status"] = status
            change_records[-1]["main_task_status"] = status
            change_records[-1]["blocking_reasons"] = [message]
        result = {field: available.get(field) for field in fields}
        result["case_id"] = case_id
        result["status"] = status
        dump_json(output_path, result)
        print(json.dumps({
            "status": status,
            "main_task_status": status,
            "review_status": review_status,
            "items_completed": 4,
            "top_level_fields": fields,
            "unbound_fields": unbound,
            "blocking_reasons": summary["blocking_reasons"],
            "review_limitations": summary["review_limitations"],
        }, ensure_ascii=False))
        return 0
    except InputError as exc:
        print(f"finalize.py: INPUT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
