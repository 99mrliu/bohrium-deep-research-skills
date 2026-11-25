#!/usr/bin/env bash
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$HERE/../.." && pwd)"
SCRIPT="$ROOT/scripts/algebra_certificate.py"
PYTHON="${PYTHON:-python3}"

"$PYTHON" "$SCRIPT" init-result \
  --task "$HERE/input/task.md" --input-dir "$HERE/input" \
  --output "$HERE/output/result-initial.json"

"$PYTHON" "$SCRIPT" check \
  --derivation "$HERE/work/derivation.json" \
  --certificate "$HERE/output/certificate.json" \
  --derivation-md "$HERE/output/derivation.md"

"$PYTHON" "$SCRIPT" finalize \
  --task "$HERE/input/task.md" --input-dir "$HERE/input" \
  --answers "$HERE/work/answers.json" \
  --certificate "$HERE/output/certificate.json" \
  --derivation-md "$HERE/output/derivation.md" \
  --output "$HERE/output/result.json"

# Pure graceful test: no package uninstall, monkeypatch, or external resource.
"$PYTHON" "$SCRIPT" check --simulate-no-sympy \
  --derivation "$HERE/work/derivation.json" \
  --certificate "$HERE/output/certificate-unavailable.json" \
  --derivation-md "$HERE/output/derivation-unavailable.md"
"$PYTHON" "$SCRIPT" finalize \
  --task "$HERE/input/task.md" --input-dir "$HERE/input" \
  --answers "$HERE/work/answers.json" \
  --certificate "$HERE/output/certificate-unavailable.json" \
  --derivation-md "$HERE/output/derivation-unavailable.md" \
  --output "$HERE/output/result-unavailable.json"

"$PYTHON" - "$HERE/output" <<'PY'
import json
import pathlib
import sys
out = pathlib.Path(sys.argv[1])
cert = json.loads((out / "certificate.json").read_text())
assert cert["overall_status"] == "falsified", cert["overall_status"]
steps = {step["id"]: step for step in cert["steps"]}
assert steps["E1-valid-expansion"]["status"] == "symbolic_equal"
for key in ("C2-invalid-cancellation-at-zero", "L3-invalid-real-log-power"):
    assert steps[key]["status"] == "falsified", steps[key]
    assert steps[key]["counterexample"] is not None
assert steps["C2-invalid-cancellation-at-zero"]["counterexample"]["assignment"] == {"x": "0"}
assert steps["L3-invalid-real-log-power"]["counterexample"]["assignment"]["x"] in {"-1/2", "-1", "-2", "-3", "-5"}
result = json.loads((out / "result.json").read_text())
assert result["case_id"] == "synthetic-algebra-certificate-001"
assert result["status"] == "failed", result
assert set(result) == {"case_id", "status", "answer", "derivation_summary", "certificate_summary"}
unavailable = json.loads((out / "certificate-unavailable.json").read_text())
assert unavailable["overall_status"] == "unavailable"
assert unavailable["success"] is False
assert all(step["status"] == "undetermined" for step in unavailable["steps"])
unavailable_result = json.loads((out / "result-unavailable.json").read_text())
assert unavailable_result["status"] == "partial"
print("synthetic certificate, counterexample, fail-closed result, and unavailable tests: PASS")
PY
