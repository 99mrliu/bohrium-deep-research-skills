#!/usr/bin/env bash
set -euo pipefail
EXAMPLE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$EXAMPLE/../.." && pwd)"
if [[ "$#" -gt 1 ]]; then
  printf 'Usage: %s [writable-verification-directory]\n' "$0" >&2
  exit 64
fi
VERIFY="${1:-$(mktemp -d "${TMPDIR:-/tmp}/paper-figure-twin.XXXXXXXX")}"
case "$VERIFY" in
  "$BUNDLE"|"$BUNDLE"/*)
    printf 'Verification output must be outside the text-only Skill bundle: %s\n' "$VERIFY" >&2
    exit 64
    ;;
esac
WORK="$VERIFY/work"
OUTPUT="$VERIFY/output"
mkdir -p "$WORK" "$OUTPUT" "$VERIFY/pycache" "$VERIFY/negative"
export PYTHONPYCACHEPREFIX="$VERIFY/pycache"
PYTHON="${PYTHON:-python3}"

"$PYTHON" -m py_compile "$BUNDLE/scripts/paper_figure_twin.py" "$BUNDLE/scripts/self_test.py"
set +e
"$PYTHON" "$BUNDLE/scripts/paper_figure_twin.py" compare \
  --case "$EXAMPLE/case.json" --work "$WORK" --output "$OUTPUT" \
  > "$VERIFY/example.stdout.txt" 2> "$VERIFY/example.stderr.txt"
COMPARE_RC=$?
set -e
printf '%s\n' "$COMPARE_RC" > "$VERIFY/comparison.exit_code.txt"
if [[ "$COMPARE_RC" -ne 2 ]]; then
  printf 'Expected complete scientific verdict FAIL (2), got %s\n' "$COMPARE_RC" >&2
  exit 1
fi

"$PYTHON" - "$OUTPUT" "$EXAMPLE" <<'PY'
import csv
import json
from pathlib import Path
import math
import sys
out = Path(sys.argv[1])
example = Path(sys.argv[2]).resolve()
case_contract = json.loads((example / "case.json").read_text(encoding="utf-8"))
comparison = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
result = json.loads((out / "result.json").read_text(encoding="utf-8"))
mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
assert comparison["case_id"] == result["case_id"] == "synthetic-figure-twin-v1"
assert comparison["status"] == result["status"] == "success"
assert comparison["reproduction_verdict"] == result["reproduction_verdict"] == "fail"
assert result["errors"] == [], "numeric disagreement is not a task execution error"
for field in case_contract["output_contract"]["required_fields"]:
    assert field in result, field
for field in ("case_id", "status", "sources", "uncertainty", "change_records"):
    assert field in result, field
assert "output_contract" not in result
assert result["comparison"] == "comparison.json" and result["mapping"] == "mapping.json" and result["report"] == "report.md"
by_candidate = {c["candidate_id"]: c for c in comparison["comparisons"]}
a, b = by_candidate["candidate_a"], by_candidate["candidate_b"]
assert a["within_tolerance"] is True and b["within_tolerance"] is False
assert a["overlap"]["n"] == b["overlap"]["n"] == 9
assert math.isclose(a["metrics"]["rmse"], math.sqrt(0.0005), abs_tol=1e-6)
assert math.isclose(a["metrics"]["mae"], 1.0 / 60.0, abs_tol=1e-5)
assert math.isclose(a["metrics"]["max_error"], 0.03, abs_tol=1e-6)
assert math.isclose(b["metrics"]["max_error"], 0.5, abs_tol=1e-6)
assert len(mapping["paper_series"]["paper_s1"]) == 9
assert all(p["value_status"] == "digitized" and p["source"]["locator"] and p["uncertainty"] for p in mapping["paper_series"]["paper_s1"])
assert not Path(result["sources"]["figure"]["resolved_file"]).is_absolute()
assert not Path(result["sources"]["figure"]["source_file"]).is_absolute()
assert example == (out / result["sources"]["figure"]["resolved_file"]).resolve().parent
for run in result["sources"]["candidates"]:
    assert not Path(run["cwd"]).is_absolute() and not Path(run["output_path"]).is_absolute()
for paper_series in mapping["paper_series"].values():
    assert all(not Path(point["source"]["source_file"]).is_absolute() for point in paper_series)
for candidate in mapping["candidate_series"].values():
    assert not Path(candidate["path"]).is_absolute()
actual_a = mapping["candidate_series"]["candidate_a"]["series"]["a_s1"]["points"]
with (example / "candidate_a.csv").open(encoding="utf-8", newline="") as f:
    fixture_a = [{"x": float(r["x"]), "y": float(r["y"])} for r in csv.DictReader(f)]
assert actual_a == fixture_a, "static candidate_a fixture drifted from executed method output"
actual_b = mapping["candidate_series"]["candidate_b"]["series"]["b_s1"]["points"]
fixture_b = json.loads((example / "candidate_b.json").read_text(encoding="utf-8"))["series"][0]["points"]
assert actual_b == fixture_b, "static candidate_b fixture drifted from executed method output"
required = {"comparison.json", "mapping.json", "report.md", "result.json", "side_by_side.svg", "side_by_side.png"}
for c in comparison["comparisons"]:
    pair = c["pair_id"]
    required.update({pair + "_" + stem for stem in ("overlay.svg", "error.svg", "overlay.png", "error.png")})
assert required <= {p.name for p in out.iterdir()}, required - {p.name for p in out.iterdir()}
for path in out.glob("*.png"):
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and len(data) > 1000, path
print("example assertions: PASS (candidate_a passes, candidate_b legitimately fails tolerances)")
PY

"$PYTHON" "$BUNDLE/scripts/self_test.py" --example "$EXAMPLE" --work "$VERIFY/negative"
"$PYTHON" - "$BUNDLE" "$VERIFY" <<'PY'
from pathlib import Path
import json
import sys
bundle, verify = map(Path, sys.argv[1:])
files = [p for p in bundle.rglob("*") if p.is_file() or p.is_symlink()]
assert len(files) < 20, len(files)
assert not any(p.is_symlink() for p in files)
assert not any(p.name.lower().startswith("readme") for p in files)
for path in files:
    path.read_text(encoding="utf-8", errors="strict")
url = (bundle / "GITHUB_URL.txt").read_text(encoding="utf-8").splitlines()[0]
assert url == "https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/challenge-da62e8d4/paper-figure-twin"
positive = json.loads((verify / "output/result.json").read_text(encoding="utf-8"))
checks = json.loads((verify / "negative/negative_results.json").read_text(encoding="utf-8"))
summary = {
    "bundle_text_file_count": len(files),
    "comparison_exit_code": int((verify / "comparison.exit_code.txt").read_text()),
    "positive_status": positive["status"],
    "positive_reproduction_verdict": positive["reproduction_verdict"],
    "contract_integration_tests": [item["test"] for item in checks["integration"]],
    "run_example_exit_code": 0,
}
(verify / "verification_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary))
PY
