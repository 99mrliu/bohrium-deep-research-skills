#!/usr/bin/env python3
"""Compare two real four-item output trees using a narrow volatility allowlist."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    canonical_bytes,
    decimal_sum,
    effective_run_record,
    read_json,
    sha256_bytes,
    sha256_file,
    write_json_new,
)

# No path, score, answer, source hash, rubric hash, or error text is volatile.
VOLATILE_FIELDS = frozenset(
    {
        "run_id",
        "raw_output_id",
        "score_id",
        "run_config_sha256",
        "raw_output_file_sha256",
        "generated_at",
    }
)


def canonicalize(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: canonicalize(child)
            for key, child in value.items()
            if key not in VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [canonicalize(child) for child in value]
    return value


def sorted_raw_records(run_dir: Path) -> list[dict[str, object]]:
    paths = sorted((run_dir / "raw_outputs").glob("*.json"))
    records = [read_json(path) for path in paths]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("raw output records must be JSON objects")
    return sorted(records, key=lambda record: str(record["item_id"]))


def validate_run(run_dir: Path, bank: dict[str, object]) -> dict[str, object]:
    effective = effective_run_record(run_dir)
    if effective.get("status") != "STABLE":
        raise ValueError(f"run is not STABLE: {run_dir}")
    selection = read_json(run_dir / "selection.json")
    if selection.get("mode") != "full":
        raise ValueError("compare_runs requires two full four-item runs")
    scores_document = read_json(run_dir / "scores.json")
    scores = scores_document.get("scores")
    if not isinstance(scores, list):
        raise ValueError("scores.json must contain a scores list")
    raw_records = sorted_raw_records(run_dir)
    items = bank["items"]
    required_ids = {item["item_id"] for item in items}
    if len(items) != 4 or len(required_ids) != 4:
        raise ValueError("the required item bank must contain exactly four unique items")
    score_ids = [record.get("item_id") for record in scores]
    raw_ids = [record.get("item_id") for record in raw_records]
    if len(scores) != 4 or set(score_ids) != required_ids or len(set(score_ids)) != 4:
        raise ValueError("scores must contain exactly the required four item IDs")
    if len(raw_records) != 4 or set(raw_ids) != required_ids or len(set(raw_ids)) != 4:
        raise ValueError("raw outputs must contain exactly the required four item IDs")
    raw_by_id = {record["item_id"]: record for record in raw_records}
    item_by_id = {item["item_id"]: item for item in items}
    for score in scores:
        item_id = score["item_id"]
        item = item_by_id[item_id]
        actual = decimal_sum(score.get("component_scores"))
        recorded = Decimal(str(score.get("score")))
        if actual != recorded:
            raise ValueError(f"score arithmetic mismatch for {item_id}")
        maximum = Decimal(str(score.get("max_score")))
        rubric_total = sum(
            Decimal(str(component["points"])) for component in item["rubric"]["components"]
        )
        if maximum != rubric_total or maximum != Decimal(str(item["rubric"]["max_score"])):
            raise ValueError(f"rubric/max-score mismatch for {item_id}")
        if recorded < 0 or recorded > maximum:
            raise ValueError(f"score outside range for {item_id}")
        if score.get("raw_output_id") != raw_by_id[item_id].get("raw_output_id"):
            raise ValueError(f"raw-output lineage mismatch for {item_id}")
        if set(score["component_scores"]) != {
            component["component_id"] for component in item["rubric"]["components"]
        }:
            raise ValueError(f"rubric component mismatch for {item_id}")
    errors = read_json(run_dir / "errors.json")
    if not isinstance(errors, list):
        raise ValueError("errors.json must be a list")
    return {
        "raw_outputs": raw_records,
        "scores": sorted(scores, key=lambda record: record["item_id"]),
        "selection": selection,
        "errors": errors,
        "item_bank_sha256": sha256_file(Path(read_json(run_dir / "run_config.json")["item_bank_path"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True)
    parser.add_argument("--run-b", required=True)
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run_a = Path(args.run_a).resolve()
    run_b = Path(args.run_b).resolve()
    if run_a == run_b:
        raise ValueError("two distinct real run directories are required")
    bank = read_json(Path(args.item_bank).resolve())
    if not isinstance(bank, dict):
        raise ValueError("item bank must be an object")
    data_a = validate_run(run_a, bank)
    data_b = validate_run(run_b, bank)
    declared_bank_hash = sha256_file(Path(args.item_bank).resolve())
    if data_a["item_bank_sha256"] != declared_bank_hash or data_b["item_bank_sha256"] != declared_bank_hash:
        raise ValueError("run item-bank lineage does not match --item-bank")
    semantic_a = canonicalize(
        {
            "raw_outputs": data_a["raw_outputs"],
            "scores": data_a["scores"],
            "selection": data_a["selection"],
            "item_bank_sha256": data_a["item_bank_sha256"],
        }
    )
    semantic_b = canonicalize(
        {
            "raw_outputs": data_b["raw_outputs"],
            "scores": data_b["scores"],
            "selection": data_b["selection"],
            "item_bank_sha256": data_b["item_bank_sha256"],
        }
    )
    errors_a = canonicalize(data_a["errors"])
    errors_b = canonicalize(data_b["errors"])
    semantic_hash_a = sha256_bytes(canonical_bytes(semantic_a))
    semantic_hash_b = sha256_bytes(canonical_bytes(semantic_b))
    report = {
        "schema": "rerun-impact-ledger/comparison-v1",
        "run_a": str(run_a),
        "run_b": str(run_b),
        "volatile_fields_removed": sorted(VOLATILE_FIELDS),
        "canonicalization_policy": "Only the explicit volatile-field allowlist is removed; errors are never ignored.",
        "semantic_hash_a": semantic_hash_a,
        "semantic_hash_b": semantic_hash_b,
        "semantic_equal": semantic_hash_a == semantic_hash_b,
        "errors_a": data_a["errors"],
        "errors_b": data_b["errors"],
        "errors_equal": errors_a == errors_b,
        "exactly_four_items_each": True,
        "score_arithmetic_valid_each": True,
        "scientific_correctness": "NOT_ESTABLISHED_BY_HASH_EQUALITY",
        "limitation": "Repeated semantic hash equality is repeatability evidence only, never scientific correctness.",
    }
    if errors_a != errors_b:
        report["semantic_equal"] = False
        report["error"] = "ERROR_SETS_UNEQUAL"
    write_json_new(Path(args.output).resolve(), report, immutable=False)
    if errors_a != errors_b:
        print("compare_runs.py: ERROR: error sets are unequal", file=sys.stderr)
        return 2
    print(
        f"semantic_equal={str(report['semantic_equal']).lower()} "
        f"semantic_hash_a={semantic_hash_a} semantic_hash_b={semantic_hash_b}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"compare_runs.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
