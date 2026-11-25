#!/usr/bin/env python3
"""Create an early honest partial result without inventing any extracted value."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from result_contract import InputDataError, load_json, parse_targets


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def empty_field(target: Dict[str, Any]) -> Dict[str, Any]:
    condition = target.get("experimental_condition", target.get("condition"))
    return {
        "field_id": target["field_id"],
        "status": "extraction_failed",
        "subject": target.get("subject"),
        "scalar": None,
        "units": None,
        "statistic": None,
        "experimental_condition": condition,
        "condition": condition,
        "comparator": target.get("comparator"),
        "paragraph_id": None,
        "quote": None,
        "evidence": None,
        "notes": "Pending extraction: no source-backed value has been established yet. This is not not_reported.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("/input/case.json"))
    parser.add_argument("--targets", type=Path, default=Path("/input/target-fields.json"))
    parser.add_argument("--task", type=Path, default=Path("/input/task.md"))
    parser.add_argument("--work", type=Path, default=Path("/app/work"))
    parser.add_argument("--output", type=Path, default=Path("/app/output"))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "result.json"
    if result_path.exists():
        print(dumps({"actual_pass": True, "action": "left_existing_result_untouched", "result": str(result_path)}))
        return 0

    errors = []
    case_id = "UNKNOWN_CASE_ID"
    try:
        case = load_json(args.case)
        if isinstance(case, dict) and isinstance(case.get("case_id"), str) and case["case_id"]:
            case_id = case["case_id"]
        else:
            errors.append("case.json lacks a nonempty string case_id")
    except (InputDataError, OSError, ValueError) as exc:
        case = {}
        errors.append(str(exc))
    try:
        target_data = parse_targets(load_json(args.targets))
        fields = [empty_field(target) for target in target_data]
    except (InputDataError, OSError, ValueError) as exc:
        target_data, fields = [], []
        errors.append(str(exc))
    try:
        task_bytes = args.task.read_bytes()
        task_sha256 = hashlib.sha256(task_bytes).hexdigest()
    except OSError as exc:
        task_sha256 = None
        errors.append("cannot read task.md: %s" % exc)

    result = {
        "case_id": case_id,
        "status": "partial" if fields and case_id != "UNKNOWN_CASE_ID" else "input_error",
        "result": {"fields": fields, "field_results": json.loads(json.dumps(fields))},
        "claims": [],
        "uncertainties": [{
            "kind": "incomplete_extraction",
            "description": "Early scaffold only. Every requested field remains pending and no absence, value, or claim has been inferred.",
        }] + [{"kind": "input_error", "description": message} for message in errors],
        "sources": [],
        "change_records": [{
            "sequence": 1,
            "action": "scaffolded_early_partial",
            "description": "Initialized requested field IDs with extraction_failed/pending; no scientific values were supplied.",
        }],
    }
    atomic_write(result_path, dumps(result))
    draft = args.work / "draft-result.json"
    if not draft.exists():
        atomic_write(draft, dumps(result))
    corpus_template = args.work / "source-corpus.json"
    if not corpus_template.exists():
        atomic_write(corpus_template, dumps({"schema": "evidence-corpus/v1", "sources": []}))
    review_template = args.work / "decoy-review.json"
    if not review_template.exists():
        atomic_write(review_template, dumps({
            "schema": "decoy-review/v1",
            "case_id": case_id,
            "semantic_correctness_not_proven": True,
            "reviewer": "",
            "field_reviews": [{
                "field_id": target["field_id"],
                "verdict": "needs_revision",
                "decoys_checked": [],
                "observation": "",
            } for target in target_data],
            "claim_reviews": [],
        }))
    inventory = {
        "case_id": case_id,
        "task_sha256": task_sha256,
        "requested_field_ids": [target["field_id"] for target in target_data],
        "input_errors": errors,
        "next": "Read actual material, replace pending statuses truthfully, build exact source corpus, then perform decoy review.",
    }
    atomic_write(args.work / "input-inventory.json", dumps(inventory))
    print(dumps({
        "actual_pass": True,
        "action": "created_early_honest_partial",
        "status": result["status"],
        "requested_field_count": len(fields),
        "result": str(result_path),
        "draft": str(draft),
        "decoy_review_template": str(review_template),
        "input_errors": errors,
    }))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
