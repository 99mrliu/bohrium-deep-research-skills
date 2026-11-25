#!/usr/bin/env python3
"""Fail-closed contract finalizer with item-to-source-to-score lineage checks."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    canonical_bytes,
    contract_type_errors,
    decimal_sum,
    effective_run_record,
    make_contract_payload,
    output_field_specs,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_contract_payload,
    write_json_atomic,
)


MANDATORY_RUNTIME_FIELDS = frozenset({"case_id", "status", "success"})


def raw_records(run_dir: Path) -> dict[str, tuple[Path, dict[str, object]]]:
    records = {}
    for path in sorted((run_dir / "raw_outputs").glob("*.json")):
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError("raw output records must be objects")
        item_id = value.get("item_id")
        if not isinstance(item_id, str) or item_id in records:
            raise ValueError("raw output item IDs must be unique strings")
        records[item_id] = (path, value)
    return records


def validate_strict(run_dir: Path, bank: dict[str, object], bank_path: Path) -> dict[str, object]:
    effective = effective_run_record(run_dir)
    if effective.get("status") != "STABLE" or effective.get("success") is not True:
        raise ValueError("failed or partial run gates SUCCESS")
    selection = read_json(run_dir / "selection.json")
    if selection.get("mode") != "full":
        raise ValueError("final success requires a full four-item run")
    items = bank.get("items")
    if not isinstance(items, list) or len(items) != 4:
        raise ValueError("exactly four bank items are required")
    item_by_id = {item["item_id"]: item for item in items}
    if len(item_by_id) != 4:
        raise ValueError("item IDs must be unique")
    raw_by_id = raw_records(run_dir)
    scores_document = read_json(run_dir / "scores.json")
    scores = scores_document.get("scores")
    if not isinstance(scores, list):
        raise ValueError("scores.json must contain a scores list")
    score_by_id = {score.get("item_id"): score for score in scores}
    if len(scores) != 4 or len(score_by_id) != 4:
        raise ValueError("exactly four unique score records are required")
    if set(raw_by_id) != set(item_by_id) or set(score_by_id) != set(item_by_id):
        raise ValueError("item, raw-output, and score ID sets must match exactly")
    raw_lineage_ids = [record.get("raw_output_id") for _, record in raw_by_id.values()]
    score_lineage_ids = [score.get("score_id") for score in scores]
    if any(not isinstance(value, str) or not value for value in raw_lineage_ids + score_lineage_ids):
        raise ValueError("raw_output_id and score_id values must be nonempty strings")
    if len(set(raw_lineage_ids)) != 4 or len(set(score_lineage_ids)) != 4:
        raise ValueError("raw-output and score lineage IDs must be unique across four items")
    errors = read_json(run_dir / "errors.json")
    if errors != []:
        raise ValueError("nonempty errors.json gates SUCCESS")
    config_path = run_dir / "run_config.json"
    config = read_json(config_path)
    config_hash = sha256_file(config_path)
    if effective.get("run_config_sha256") != config_hash:
        raise ValueError("execution run_config hash mismatch")
    if sha256_file(Path(config["item_bank_path"])) != config.get("item_bank_sha256"):
        raise ValueError("item-bank byte hash does not match run configuration")
    if sha256_file(bank_path) != config.get("item_bank_sha256"):
        raise ValueError("supplied item bank is not the configured bank version")
    material_dir = Path(config["materials_dir"])
    output_items = []
    output_scores = []
    total = Decimal("0")
    maximum_total = Decimal("0")
    for item_id in sorted(item_by_id):
        item = item_by_id[item_id]
        raw_path, raw = raw_by_id[item_id]
        score = score_by_id[item_id]
        task_hash = sha256_bytes(canonical_bytes(item["task"]))
        reference_answer_hash = sha256_bytes(canonical_bytes(item["reference_answer"]))
        rubric_hash = sha256_bytes(canonical_bytes(item["rubric"]))
        if raw.get("task_sha256") != task_hash or score.get("rubric_sha256") != rubric_hash:
            raise ValueError(f"task/rubric lineage mismatch for {item_id}")
        if raw.get("reference_answer_sha256") != reference_answer_hash:
            raise ValueError(f"reference-answer lineage mismatch for {item_id}")
        if raw.get("rubric_sha256") != rubric_hash:
            raise ValueError(f"raw-output rubric lineage mismatch for {item_id}")
        if raw.get("run_config_sha256") != config_hash or score.get("run_config_sha256") != config_hash:
            raise ValueError(f"run-config lineage mismatch for {item_id}")
        if score.get("raw_output_id") != raw.get("raw_output_id"):
            raise ValueError(f"score-to-raw-output lineage mismatch for {item_id}")
        if score.get("raw_output_file_sha256") != sha256_file(raw_path):
            raise ValueError(f"raw-output file hash mismatch for {item_id}")
        if score.get("raw_output_text_sha256") != raw.get("raw_output_text_sha256"):
            raise ValueError(f"raw-output text hash mismatch for {item_id}")
        evidence = raw.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != len(item["evidence"]):
            raise ValueError(f"evidence lineage mismatch for {item_id}")
        for actual, declared in zip(evidence, item["evidence"]):
            if actual.get("material") != declared["material"] or actual.get("quote") != declared["quote"]:
                raise ValueError(f"evidence identity mismatch for {item_id}")
            if actual.get("source_sha256") != sha256_file(material_dir / declared["material"]):
                raise ValueError(f"source byte hash mismatch for {item_id}")
        component_total = decimal_sum(score.get("component_scores"))
        score_value = Decimal(str(score.get("score")))
        maximum = Decimal(str(score.get("max_score")))
        if component_total != score_value:
            raise ValueError(f"score arithmetic mismatch for {item_id}")
        if score_value < 0 or score_value > maximum:
            raise ValueError(f"score outside rubric range for {item_id}")
        rubric_total = sum(Decimal(str(part["points"])) for part in item["rubric"]["components"])
        if rubric_total != Decimal(str(item["rubric"]["max_score"])) or maximum != rubric_total:
            raise ValueError(f"rubric arithmetic mismatch for {item_id}")
        if set(score["component_scores"]) != {part["component_id"] for part in item["rubric"]["components"]}:
            raise ValueError(f"rubric component lineage mismatch for {item_id}")
        total += score_value
        maximum_total += maximum
        output_scores.append(score)
        # Start with the complete bank item: no task, answer, rubric, evidence,
        # computation, or bank metadata is discarded in the publication view.
        output_item = dict(item)
        output_item.update(
            {
                "answer": raw.get("answer"),
                "raw_answer": raw.get("answer"),
                "score": score.get("score"),
                "max_score": score.get("max_score"),
                "component_scores": score.get("component_scores"),
                "raw_output_id": raw.get("raw_output_id"),
                "score_id": score.get("score_id"),
                "rubric_sha256": rubric_hash,
                "raw_output": raw,
                "score_record": score,
                "content_correctness": "AGENT_REVIEW_REQUIRED",
            }
        )
        output_items.append(output_item)
    return {
        "items": output_items,
        "scores": output_scores,
        "score_total": float(total) if total % 1 else int(total),
        "score_max": float(maximum_total) if maximum_total % 1 else int(maximum_total),
        "sources": read_json(run_dir / "manifest.json")["inputs"],
    }


def _declared_mismatch_fields(case: dict[str, object], result: dict[str, object]) -> set[str]:
    errors = contract_type_errors(case, result)
    mismatched = set()
    for spec in output_field_specs(case):
        field = str(spec["name"])
        if any(error.startswith(f"field {field!r} ") for error in errors):
            mismatched.add(field)
    return mismatched


def _repair_partial_types(case: dict[str, object], result: dict[str, object]) -> list[str]:
    """Keep PARTIAL publishable while retaining every declared field's type."""
    defaults = make_contract_payload(case)
    mismatched = sorted(_declared_mismatch_fields(case, result))
    for field in mismatched:
        if field in MANDATORY_RUNTIME_FIELDS:
            raise ValueError(f"mandatory runtime field {field!r} has an incompatible declared type")
        result[field] = defaults[field]
    return mismatched


