#!/usr/bin/env python3
"""SYNTHETIC runnable example: valid base, mutation audit, real CLI rejections."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mutation_audit import SEMANTIC_LIMIT, run_audit  # noqa: E402
from scaffold import atomic_write, dumps  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "generated")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = run_audit(output)
    base_path = output / "valid-result.json"
    base_before = hashlib.sha256(base_path.read_bytes()).hexdigest()
    cli_records = []
    for mutation in sorted((output / "corrupted").glob("*.json")):
        command = [
            sys.executable, str(SCRIPTS / "validate_result.py"),
            "--case", str(output / "case.json"),
            "--targets", str(output / "target-fields.json"),
            "--corpus", str(output / "source-corpus.json"),
            "--result", str(mutation),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        try:
            validation = json.loads(completed.stdout)
        except json.JSONDecodeError:
            validation = {"actual_pass": False, "input_error": "validator output was not JSON", "stdout": completed.stdout}
        expected = next(item["expected_rejection_code"] for item in report["mutation_results"] if item["mutation"] == mutation.stem)
        observed = {item.get("code") for item in validation.get("errors", [])}
        passed = completed.returncode != 0 and expected in observed
        record = {
            "mutation": mutation.stem,
            "corrupted_copy": "corrupted/%s" % mutation.name,
            "expected_rejection_code": expected,
            "actual_exit_status": completed.returncode,
            "actual_pass": passed,
            "observed_error_codes": sorted(code for code in observed if code),
            "base_valid_result_sha256": base_before,
        }
        cli_records.append(record)
        print("%s: actual_pass=%s validator_exit=%d expected_code=%s" % (
            mutation.stem, str(passed).lower(), completed.returncode, expected,
        ))
        if completed.returncode == 0:
            print(completed.stdout)
    base_after = hashlib.sha256(base_path.read_bytes()).hexdigest()
    base_unchanged = base_before == base_after

    final_output = output / "finalized"
    final_command = [
        sys.executable, str(SCRIPTS / "finalize.py"),
        "--case", str(output / "case.json"),
        "--targets", str(output / "target-fields.json"),
        "--corpus", str(output / "source-corpus.json"),
        "--draft", str(base_path),
        "--review", str(output / "decoy-review.json"),
        "--output", str(final_output),
    ]
    finalized = subprocess.run(final_command, text=True, capture_output=True, check=False)
    final_ok = finalized.returncode == 0 and (final_output / "result.json").read_bytes() == base_path.read_bytes()
    cli_report = {
        "schema": "synthetic-cli-rejections/v1",
        "synthetic": True,
        "official_case": False,
        "records": cli_records,
        "base_valid_result_sha256_before": base_before,
        "base_valid_result_sha256_after": base_after,
        "base_valid_result_unchanged": base_unchanged,
        "finalizer_actual_exit_status": finalized.returncode,
        "finalizer_reproduced_valid_bytes": final_ok,
        "finalizer_stdout": json.loads(finalized.stdout),
        "overall_actual_pass": (
            report["overall_actual_pass"] and base_unchanged and final_ok
            and all(record["actual_pass"] for record in cli_records)
        ),
        "semantic_limit": SEMANTIC_LIMIT,
    }
    atomic_write(output / "cli-rejections.json", dumps(cli_report))
    print("valid base: actual_pass=%s" % str(report["base"]["actual_pass"]).lower())
    print("finalizer: actual_pass=%s exit=%d byte_identical=%s" % (str(final_ok).lower(), finalized.returncode, str(final_ok).lower()))
    print("valid base unchanged after every mutation: %s" % str(base_unchanged).lower())
    print(SEMANTIC_LIMIT)
    return 0 if cli_report["overall_actual_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
