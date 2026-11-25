#!/usr/bin/env python3
"""Run the synthetic happy path and expected-failure validation tests."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

EXAMPLES = Path(__file__).resolve().parent
BUNDLE = EXAMPLES.parent
ASSEMBLER = BUNDLE / "scripts" / "assemble_response.py"
CASE = EXAMPLES / "input" / "case.json"
LABEL = "SYNTHETIC VALIDATION — NOT AN OFFICIAL CASE ANSWER"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_assembler(workdir: Path, workorder: Any, response: Any, cells: Any) -> subprocess.CompletedProcess[str]:
    workdir.mkdir(parents=True, exist_ok=True)
    write(workdir / "workorder.json", workorder)
    write(workdir / "response.json", response)
    write(workdir / "cells.json", cells)
    return subprocess.run(
        [
            sys.executable,
            str(ASSEMBLER),
            "--case",
            str(CASE),
            "--workorder",
            str(workdir / "workorder.json"),
            "--response",
            str(workdir / "response.json"),
            "--cells",
            str(workdir / "cells.json"),
            "--source-root",
            str(EXAMPLES),
            "--output-dir",
            str(workdir / "output"),
            "--output-label",
            LABEL,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def expect_failure(
    name: str,
    expected_message: str,
    base: tuple[Any, Any, Any],
    mutate: Callable[[Any, Any, Any], None],
    parent: Path,
) -> None:
    workorder, response, cells = copy.deepcopy(base)
    mutate(workorder, response, cells)
    completed = run_assembler(parent / name, workorder, response, cells)
    combined = completed.stdout + completed.stderr
    if completed.returncode == 0 or expected_message not in combined:
        raise AssertionError(
            f"{name}: expected nonzero containing {expected_message!r}; "
            f"returncode={completed.returncode}, output={combined}"
        )
    print(f"PASS {name}: rejected with {expected_message!r}")


def main() -> int:
    base = (
        load(EXAMPLES / "input" / "comparison-workorder.json"),
        load(EXAMPLES / "agent-response.json"),
        load(EXAMPLES / "common-cells.json"),
    )
    with tempfile.TemporaryDirectory(prefix=".validation-", dir=EXAMPLES) as temporary:
        root = Path(temporary)

        # The baseline already contains three legitimate not_reported cells.
        happy = run_assembler(root / "not-reported-success", *base)
        if happy.returncode != 0:
            raise AssertionError(f"not_reported success case failed: {happy.stdout + happy.stderr}")
        result = load(root / "not-reported-success" / "output" / "result.json")
        assert result["status"] == "success"
        assert len(result["sources"]) == 3
        assert result["pooled_result_or_separate_values"]["result"] == 76
        for output_name in ("result.json", "comparison-matrix.md", "integration-report.md"):
            assert (root / "not-reported-success" / "output" / output_name).is_file()
        print("PASS not-reported-success: three documents, success status, all outputs created")

        def missing_key(workorder: Any, response: Any, cells: Any) -> None:
            response["fields"].pop("open_questions")

        expect_failure(
            "missing-contract-key", "Missing output_contract key: open_questions", base, missing_key, root
        )

        def fake_locator(workorder: Any, response: Any, cells: Any) -> None:
            cells["cells"][0]["paragraph_id"] = "SYN-A:not-a-real-paragraph"

        expect_failure("fake-locator", "unknown paragraph_id", base, fake_locator, root)

        def single_document(workorder: Any, response: Any, cells: Any) -> None:
            workorder["document_scope"]["in_scope"] = [{"source_document_id": "SYN-A"}]
            cells["documents"] = [cells["documents"][0]]
            cells["cells"] = [
                cell for cell in cells["cells"] if cell["source_document_id"] == "SYN-A"
            ]
            cells["syntheses"] = []
            cells["excluded_from_synthesis"] = []

        expect_failure(
            "single-document-matrix",
            "at least two in-scope documents",
            base,
            single_document,
            root,
        )

        def incomparable_quantitative(workorder: Any, response: Any, cells: Any) -> None:
            cells["syntheses"][0]["member_cell_ids"].append("c-performance")

        expect_failure(
            "incomparable-quantitative-synthesis",
            "pollutant differs among member cells",
            base,
            incomparable_quantitative,
            root,
        )

    print("All 5 validation checks passed (4 expected failures, 1 legitimate success).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, json.JSONDecodeError) as exc:
        print(f"TEST FAILURE: {exc}", file=sys.stderr)
        raise SystemExit(1)
