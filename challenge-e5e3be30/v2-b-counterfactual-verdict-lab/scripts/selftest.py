#!/usr/bin/env python3
"""Run the end-to-end SYNTHETIC demo plus dynamic-contract and exit-1 fault tests."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True


def run(arguments: list[str], expected: int) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"exit {result.returncode}, expected {expected}: {' '.join(arguments)}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-root", type=Path, help="Parent for disposable test artifacts; defaults to the system temporary directory")
    parser.add_argument("--bundle-root", type=Path, default=Path(__file__).resolve().parent.parent, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.bundle_root.resolve()
    scripts = root / "scripts"
    examples = root / "examples" / "synthetic"
    test_root = args.test_root if args.test_root is not None else Path(tempfile.gettempdir())
    test_root.mkdir(parents=True, exist_ok=True)
    test_dir = Path(tempfile.mkdtemp(prefix="counterfactual-verdict-lab-", dir=test_root))
    work = test_dir / "work"
    output = test_dir / "output"
    run(
        [
            str(scripts / "run_synthetic_demo.py"),
            "--bundle-root",
            str(root),
            "--work-dir",
            str(work),
            "--output-dir",
            str(output),
        ],
        0,
    )
    final = json.loads((output / "result.json").read_text(encoding="utf-8"))
    report = json.loads((output / "transition-report.json").read_text(encoding="utf-8"))
    assert final["status"] == "success" and final["synthetic"] is True
    assert len(final["probe_verifications"]) == 6
    assert len(final["change_records"]) == 1
    assert report["summary"]["inconsistent"] == 0
    svg = (output / "transition-preview.svg").read_text(encoding="utf-8")
    assert 'data-observed-transition="supported-&gt;contradicted"' in svg
    assert "RE-REVIEW" not in svg

    # The apparently continuous edit changes both negation and direction: design error, exit 1.
    invalid_report = test_dir / "invalid-multipoint-report.json"
    invalid = run(
        [
            str(scripts / "transition_check.py"),
            "--claims",
            str(work / "claims-to-verify.json"),
            "--probe-plan",
            str(examples / "invalid-multipoint-plan.json"),
            "--annotations",
            str(work / "independent-annotations.reviewed.json"),
            "--sources",
            str(work / "sources.json"),
            "--report",
            str(invalid_report),
        ],
        1,
    )
    assert "illegal 2-operator perturbation" in invalid.stderr
    invalid_doc = json.loads(invalid_report.read_text(encoding="utf-8"))
    assert invalid_doc["status"] == "invalid"

    # A list-shaped dynamic contract is tested independently of the dictionary-shaped demo.
    list_case = test_dir / "list-case.json"
    list_case.write_text(
        json.dumps(
            {
                "case_id": "SYNTHETIC-LIST-CONTRACT",
                "output_contract": [
                    {"name": "answer", "type": "string"},
                    "quotation",
                    {"field": "translation", "type": "string"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    list_result = test_dir / "list-result.json"
    run(
        [
            str(scripts / "contract_tools.py"),
            "skeleton",
            "--case-json",
            str(list_case),
            "--output",
            str(list_result),
        ],
        0,
    )
    dynamic = json.loads(list_result.read_text(encoding="utf-8"))
    assert all(key in dynamic for key in ("answer", "quotation", "translation"))
    assert dynamic["status"] == "partial" and dynamic["case_id"] == "SYNTHETIC-LIST-CONTRACT"
    dynamic["sources"] = [{"source_id": "synthetic", "path": "paper.txt"}]
    dynamic["uncertainty"] = ["SYNTHETIC structural test only."]
    dynamic["status"] = "success"
    list_result.write_text(json.dumps(dynamic) + "\n", encoding="utf-8")
    run(
        [
            str(scripts / "contract_tools.py"),
            "validate-final",
            "--case-json",
            str(list_case),
            "--result",
            str(list_result),
        ],
        0,
    )

    print(
        "PASS: end-to-end initial mismatch/re-review/final result; actual-data SVG; "
        "dictionary+list contracts; illegal multipoint exit 1"
    )
    print(f"SYNTHETIC selftest artifacts: {test_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
