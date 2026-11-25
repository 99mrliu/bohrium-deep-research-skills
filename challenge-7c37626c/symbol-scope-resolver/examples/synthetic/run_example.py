#!/usr/bin/env python3
"""Reproducible valid, adversarial, deterministic, and no-formula tests."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
BUNDLE = EXAMPLE.parents[1]
LEDGER = BUNDLE / "scripts" / "ledger.py"
FINALIZE = BUNDLE / "scripts" / "finalize.py"


def run(command: list[str], expected: int = 0, capture: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, capture_output=capture, check=False)
    if proc.returncode != expected:
        if capture:
            print(proc.stdout, file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
        raise AssertionError(f"Expected exit {expected}, got {proc.returncode}: {' '.join(command)}")
    return proc


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    work = EXAMPLE / "work"
    out = EXAMPLE / "out"
    (out / "valid").mkdir(parents=True, exist_ok=True)
    (out / "invalid").mkdir(parents=True, exist_ok=True)
    extract_cmd = [sys.executable, str(LEDGER), "--case", str(EXAMPLE / "case.json"),
                   "--task", str(EXAMPLE / "task.md"), "--work", str(work)]
    run(extract_cmd)
    first_hash = load(work / "ledger.json")["ledger_sha256"]
    run(extract_cmd)
    second_ledger = load(work / "ledger.json")
    assert first_hash == second_ledger["ledger_sha256"], "Ledger digest changed between identical runs"

    run([sys.executable, str(FINALIZE), "--case", str(EXAMPLE / "case.json"), "--work", str(work),
         "--bindings", str(EXAMPLE / "bindings.json"), "--output", str(out / "valid")])
    result = load(out / "valid" / "result.json")
    assert result["case_id"] == "SYNTHETIC-R-SCOPE-001"
    assert result["status"] == "complete"
    assert result["validation"]["valid"] is True
    assert len(result["variables"]) == 4
    plain_r = [row for row in result["variables"] if row["canonical"] == "r"]
    assert len(plain_r) == 2
    meanings = {row["section_id"]: row["binding"]["meaning"] for row in plain_r}
    assert meanings["doc-0001-sec-0001"] != meanings["doc-0001-sec-0002"]
    resistance = next(row for row in plain_r if row["section_id"] == "doc-0001-sec-0002")
    assert resistance["binding"]["unit"]["value"] is None
    assert resistance["binding"]["unit"]["provenance"] == "not_reported"
    assert {row["canonical"] for row in result["variables"]} == {"r", "r_{1}", "r_{2}"}
    assert (out / "valid" / "variable_table.md").is_file()
    assert (out / "valid" / "variable_table.json").is_file()

    # Early finalization with the untouched template must retain outputs, expose
    # incomplete coverage, and use partial rather than silently claiming success.
    (out / "early").mkdir(parents=True, exist_ok=True)
    early = run([sys.executable, str(FINALIZE), "--case", str(EXAMPLE / "case.json"),
                 "--work", str(work), "--bindings", str(work / "bindings.template.json"),
                 "--output", str(out / "early"), "--report", str(out / "early" / "validation.json")],
                expected=2, capture=True)
    (out / "early" / "stdout.txt").write_text(early.stdout, encoding="utf-8")
    (out / "early" / "stderr.txt").write_text(early.stderr, encoding="utf-8")
    early_result = load(out / "early" / "result.json")
    assert early_result["status"] == "partial"
    assert early_result["validation"]["valid"] is False
    assert early_result["case_id"] == "SYNTHETIC-R-SCOPE-001"
    assert len(early_result["formula_occurrences"]) == 2

    invalid = run([sys.executable, str(FINALIZE), "--case", str(EXAMPLE / "case.json"),
                   "--work", str(work), "--bindings", str(EXAMPLE / "bindings.invalid.json"),
                   "--validate-only", "--report", str(out / "invalid" / "validation.json")],
                  expected=2, capture=True)
    (out / "invalid" / "stdout.txt").write_text(invalid.stdout, encoding="utf-8")
    (out / "invalid" / "stderr.txt").write_text(invalid.stderr, encoding="utf-8")
    invalid_report = load(out / "invalid" / "validation.json")
    assert invalid_report["valid"] is False
    assert len(invalid_report["errors"]) >= 5
    assert "validation failed" in invalid.stderr
    invalid_blob = "\n".join(invalid_report["errors"])
    assert "exact substring" in invalid_blob
    assert "omits scoped symbol instances" in invalid_blob
    assert "without coverage/exclusion" in invalid_blob

    # A wholly invented no-formula case exercises dynamic field/status handling
    # and ensures absent numeric evidence is not zero-filled.
    with tempfile.TemporaryDirectory(prefix="symbol-scope-no-formula-") as tmp:
        root = Path(tmp)
        no_case = {
            "case_id": "SYNTHETIC-NO-FORMULA-002",
            "source_text": "An invented note mentions a quantity q but supplies no formula representation and no value for q.",
            "output_contract": {
                "required_fields": ["case_id", "status", "variables", "reported_value", "quality_note"],
                "field_types": {"case_id": "string", "status": "string", "variables": "array",
                                "reported_value": "number", "quality_note": "string"},
                "status_enum": ["complete", "partial", "insufficient_evidence"]
            }
        }
        (root / "case.json").write_text(json.dumps(no_case), encoding="utf-8")
        (root / "task.md").write_text("Return only evidence available in the invented note.", encoding="utf-8")
        (root / "work").mkdir()
        run([sys.executable, str(LEDGER), "--case", str(root / "case.json"),
             "--task", str(root / "task.md"), "--work", str(root / "work")])
        assert not load(root / "work" / "ledger.json")["formulas"]
        empty_bindings = {"schema_version": "symbol-scope-bindings-1", "case_id": no_case["case_id"],
                          "requested_status": None, "symbol_bindings": [], "formula_coverage": [],
                          "limitations": [], "output_fields": {}}
        (root / "work" / "bindings.json").write_text(json.dumps(empty_bindings), encoding="utf-8")
        run([sys.executable, str(FINALIZE), "--case", str(root / "case.json"),
             "--work", str(root / "work"), "--output", str(root / "output")])
        no_result = load(root / "output" / "result.json")
        assert no_result["case_id"] == no_case["case_id"]
        assert no_result["status"] == "insufficient_evidence"
        assert no_result["reported_value"] is None and no_result["reported_value"] != 0
        assert all(field in no_result for field in no_case["output_contract"]["required_fields"])

    summary = {
        "all_passed": True,
        "deterministic_ledger_sha256": first_hash,
        "valid": {"exit": 0, "status": result["status"], "formula_count": 2, "scoped_symbol_count": 4},
        "early_partial": {"expected_exit": 2, "actual_exit": early.returncode,
                          "status": early_result["status"], "outputs_retained": True},
        "adversarial": {"expected_exit": 2, "actual_exit": invalid.returncode,
                        "valid": invalid_report["valid"], "error_count": len(invalid_report["errors"])},
        "no_formula_dynamic_contract": {"expected_exit": 0, "status": "insufficient_evidence",
                                         "reported_value": None, "zero_filled": False},
        "example_data": "wholly invented; no platform data",
    }
    (out / "test_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
