#!/usr/bin/env python3
"""Run the three-paper synthetic example end to end and assert its key gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_estimands import run  # noqa: E402


def main() -> int:
    result = run(ROOT / "example" / "input", ROOT / "example" / "work", ROOT / "example" / "output")
    decisions = {item["operation_id"]: item for item in result["operation_results"]}
    assert result["case_id"] == "synthetic-estimand-case-001"
    assert result["status"] == "success"
    assert decisions["describe-all"]["allowed"] is True
    assert decisions["direction-a-b"]["allowed"] is True
    assert decisions["rank-a-b"]["allowed"] is False
    assert decisions["pool-a-b"]["allowed"] is False
    assert decisions["transform-a-c"]["allowed"] is True
    assert decisions["rank-a-c-after-transform"]["allowed"] is True
    rank_reasons = decisions["rank-a-b"]["blocking_reasons"]
    assert "UNKNOWN:b-adsorption:budget.value" in rank_reasons
    assert "UNKNOWN:b-adsorption:budget.unit" in rank_reasons
    assert any(item["code"] == "NOT_REPORTED" and item["estimand_id"] == "b-adsorption"
               for item in result["uncertainty"])
    output = ROOT / "example" / "output"
    matrix = (output / "comparison-matrix.md").read_text(encoding="utf-8")
    assert "paper-a" in matrix and "paper-b" in matrix and "paper-c" in matrix
    assert "not_reported" in matrix
    print(json.dumps({
        "example": "PASS", "status": result["status"],
        "decisions": {key: value["allowed"] for key, value in decisions.items()},
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
