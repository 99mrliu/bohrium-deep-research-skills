#!/usr/bin/env python3
"""Exercise no-human finalization across all supported contract shapes."""

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path


FIELDS = [
    "case_id", "status", "questions", "benchmark_draft", "reference_answers", "rubrics",
    "evidence", "sources", "uncertainty", "change_records", "diagnostics",
    "adjudication", "agreement", "review_status",
]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent.parent
    original_case = read_json(bundle / "examples" / "input" / "case.json")
    item_bank = bundle / "examples" / "input" / "item_bank.json"
    sources = bundle / "examples" / "input" / "source_evidence.json"
    variants = {
        "list_strings": FIELDS,
        "fields_strings": {"fields": FIELDS},
        "fields_objects": {"fields": [{"name": field, "description": "contract-shape test"} for field in FIELDS]},
        "direct_map": {field: {"type": "object"} for field in FIELDS},
        "properties": {"type": "object", "properties": {field: {} for field in FIELDS}},
        "required_top_level_fields": {"required_top_level_fields": FIELDS},
    }
    root = Path(args.output_dir)
    for label, contract in variants.items():
        case = copy.deepcopy(original_case)
        case["output_contract"] = contract
        case_path = root / label / "case.json"
        output_dir = root / label / "output"
        write_json(case_path, case)
        if label == "list_strings":
            subprocess.run([
                sys.executable, str(bundle / "scripts" / "finalize.py"),
                "--case", str(case_path), "--output-dir", str(output_dir), "--early-partial",
            ], check=True)
            partial = read_json(output_dir / "result.json")
            assert partial["status"] == "partial"
            assert partial["review_status"] == "not_conducted_no_human_verdicts"
            assert set(partial) == set(FIELDS)
        subprocess.run([
            sys.executable, str(bundle / "scripts" / "finalize.py"),
            "--case", str(case_path), "--item-bank", str(item_bank),
            "--source-evidence", str(sources), "--output-dir", str(output_dir),
        ], check=True)
        result = read_json(output_dir / "result.json")
        assert set(result) == set(FIELDS), (label, list(result))
        assert all(result[field] is not None for field in FIELDS), label
        assert result["status"] == "success", (label, result["summary"] if "summary" in result else result)
        assert result["review_status"] == "not_conducted_no_human_verdicts"
        assert len(result["questions"]) == 4
        assert len(result["benchmark_draft"]["items"]) == 4
        assert len(result["reference_answers"]) == 4
        assert len(result["rubrics"]) == 4
        assert all(set(row["rubric"]) == {"0", "1", "2"} for row in result["rubrics"])
        assert result["evidence"]["sources"] == result["sources"]["sources"]
        assert result["adjudication"]["status"] == "not_applicable"
        assert result["agreement"]["cohen_kappa_unweighted"]["status"] == "not_computed_no_human_verdicts"
        assert result["agreement"]["cohen_kappa_unweighted"]["value"] is None
        assert result["diagnostics"]["main_task_status"] == "success"
        print(f"Contract shape verified: {label}")
    print("All case.json contract shapes exported four primary items successfully without human review or kappa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
