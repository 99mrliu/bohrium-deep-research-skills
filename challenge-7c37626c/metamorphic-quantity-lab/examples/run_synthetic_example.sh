#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/metamorphic-quantity-lab-example.XXXXXX")"
WORK_DIR="$EXAMPLE_ROOT/work"
OUTPUT_DIR="$EXAMPLE_ROOT/output"
export PYTHONDONTWRITEBYTECODE=1

python3 "$BUNDLE_ROOT/scripts/verify_case.py" \
  --case "$BUNDLE_ROOT/examples/synthetic_case.json" \
  --task "$BUNDLE_ROOT/examples/task.md" \
  --work-dir "$WORK_DIR" \
  --output "$OUTPUT_DIR/result.json"

SWEEP_PNG="$WORK_DIR/synthetic-energy-speed-sweep_sweep.png"
ARTIFACTS=("$WORK_DIR/analysis.json" "$WORK_DIR/report.md" "$WORK_DIR/synthetic-energy-speed-sweep_sweep.csv")
if [[ -f "$SWEEP_PNG" ]]; then
  ARTIFACTS+=("$SWEEP_PNG")
fi

python3 "$BUNDLE_ROOT/scripts/finalize_result.py" \
  --case "$BUNDLE_ROOT/examples/synthetic_case.json" \
  --task "$BUNDLE_ROOT/examples/task.md" \
  --analysis "$WORK_DIR/analysis.json" \
  --answers "$BUNDLE_ROOT/examples/synthetic_answers.json" \
  --artifacts "${ARTIFACTS[@]}" \
  --output "$OUTPUT_DIR/result.json"

RESULT_PATH="$OUTPUT_DIR/result.json" ANALYSIS_PATH="$WORK_DIR/analysis.json" python3 - <<'PY'
import json
import os
from pathlib import Path

result = json.loads(Path(os.environ["RESULT_PATH"]).read_text(encoding="utf-8"))
analysis = json.loads(Path(os.environ["ANALYSIS_PATH"]).read_text(encoding="utf-8"))
assert result["case_id"] == "synthetic-metamorphic-energy-001"
assert result["status"] == "completed"
assert result["source_claim_verdict"] == "compatible_within_tolerance"
assert analysis["diagnostic_fault_injection_verdict"]["overall"] == "all_injected_faults_detected"
assert all(p["verdict"] == "passed" for p in analysis["property_results"])
print(json.dumps({
    "result_path": os.environ["RESULT_PATH"],
    "report_path": str(Path(os.environ["ANALYSIS_PATH"]).with_name("report.md")),
    "status": result["status"],
    "source_claim_verdict": result["source_claim_verdict"],
    "fault_verdict": analysis["diagnostic_fault_injection_verdict"]["overall"],
    "property_verdicts": {p["property_id"]: p["verdict"] for p in analysis["property_results"]},
    "plot_verdicts": analysis.get("plot_verdicts", []),
}, indent=2, ensure_ascii=False))
PY

printf 'External example work retained at: %s\n' "$EXAMPLE_ROOT"
