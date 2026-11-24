#!/usr/bin/env bash
# run_example.sh — end-to-end proof for the frontier-run-gates bundle.
# GOOD: manifest init + register inputs -> mini_pipeline -> gates G0..G8 pass
#       -> replay_diff byte-identical -> contract_lint clean on the draft.
# BAD:  contract_lint on the booby-trapped result -> exit 1 with exactly the
#       three planted violations (missing field, invalid status, dangling ref).
# All inputs under synthetic_case/ are synthetic/合成 fixtures.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SCRIPTS="$ROOT/scripts"
SYNTH="$HERE/synthetic_case"
OUT="$HERE/example_output"
WORK="$OUT/good_work"

rm -rf "$OUT"
mkdir -p "$OUT/good" "$OUT/bad" "$WORK"
RUNLOG="$OUT/good/run.log"
: > "$RUNLOG"

PY=python3

echo "== GOOD RUN =="

echo "--- step 1: manifest init (scan synthetic_case as /input-style dir) ---"
"$PY" "$SCRIPTS/run_manifest.py" --work "$WORK" init --input-dir "$SYNTH" | tee -a "$RUNLOG"

echo "--- step 2: register inputs explicitly (idempotent re-hash) ---"
"$PY" "$SCRIPTS/run_manifest.py" --work "$WORK" add-input "$SYNTH/corpus.jsonl" >> "$RUNLOG"
"$PY" "$SCRIPTS/run_manifest.py" --work "$WORK" add-input "$SYNTH/case.json" >> "$RUNLOG"

echo "--- step 3: mini_pipeline (deterministic reference stages) ---"
"$PY" "$SCRIPTS/mini_pipeline.py" --work "$WORK" \
  --corpus "$SYNTH/corpus.jsonl" --case "$SYNTH/case.json" | tee -a "$RUNLOG"

echo "--- step 4: gate_check full run G0..G8 ---"
"$PY" "$SCRIPTS/gate_check.py" --work "$WORK" > "$OUT/good/gate_report.json"
cat "$OUT/good/gate_report.json"

echo "--- step 5: replay_diff (determinism proof) ---"
"$PY" "$SCRIPTS/replay_diff.py" --work "$WORK" > "$OUT/good/replay_report.json"
rm -rf "$WORK/replay"   # report already captured; keep the bundle lean
"$PY" - "$OUT/good/replay_report.json" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
assert rep["status"] == "identical", rep
print("PROOF: replay_diff exit=0, all %d stage artifacts byte-identical"
      % len(rep["files"]))
PYEOF

echo "--- step 6: contract_lint on the drafted result ---"
"$PY" "$SCRIPTS/contract_lint.py" --case "$SYNTH/case.json" \
  --result "$WORK/result_draft.json" \
  --evidence-matrix "$WORK/evidence_matrix.jsonl" > "$OUT/good/lint_report.json"
"$PY" - "$OUT/good/lint_report.json" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
assert rep["verdict"] == "clean", rep
print("PROOF: contract_lint exit=0, drafted result is contract-clean "
      "(%d fields, %d refs checked)" % (rep["fields_checked"], rep["refs_checked"]))
PYEOF

echo "--- step 7: assert all gates G0..G8 passed ---"
"$PY" - "$OUT/good/gate_report.json" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
assert rep["status"] == "pass", rep
got = [g["gate"] for g in rep["gates"]]
assert got == ["G0","G1","G2","G3","G4","G5","G6","G7","G8"], got
print("PROOF: gate_check exit=0, gates %s all pass" % ",".join(got))
PYEOF

echo "--- step 8: copy real artifacts to example_output/good/ ---"
cp "$WORK/manifest.json" "$WORK/canon.jsonl" "$WORK/slices.json" \
   "$WORK/cohorts.json" "$WORK/representatives.json" "$WORK/gaps.json" \
   "$WORK/evidence_matrix.jsonl" "$WORK/result_draft.json" "$OUT/good/"
echo "PROOF: example_output/good/ holds real artifacts from this run"

echo
echo "== BAD RUN (expected lint failure) =="
set +e
"$PY" "$SCRIPTS/contract_lint.py" --case "$SYNTH/case.json" \
  --result "$SYNTH/result_bad.json" \
  --evidence-matrix "$WORK/evidence_matrix.jsonl" \
  > "$OUT/bad/lint_bad.json" 2>&1
rc=$?
set -e
cp "$SYNTH/result_bad.json" "$OUT/bad/result_bad.json"
if [ "$rc" -ne 1 ]; then
  echo "PROOF-FAIL: expected contract_lint exit 1 on result_bad.json, got $rc"
  exit 1
fi
"$PY" - "$OUT/bad/lint_bad.json" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
v = rep["violations"]
assert len(v) == 3, "expected exactly 3 violations, got %d: %s" % (len(v), v)
text = "\n".join(v)
assert "missing_field" in text and "research_gaps" in text, v
assert "invalid_status" in text and "'done'" in text, v
assert "dangling_evidence" in text and "SYNTH-R99" in text, v
print("PROOF: bad run exit=1 with exactly the three planted violations:")
for line in v:
    print("  PROOF violation: " + line)
PYEOF

echo
echo "ALL CHECKS PASSED — example_output holds real generated artifacts."
