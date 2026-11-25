#!/usr/bin/env python3
"""Meaningful negative test: an unsupported invented connection must fail the gate."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Directory outside the bundle for failed-gate artifacts")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(SCRIPT_DIR / "source_span_atlas.py"),
               "--atlas", str(TEST_DIR / "negative" / "atlas.json"),
               "--output-dir", str(output_dir)]
    completed = subprocess.run(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True)
    atlas_path = output_dir / "atlas.json"
    if not atlas_path.is_file():
        print("Negative test did not produce its failed atlas report", file=sys.stderr)
        return 3
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    codes = [error.get("code") for error in atlas.get("errors", [])]
    figure_absent = not (output_dir / "figure.svg").exists()
    passed = completed.returncode != 0 and atlas.get("verdict") == "failed" and "UNSUPPORTED_ASSERTION" in codes and figure_absent
    payload = {"synthetic": True, "negative_test": "unsupported invented connection", "passed": passed,
               "validator_returncode": completed.returncode, "required_error_code": "UNSUPPORTED_ASSERTION",
               "actual_error_codes": codes, "figure_absent": figure_absent,
               "stdout": completed.stdout, "stderr": completed.stderr}
    (output_dir / "negative_test_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Negative unsupported-assertion gate: %s" % ("PASS" if passed else "FAIL"))
    return 0 if passed else 4


if __name__ == "__main__":
    raise SystemExit(main())
