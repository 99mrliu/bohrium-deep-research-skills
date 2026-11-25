#!/usr/bin/env python3
"""Local regression for independent output-contract shapes and alias binding."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import (  # noqa: E402
    make_contract_payload,
    output_fields,
    validate_contract_payload,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_full_items(records: object, bank: dict[str, object]) -> None:
    assert isinstance(records, list) and len(records) == 4
    by_id = {record["item_id"]: record for record in records}
    assert len(by_id) == 4
    for source in bank["items"]:
        actual = by_id[source["item_id"]]
        # Every original bank-item property survives, not just selected content.
        for key, value in source.items():
            assert actual[key] == value, (source["item_id"], key)
        for key in ("task", "reference_answer", "rubric", "evidence", "computation"):
            assert key in actual
        assert actual["answer"] == actual["raw_answer"] == actual["raw_output"]["answer"]
        assert actual["score"] == actual["score_record"]["score"] == 2
        assert actual["max_score"] == actual["score_record"]["max_score"] == 2
        assert actual["component_scores"] == actual["score_record"]["component_scores"]
        assert actual["raw_output_id"] == actual["raw_output"]["raw_output_id"]
        assert actual["score_id"] == actual["score_record"]["score_id"]


def parser_regressions() -> None:
    assert output_fields({"output_contract": ["items", "success"]}) == [
        "items",
        "success",
        "case_id",
        "status",
    ]
    assert output_fields({"case_id": "x"}) == ["case_id", "status"]
    shapes = [
        {"fields": ["items", "summary"]},
        {"fields": [{"name": "items", "type": "array", "description": "full items"}]},
        {"required_fields": ["questions"]},
        {"required_top_fields": [{"name": "scores", "type": "array"}]},
        {"required_top_level_fields": ["rollup"]},
        {"properties": {"item_bank": {"type": "object"}, "success": "boolean"}},
        {"items": "array", "summary": {"type": "object", "description": "metadata"}},
    ]
    for contract in shapes:
        fields = output_fields({"output_contract": contract})
        assert "case_id" in fields and "status" in fields
        assert len(fields) == len(set(fields))
    combined = {
        "required_fields": ["items"],
        "properties": {"items": {"type": "array"}, "summary": "object"},
    }
    assert output_fields({"output_contract": combined}) == [
        "items",
        "summary",
        "case_id",
        "status",
    ]
    typed_case = {
        "case_id": "typed-empty",
        "output_contract": {
            "unknown_array": "array",
            "unknown_object": {"type": "object", "metadata": "preserved by parser"},
            "unknown_text": {"type": ["string", "null"]},
            "unknown_flag": "boolean",
            "unknown_number": "number",
            "unknown_integer": "integer",
            "unknown_null": "null",
        },
    }
    payload = make_contract_payload(typed_case)
    assert payload["unknown_array"] == []
    assert payload["unknown_object"] == {}
    assert payload["unknown_text"] == ""
    assert payload["unknown_flag"] is False
    assert payload["unknown_number"] == 0
    assert payload["unknown_integer"] == 0
    assert payload["unknown_null"] is None
    assert payload["case_id"] == "typed-empty" and payload["status"] == "PARTIAL"
    validate_contract_payload(typed_case, payload)
    bad_typed = dict(payload)
    bad_typed["unknown_array"] = {}
    try:
        validate_contract_payload(typed_case, bad_typed)
    except ValueError:
        pass
    else:
        raise AssertionError("declared field type mismatch was not rejected")
    invalid_contracts = [
        {"fields": [{"type": "array"}]},
        {"fields": ["items", "items"]},
        {"properties": {"items": {"type": "not-a-json-type"}}},
        {"items": ["array"]},
        ["items", 3],
    ]
    for contract in invalid_contracts:
        try:
            output_fields({"output_contract": contract})
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid contract shape accepted: {contract!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--item-bank", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--impact", required=True)
    parser.add_argument("--selective-run", required=True)
    args = parser.parse_args()
    work = Path(args.work_dir).resolve()
    try:
        work.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("contract regression outputs must be outside the bundle")
    work.mkdir(parents=True, exist_ok=True)
    bank_path = Path(args.item_bank).resolve()
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    parser_regressions()

    rich_contract = {
        "case_id": "string",
        "status": "string",
        "success": "boolean",
        "items": "array",
        "item_bank": "object",
        "benchmark_draft": "array",
        "questions": "array",
        "score_report": "object",
        "scores": "array",
        "rollup": "object",
        "run_manifest": "object",
        "sources": "object",
        "uncertainty": "array",
        "change_records": "array",
        "limitations": "array",
        "summary": "object",
    }
    shape_cases = [
        ("top_level_list", ["items", "success"]),
        (
            "fields_descriptors",
            {"fields": [{"name": "items", "type": "array"}, {"name": "rollup", "type": "object"}]},
        ),
        ("required_fields", {"required_fields": ["questions", "score_report"]}),
        ("required_top_fields", {"required_top_fields": [{"name": "scores", "type": "array"}]}),
        ("required_top_level_fields", {"required_top_level_fields": ["benchmark_draft"]}),
        ("properties", {"properties": {"item_bank": "object", "sources": "object"}}),
        ("direct_map_all_aliases", rich_contract),
    ]
    results: dict[str, dict[str, object]] = {}
    for name, contract in shape_cases:
        case = {"case_id": "contract-shape-regression", "output_contract": contract}
        case_path = work / f"{name}_case.json"
        output_path = work / f"{name}_result.json"
        write_json(case_path, case)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "finalize.py"),
            "--case",
            str(case_path),
            "--item-bank",
            str(bank_path),
            "--run-dir",
            str(Path(args.run_dir).resolve()),
            "--comparison",
            str(Path(args.comparison).resolve()),
            "--impact",
            str(Path(args.impact).resolve()),
            "--selective-run",
            str(Path(args.selective_run).resolve()),
            "--output",
            str(output_path),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode == 0, (name, completed.stdout, completed.stderr)
        result = json.loads(output_path.read_text(encoding="utf-8"))
        results[name] = result
        expected_fields = output_fields(case)
        assert set(result) == set(expected_fields), (name, result.keys(), expected_fields)
        assert result["case_id"] == case["case_id"]
        assert result["status"] == "SUCCESS"
        validate_contract_payload(case, result)
        for alias in ("items", "questions", "benchmark_draft"):
            if alias in result:
                check_full_items(result[alias], bank)
        if "item_bank" in result:
            assert result["item_bank"]["bank_version"] == bank["bank_version"]
            assert result["item_bank"]["items"]
            check_full_items(result["item_bank"]["items"], bank)
        if "scores" in result:
            assert isinstance(result["scores"], list) and len(result["scores"]) == 4
            assert all(record["score"] == 2 and record["max_score"] == 2 for record in result["scores"])
        if "sources" in result:
            assert isinstance(result["sources"], dict)
            assert {"case.json", "task.md", "materials", "item_bank"} <= set(result["sources"])

    rich = results["direct_map_all_aliases"]
    check_full_items(rich["items"], bank)
    assert rich["benchmark_draft"] == rich["questions"] == rich["items"]
    assert rich["item_bank"]["items"] == rich["items"]
    assert rich["score_report"]["scores"] == rich["scores"]
    for alias in ("rollup", "score_report", "summary"):
        assert rich[alias]["score_total"] == 8
        assert rich[alias]["score_max"] == 8
    assert rich["rollup"]["score_total"] == sum(record["score"] for record in rich["scores"])
    assert rich["rollup"]["score_max"] == sum(record["max_score"] for record in rich["scores"])
    score_by_id = {record["item_id"]: record for record in rich["scores"]}
    for record in rich["items"]:
        assert record["score_record"] == score_by_id[record["item_id"]]
    assert rich["run_manifest"]["manifest"]["case_id"]
    assert rich["run_manifest"]["execution"]["status"] == "STABLE"
    assert rich["change_records"][0]["impact"]["recompute_item_ids"] == [
        "SYNTH-DRAFT-002",
        "SYNTH-DRAFT-003",
        "SYNTH-DRAFT-004",
    ]

    partial_cases = [
        (
            "unknown_fields",
            {
                "properties": {
                    "items": "array",
                    "success": "boolean",
                    "summary": "object",
                    "mystery_array": "array",
                    "mystery_object": "object",
                    "mystery_text": "string",
                    "mystery_null": "null",
                }
            },
        ),
        ("declared_type_mismatch", {"fields": [{"name": "items", "type": "object"}]}),
    ]
    for name, contract in partial_cases:
        case = {"case_id": "contract-partial-regression", "output_contract": contract}
        case_path = work / f"{name}_case.json"
        output_path = work / f"{name}_result.json"
        write_json(case_path, case)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "finalize.py"),
            "--case",
            str(case_path),
            "--item-bank",
            str(bank_path),
            "--run-dir",
            str(Path(args.run_dir).resolve()),
            "--output",
            str(output_path),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode != 0, (name, completed.stdout, completed.stderr)
        result = json.loads(output_path.read_text(encoding="utf-8"))
        assert result["status"] == "PARTIAL", result
        assert "SUCCESS gated:" in completed.stderr
        assert set(result) == set(output_fields(case))
        validate_contract_payload(case, result)
        if name == "unknown_fields":
            assert result["success"] is False
            assert result["mystery_array"] == []
            assert result["mystery_object"] == {}
            assert result["mystery_text"] == ""
            assert result["mystery_null"] is None
            check_full_items(result["items"], bank)
            assert set(result["summary"]["unbound_or_type_mismatched_fields"]) == {
                "mystery_array",
                "mystery_object",
                "mystery_text",
                "mystery_null",
            }
        else:
            assert result["items"] == {}

    print(f"CONTRACT SHAPE REGRESSION ASSERTIONS PASSED ({len(shape_cases)} SUCCESS, {len(partial_cases)} PARTIAL)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"contract_regression.py: ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
