#!/usr/bin/env python3
"""Content-address an item bank and optionally diff two actual bank states."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

from common import canonical_bytes, content_sha256, fail_message, load_json, write_json

CONSTRUCT_FIELDS = (
    "task", "task_intent", "cognitive_operation", "input_material", "source_scope",
)
SCORING_FIELDS = ("reference_answer", "rubric", "arithmetic")


def bank_items(bank: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw_items = bank.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("bank.items must be a list")
    result: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict) or not isinstance(item.get("item_id"), str) or not item["item_id"]:
            raise ValueError("bank item %d lacks a non-empty string item_id" % index)
        item_id = item["item_id"]
        if item_id in result:
            raise ValueError("duplicate item_id in bank: %s" % item_id)
        result[item_id] = item
    return result


def load_bank_state(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("bank or snapshot root must be an object")
    if "bank" in value:
        bank = value["bank"]
        if not isinstance(bank, dict):
            raise ValueError("snapshot.bank must be an object")
        if isinstance(value.get("bank_sha256"), str):
            digest = content_sha256(bank)
            if value["bank_sha256"] != digest:
                raise ValueError("snapshot content address does not match its embedded bank")
        bank_items(bank)
        return bank
    bank_items(value)
    return value


def item_digest_record(item_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "item_sha256": content_sha256(item),
        "answer_sha256": content_sha256(item.get("reference_answer")),
        "rubric_sha256": content_sha256(item.get("rubric")),
    }


def diff_banks(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    before_items = bank_items(previous)
    after_items = bank_items(current)
    before_ids, after_ids = set(before_items), set(after_items)
    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    changed: List[Dict[str, Any]] = []
    comparable_flags: List[bool] = []
    construct_impacting = bool(added or removed)
    scoring_impacting = bool(added or removed)

    for item_id in sorted(before_ids & after_ids):
        before, after = before_items[item_id], after_items[item_id]
        if canonical_bytes(before) == canonical_bytes(after):
            continue
        all_fields = sorted(set(before) | set(after))
        changed_fields = [field for field in all_fields if canonical_bytes(before.get(field)) != canonical_bytes(after.get(field))]
        answer_changed = "reference_answer" in changed_fields
        rubric_changed = "rubric" in changed_fields
        arithmetic_changed = "arithmetic" in changed_fields
        construct_changed = any(field in CONSTRUCT_FIELDS for field in changed_fields)
        scoring_changed = answer_changed or rubric_changed or arithmetic_changed
        construct_impacting = construct_impacting or construct_changed
        scoring_impacting = scoring_impacting or scoring_changed
        construct_comparable = not construct_changed
        scoring_comparable = not scoring_changed
        comparable_flags.append(construct_comparable and scoring_comparable)
        changed.append({
            "item_id": item_id,
            "changed_fields": changed_fields,
            "answer_changed": answer_changed,
            "rubric_changed": rubric_changed,
            "arithmetic_changed": arithmetic_changed,
            "construct_changed": construct_changed,
            "scoring_changed": scoring_changed,
            "old_item_sha256": content_sha256(before),
            "new_item_sha256": content_sha256(after),
            "construct_comparable": construct_comparable,
            "scoring_comparable": scoring_comparable,
        })

    construct_comparable = not construct_impacting
    scoring_comparable = not scoring_impacting
    comparable = construct_comparable and scoring_comparable and not (added or removed) and all(comparable_flags)
    if not construct_comparable:
        comparability = "not_comparable"
    elif not scoring_comparable:
        comparability = "rescore_required"
    else:
        comparability = "comparable"
    before_metadata = {key: value for key, value in previous.items() if key != "items"}
    after_metadata = {key: value for key, value in current.items() if key != "items"}
    return {
        "schema_version": "1.0",
        "comparison_basis": "two supplied actual states; no hypothetical or reconstructed version",
        "previous_bank_sha256": content_sha256(previous),
        "current_bank_sha256": content_sha256(current),
        "added_item_ids": added,
        "removed_item_ids": removed,
        "changed_items": changed,
        "answer_changed_item_ids": [entry["item_id"] for entry in changed if entry["answer_changed"]],
        "rubric_changed_item_ids": [entry["item_id"] for entry in changed if entry["rubric_changed"]],
        "bank_metadata_changed": canonical_bytes(before_metadata) != canonical_bytes(after_metadata),
        "construct_comparable": construct_comparable,
        "scoring_comparable": scoring_comparable,
        "comparable": comparable,
        "comparability": comparability,
        "comparability_rule": "Item membership/task/stimulus/scope/operation changes break construct comparability; answer/rubric/arithmetic changes require rescoring. Metadata-only changes do not alter either.",
    }


def make_snapshot(bank: Dict[str, Any], previous: Dict[str, Any] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    items = bank_items(bank)
    diff = diff_banks(previous, bank) if previous is not None else None
    snapshot = {
        "schema_version": "1.0",
        "content_address": "sha256:" + content_sha256(bank),
        "bank_sha256": content_sha256(bank),
        "item_count": len(items),
        "item_digests": [item_digest_record(item_id, items[item_id]) for item_id in sorted(items)],
        "diff_status": "compared_supplied_states" if diff is not None else "not_requested_no_previous_state_assumed",
        "diff": diff,
        "bank": bank,
    }
    return snapshot, diff


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("item_bank", help="Current actual item_bank.json")
    parser.add_argument("--previous", help="Prior actual item_bank.json or a content-verified snapshot")
    parser.add_argument("--output", required=True, help="Snapshot JSON destination")
    parser.add_argument("--diff-output", help="Optional separate diff JSON; requires --previous")
    args = parser.parse_args(argv)
    try:
        if args.diff_output and not args.previous:
            parser.error("--diff-output requires --previous")
        bank = load_bank_state(load_json(args.item_bank))
        previous = load_bank_state(load_json(args.previous)) if args.previous else None
        snapshot, diff = make_snapshot(bank, previous)
        write_json(args.output, snapshot)
        if args.diff_output:
            write_json(args.diff_output, diff)
        if not args.diff_output:
            json.dump(diff, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stdout.write("Snapshot %s (%d items); comparability=%s\n" % (
                snapshot["content_address"], snapshot["item_count"],
                diff["comparability"] if diff else "not_requested",
            ))
        return 0
    except (ValueError, OSError) as exc:
        fail_message(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
