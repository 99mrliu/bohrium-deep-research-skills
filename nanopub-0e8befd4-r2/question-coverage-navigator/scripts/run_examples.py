#!/usr/bin/env python3
"""Run real positive and expected-failure CLI tests; no network is used."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "coverage_tool.py"
MANIFEST = ROOT / "references" / "coverage-manifest.json"


def run(command, expected):
    completed = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True)
    print("$ " + " ".join(str(part) for part in command))
    print((completed.stdout + completed.stderr).strip())
    print(f"exit={completed.returncode} expected={expected}")
    if completed.returncode != expected:
        raise SystemExit(f"Unexpected exit {completed.returncode}; wanted {expected}")
    return completed


def main():
    positive = ROOT / "examples" / "positive"
    negative = ROOT / "examples" / "negative"
    common_pos = [sys.executable, str(TOOL), "--help"]
    help_result = subprocess.run(common_pos, cwd=str(ROOT), text=True, capture_output=True)
    if help_result.returncode != 0:
        raise SystemExit("CLI help failed")
    p_task = str(positive / "input" / "task.md")
    p_case = str(positive / "input" / "case.json")
    p_coverage = str(positive / "input" / "coverage.json")
    p_result = str(positive / "output" / "result.json")
    p_report = str(positive / "output" / "coverage-report.json")
    p_skeleton = str(positive / "work" / "result-skeleton.json")
    base_pos = ["--task", p_task, "--case", p_case, "--manifest", str(MANIFEST)]
    run([sys.executable, str(TOOL), "skeleton", *base_pos, "--output", p_skeleton], 0)
    run([sys.executable, str(TOOL), "build-result", *base_pos, "--coverage", p_coverage, "--output", p_result, "--report", p_report], 0)
    run([sys.executable, str(TOOL), "audit", *base_pos, "--coverage", p_coverage, "--result", p_result, "--report", p_report, "--skeleton", p_skeleton], 0)

    n_task = str(negative / "input" / "task.md")
    n_case = str(negative / "input" / "case.json")
    n_coverage = str(negative / "input" / "coverage.json")
    n_report = str(negative / "output" / "coverage-report.json")
    n_skeleton = str(negative / "work" / "result-skeleton.json")
    base_neg = ["--task", n_task, "--case", n_case, "--manifest", str(MANIFEST)]
    run([sys.executable, str(TOOL), "validate", *base_neg, "--coverage", n_coverage, "--report", n_report, "--skeleton", n_skeleton], 1)

    positive_report = json.loads(Path(p_report).read_text(encoding="utf-8"))
    negative_report = json.loads(Path(n_report).read_text(encoding="utf-8"))
    codes = {gap["code"] for gap in negative_report["gaps"]}
    required = {"answer.missing", "id.dangling"}
    if positive_report is None or not positive_report["ok"]:
        raise SystemExit("Positive report did not pass")
    if negative_report["ok"] or not required.issubset(codes):
        raise SystemExit("Negative fixture did not produce required failures")
    print(json.dumps({"positive_ok": positive_report["ok"], "negative_ok": negative_report["ok"], "negative_gap_codes": sorted(codes), "synthetic_claims": positive_report["summary"]["claims"], "subquestions": positive_report["summary"]["subquestions"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
