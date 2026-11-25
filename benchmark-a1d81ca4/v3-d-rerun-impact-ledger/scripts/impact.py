#!/usr/bin/env python3
"""Classify item-bank dependency changes and select exactly the scores to recompute."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from common import (
    canonical_bytes,
    effective_run_record,
    hash_tree,
    read_json,
    sha256_bytes,
    sha256_file,
    write_json_new,
)

DIFF_FIELDS = ("task", "reference_answer", "rubric", "evidence", "computation")


def index_bank(bank: dict[str, object]) -> dict[str, dict[str, object]]:
    items = bank.get("items")
    if not isinstance(items, list) or len(items) != 4:
        raise ValueError("both item banks must contain exactly four items")
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
            raise ValueError("invalid item record")
        if item["item_id"] in result:
            raise ValueError("duplicate item ID")
        result[item["item_id"]] = item
    return result


def source_map(materials: Path) -> dict[str, dict[str, object]]:
    return {record["path"]: record for record in hash_tree(materials)}


def item_source_records(
    item: dict[str, object], materials: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"item {item.get('item_id')} has no evidence list")
    records = []
    for reference in evidence:
        name = reference.get("material")
        if name not in materials:
            raise ValueError(f"evidence material is missing: {name}")
        records.append({"material": name, "sha256": materials[name]["sha256"]})
    return sorted(records, key=lambda record: record["material"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-bank", required=True)
    parser.add_argument("--new-bank", required=True)
    parser.add_argument("--old-materials", required=True)
    parser.add_argument("--new-materials", required=True)
    parser.add_argument("--old-run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    old_bank_path = Path(args.old_bank).resolve()
    new_bank_path = Path(args.new_bank).resolve()
    old_bank = read_json(old_bank_path)
    new_bank = read_json(new_bank_path)
    if not isinstance(old_bank, dict) or not isinstance(new_bank, dict):
        raise ValueError("item banks must be objects")
    old_items = index_bank(old_bank)
    new_items = index_bank(new_bank)
    old_sources = source_map(Path(args.old_materials).resolve())
    new_sources = source_map(Path(args.new_materials).resolve())
    old_run_dir = Path(args.old_run).resolve()
    if effective_run_record(old_run_dir).get("status") != "STABLE":
        raise ValueError("impact analysis requires a STABLE old run")
    scores_document = read_json(old_run_dir / "scores.json")
    old_scores = scores_document.get("scores")
    if not isinstance(old_scores, list) or len(old_scores) != 4:
        raise ValueError("old run must contain exactly four score records")
    score_by_item = {score["item_id"]: score for score in old_scores}
    if set(score_by_item) != set(old_items):
        raise ValueError("old score IDs do not match the old item bank")
    semantics_unchanged = old_bank.get("scoring_semantics") == new_bank.get("scoring_semantics")
    changed_records = []
    unaffected_records = []
    recompute_ids = set()
    affected_score_ids = []
    all_ids = sorted(old_items.keys() | new_items.keys())
    for item_id in all_ids:
        old = old_items.get(item_id)
        new = new_items.get(item_id)
        if old is None or new is None:
            change_kind = "added" if old is None else "removed"
            changed_fields = list(DIFF_FIELDS) + ["source_bytes"]
            old_score = score_by_item.get(item_id)
            if old_score:
                affected_score_ids.append(old_score["score_id"])
            if new is not None:
                recompute_ids.add(item_id)
            changed_records.append(
                {
                    "item_id": item_id,
                    "change_kind": change_kind,
                    "changed_fields": changed_fields,
                    "requires_recomputation": True,
                    "old_score_id": old_score.get("score_id") if old_score else None,
                }
            )
            continue
        changed_fields = [
            field
            for field in DIFF_FIELDS
            if canonical_bytes(old.get(field)) != canonical_bytes(new.get(field))
        ]
        old_item_sources = item_source_records(old, old_sources)
        new_item_sources = item_source_records(new, new_sources)
        source_bytes_changed = canonical_bytes(old_item_sources) != canonical_bytes(new_item_sources)
        if source_bytes_changed:
            changed_fields.append("source_bytes")
        global_semantics_affected = not semantics_unchanged
        changed = bool(changed_fields) or global_semantics_affected
        old_score = score_by_item[item_id]
        if changed:
            recompute_ids.add(item_id)
            affected_score_ids.append(old_score["score_id"])
            changed_records.append(
                {
                    "item_id": item_id,
                    "change_kind": "modified" if changed_fields else "global_semantics_changed",
                    "changed_fields": changed_fields,
                    "old_sources": old_item_sources,
                    "new_sources": new_item_sources,
                    "requires_recomputation": True,
                    "affected_score_id": old_score["score_id"],
                    "affected_score_sha256": sha256_bytes(canonical_bytes(old_score)),
                }
            )
        else:
            unaffected_records.append(
                {
                    "item_id": item_id,
                    "old_score_id": old_score["score_id"],
                    "old_score_sha256": sha256_bytes(canonical_bytes(old_score)),
                    "requires_recomputation": False,
                    "comparable": True,
                    "condition": "Item dependencies and applicable scoring semantics are byte-equivalent after canonical JSON comparison; source bytes are unchanged.",
                }
            )
    report = {
        "schema": "rerun-impact-ledger/impact-v1",
        "old_bank": {"path": str(old_bank_path), "version": old_bank.get("bank_version"), "sha256": sha256_file(old_bank_path)},
        "new_bank": {"path": str(new_bank_path), "version": new_bank.get("bank_version"), "sha256": sha256_file(new_bank_path)},
        "old_run": str(Path(args.old_run).resolve()),
        "applicable_semantics_unchanged": semantics_unchanged,
        "old_scoring_semantics_sha256": sha256_bytes(canonical_bytes(old_bank.get("scoring_semantics"))),
        "new_scoring_semantics_sha256": sha256_bytes(canonical_bytes(new_bank.get("scoring_semantics"))),
        "changed_items": changed_records,
        "recompute_item_ids": sorted(recompute_ids),
        "affected_score_ids": sorted(affected_score_ids),
        "unaffected_scores": unaffected_records,
        "selective_recomputation_required": sorted(recompute_ids),
        "unaffected_comparability_limit": "Unaffected scores remain comparable only while the stated applicable semantics and all item dependencies remain unchanged; this is not a correctness certificate.",
    }
    write_json_new(Path(args.output).resolve(), report, immutable=False)
    print(f"recompute_item_ids={','.join(sorted(recompute_ids))}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"impact.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
