#!/usr/bin/env python3
"""Introspect a workorder and create an agent-adaptable response plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from contract_utils import (
    InputError,
    contract_fields,
    get_contract,
    in_scope_documents,
    load_json,
    write_json,
)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _questions(workorder: dict[str, Any]) -> list[dict[str, Any]]:
    raw = workorder.get("explicit_questions", workorder.get("questions", []))
    if not isinstance(raw, list):
        return []
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            questions.append(
                {
                    "question_id": f"q{index}",
                    "question": item,
                    "requested_result_fields": [],
                }
            )
        elif isinstance(item, dict):
            question = item.get("question", item.get("text", item.get("ask")))
            if isinstance(question, str):
                questions.append(
                    {
                        "question_id": str(item.get("question_id", item.get("id", f"q{index}"))),
                        "question": question,
                        "requested_result_fields": _string_list(
                            item.get("result_fields", item.get("output_fields", []))
                        ),
                        "definition": item.get("definition"),
                    }
                )
    return questions


def build_plan(case: dict[str, Any], workorder: dict[str, Any], task_text: str) -> dict[str, Any]:
    if "case_id" not in case:
        raise InputError("case.json has no case_id.")
    fields = contract_fields(get_contract(workorder))
    field_names = [name for name, _ in fields]
    questions = _questions(workorder)
    for question in questions:
        unknown = set(question["requested_result_fields"]) - set(field_names)
        if unknown:
            raise InputError(
                f"Question {question['question_id']} names unknown output fields: "
                f"{sorted(unknown)}"
            )
    response_plan = []
    for question in questions:
        response_plan.append(
            {
                **question,
                "document_ids": in_scope_documents(workorder),
                "evidence_cell_ids": [],
                "agent_answer_and_mapping": "TO_BE_COMPLETED_AFTER_READING_SOURCES",
            }
        )
    return {
        "case_id": case["case_id"],
        "purpose": "Question/workorder-adaptive response plan; not an answer template.",
        "requested_deliverables": workorder.get("requested_deliverables", []),
        "explicit_questions": questions,
        "document_scope": in_scope_documents(workorder),
        "contract_keys_exact": field_names,
        "field_definitions": [
            {"name": name, "specification": spec} for name, spec in fields
        ],
        "response_plan": response_plan,
        "agent_must_complete": [
            "Map every explicit question and requested deliverable to exact contract keys; add mappings missing from this skeleton.",
            "Read every in-scope source and record question-specific cells keyed by exact source_document_id and paragraph_id.",
            "Choose reported/not_reported/not_applicable/unclear/noncomparable from source meaning, not from a fixed domain schema.",
            "Quantitatively synthesize only after task, metric, units, material, pollutant, and budget are comparable; otherwise retain separate values.",
            "Author response.fields, uncertainty, completion, and change_records; then run assemble_response.py.",
        ],
        "source_task": {
            "sha256": hashlib.sha256(task_text.encode("utf-8")).hexdigest(),
            "text": task_text,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path, help="Path to case.json")
    parser.add_argument("--task", required=True, type=Path, help="Path to task.md")
    parser.add_argument(
        "--workorder", required=True, type=Path, help="Path to comparison-workorder.json"
    )
    parser.add_argument("--output", required=True, type=Path, help="Plan JSON to create")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        case = load_json(args.case)
        workorder = load_json(args.workorder)
        if not isinstance(case, dict) or not isinstance(workorder, dict):
            raise InputError("case.json and workorder must contain JSON objects.")
        try:
            task_text = args.task.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise InputError(f"File not found: {args.task}") from exc
        except UnicodeError as exc:
            raise InputError(f"Task is not UTF-8: {args.task}: {exc}") from exc
        plan = build_plan(case, workorder, task_text)
        write_json(args.output, plan)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "contract_fields": len(plan["contract_keys_exact"]),
                    "questions": len(plan["explicit_questions"]),
                    "documents": len(plan["document_scope"]),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