def _apply_partial_gate(
    case: dict[str, object], result: dict[str, object], message: str
) -> None:
    result["status"] = "PARTIAL"
    if "success" in result:
        result["success"] = False
    for field in result:
        if field == "summary" and isinstance(result[field], dict):
            result[field].update({"process_status": "PARTIAL", "message": message})
        elif field == "uncertainty" and isinstance(result[field], list):
            result[field].extend([message, "No SUCCESS claim is permitted for this publication."])
        elif field == "limitations" and isinstance(result[field], list):
            result[field].append("The publication gate did not pass; PARTIAL is not success.")
        elif field == "run_manifest" and isinstance(result[field], dict):
            result[field].update({"publication_status": "PARTIAL", "success": False})
    repaired = _repair_partial_types(case, result)
    if repaired:
        # A type-incompatible binding is empty in PARTIAL; record that fact in
        # any compatible narrative fields without changing the field's type.
        note = "Type-incompatible fields reset to typed empty values: " + ", ".join(repaired)
        if isinstance(result.get("summary"), dict):
            result["summary"].setdefault("type_repairs", repaired)
        if isinstance(result.get("uncertainty"), list):
            result["uncertainty"].append(note)
    validate_contract_payload(case, result)


def partial_payload(
    case: dict[str, object], run_dir: Path, message: str, impact: object = None
) -> dict[str, object]:
    result = make_contract_payload(case)
    try:
        effective = effective_run_record(run_dir)
    except Exception:
        effective = {"status": "PARTIAL", "success": False}
    for field in result:
        if field == "run_manifest":
            result[field] = {
                "run_id": run_dir.name,
                "path": str(run_dir / "manifest.json"),
                "status": effective.get("status", "PARTIAL"),
                "success": False,
                "execution": effective,
            }
        elif field == "sources":
            try:
                result[field] = [read_json(run_dir / "manifest.json")["inputs"]]
            except Exception:
                result[field] = []
        elif field == "change_records" and impact is not None:
            result[field] = [{"impact": impact}]
    _apply_partial_gate(case, result, message)
    return result


def _publication_values(
    case: dict[str, object],
    bank: dict[str, object],
    run_dir: Path,
    validated: dict[str, object],
    comparison: object,
    impact: object,
    selective: object,
) -> dict[str, object]:
    full_bank = dict(bank)
    full_bank["items"] = validated["items"]
    summary = {
        "process_status": "STABLE",
        "exact_item_count": 4,
        "score_total": validated["score_total"],
        "score_max": validated["score_max"],
        "rollup_arithmetic": "sum of four validated item scores",
        "semantic_repeat": comparison,
    }
    rollup = {
        "item_count": 4,
        "score_total": validated["score_total"],
        "score_max": validated["score_max"],
        "arithmetic": "sum of four validated item scores",
    }
    manifest_path = run_dir / "manifest.json"
    execution_path = run_dir / "execution.json"
    run_manifest = {
        "run_id": run_dir.name,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "execution_path": str(execution_path),
        "execution_sha256": sha256_file(execution_path),
        "status": "STABLE",
        "success": True,
        "manifest": read_json(manifest_path),
        "execution": read_json(execution_path),
    }
    uncertainty = [
        "Source-conditioned calculations and scoring are deterministic synthetic evidence, not scientific validation.",
        "Agent content review remains required for every benchmark-DRAFT item.",
    ]
    limitations = [
        "Hash identity establishes byte or declared-semantic repeatability only, not correctness.",
        "STABLE is a process gate, not a scientific correctness claim.",
    ]
    change_records = [
        {
            "impact": impact,
            "selective_run": selective,
            "selective_recomputation_note": "Only impact.recompute_item_ids were executed in the selective run; unaffected scores were not recomputed.",
        }
    ] if impact is not None else []
    return {
        "case_id": case.get("case_id"),
        "status": "SUCCESS",
        "success": True,
        "items": validated["items"],
        "item_bank": full_bank,
        "benchmark_draft": validated["items"],
        "questions": validated["items"],
        "score_report": {**rollup, "scores": validated["scores"]},
        "scores": validated["scores"],
        "rollup": rollup,
        "summary": summary,
        "sources": validated["sources"],
        "uncertainty": uncertainty,
        "limitations": limitations,
        "change_records": change_records,
        "run_manifest": run_manifest,
    }


def validated_payload(
    case: dict[str, object],
    bank: dict[str, object],
    run_dir: Path,
    validated: dict[str, object],
    comparison: object,
    impact: object,
    selective: object,
) -> tuple[dict[str, object], str | None]:
    values = _publication_values(case, bank, run_dir, validated, comparison, impact, selective)
    result = make_contract_payload(case)
    for field in result:
        if field in values:
            result[field] = values[field]
    unknown = sorted(set(result) - set(values))
    mismatched = _repair_partial_types(case, result)
    gate_fields = sorted(set(unknown) | set(mismatched))
    if not gate_fields:
        validate_contract_payload(case, result)
        return result, None
    reasons = []
    if unknown:
        reasons.append("unbound fields retained as typed empty/null: " + ", ".join(unknown))
    if mismatched:
        reasons.append("declared-type mismatches reset to typed empty values: " + ", ".join(mismatched))
    message = "SUCCESS gated: " + "; ".join(reasons)
    _apply_partial_gate(case, result, message)
    if isinstance(result.get("summary"), dict):
        result["summary"]["unbound_or_type_mismatched_fields"] = gate_fields
    return result, message


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--comparison")
    parser.add_argument("--impact")
    parser.add_argument("--selective-run")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    case = read_json(Path(args.case).resolve())
    bank = read_json(Path(args.item_bank).resolve())
    run_dir = Path(args.run_dir).resolve()
    output = Path(args.output).resolve()
    if not isinstance(case, dict) or not isinstance(bank, dict):
        raise ValueError("case and item bank must be objects")
    try:
        validated = validate_strict(run_dir, bank, Path(args.item_bank).resolve())
    except Exception as exc:
        message = f"SUCCESS gated: {exc}"
        impact = read_json(Path(args.impact).resolve()) if args.impact else None
        result = partial_payload(case, run_dir, message, impact)
        write_json_atomic(output, result)
        print(f"finalize.py: {message}", file=sys.stderr)
        return 0 if args.allow_partial else 1

    comparison = read_json(Path(args.comparison).resolve()) if args.comparison else None
    impact = read_json(Path(args.impact).resolve()) if args.impact else None
    selective = effective_run_record(Path(args.selective_run).resolve()) if args.selective_run else None
    result, gate_message = validated_payload(
        case, bank, run_dir, validated, comparison, impact, selective
    )
    write_json_atomic(output, result)
    if gate_message is not None:
        print(f"finalize.py: {gate_message}", file=sys.stderr)
        return 0 if args.allow_partial else 1
    print(f"SUCCESS result={output} score={validated['score_total']}/{validated['score_max']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"finalize.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
