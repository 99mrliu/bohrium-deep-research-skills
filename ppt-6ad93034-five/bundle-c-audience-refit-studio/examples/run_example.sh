#!/usr/bin/env bash
# run_example.sh — end-to-end SYNTHETIC demo of audience-refit-studio.
# Runs the good ops (audit must PASS) then a NEGATIVE demo with fabricated
# numbers (audit must FAIL and exit 1 — that non-zero exit is by design and
# the script verifies it).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$ROOT/.." && pwd)"
PY="${PYTHON:-python3}"

export CASE_INPUT_DIR="$ROOT/work/input"
export CASE_WORK_DIR="$ROOT/work"
export CASE_OUTPUT_DIR="$ROOT/output"

rm -rf "$CASE_WORK_DIR" "$CASE_OUTPUT_DIR"
mkdir -p "$CASE_INPUT_DIR" "$CASE_WORK_DIR/artifacts" "$CASE_OUTPUT_DIR"

echo "== [1/9] fixture (SYNTHETIC deck + paper + case + ops) =="
"$PY" "$ROOT/make_fixture.py"

echo "== [2/9] deck_io read: starting-deck.pptx -> model.json =="
"$PY" "$SKILL_DIR/scripts/deck_io.py" read \
  --deck "$CASE_INPUT_DIR/starting-deck.pptx" \
  --out "$CASE_WORK_DIR/model.json"

echo "== [3/9] term_table: locked terminology from paper.txt =="
"$PY" "$SKILL_DIR/scripts/term_table.py" \
  --paper-text "$CASE_WORK_DIR/paper.txt" \
  --deck-model "$CASE_WORK_DIR/model.json"

echo "== [4/9] audience_brief: deterministic editing brief =="
"$PY" "$SKILL_DIR/scripts/audience_brief.py" \
  --workorder "$CASE_WORK_DIR/workorder.json" \
  --terms "$CASE_WORK_DIR/terms.json" \
  --out "$CASE_WORK_DIR/refit_brief.md"

echo "== [5/9] refit_apply (GOOD ops): surgical edit -> output/presentation.pptx =="
"$PY" "$SKILL_DIR/scripts/refit_apply.py" \
  --model "$CASE_WORK_DIR/model.json" \
  --ops "$CASE_WORK_DIR/refit_ops.json" \
  --src "$CASE_INPUT_DIR/starting-deck.pptx" \
  --out "$CASE_OUTPUT_DIR/presentation.pptx"

echo "== [6/9] conserve_check (GOOD ops): must PASS =="
"$PY" "$SKILL_DIR/scripts/conserve_check.py" \
  --before "$CASE_WORK_DIR/model.json" \
  --after "$CASE_OUTPUT_DIR/presentation.pptx" \
  --terms "$CASE_WORK_DIR/terms.json" \
  --paper-text "$CASE_WORK_DIR/paper.txt" \
  --ops "$CASE_WORK_DIR/refit_ops.json" \
  --out "$CASE_OUTPUT_DIR/refit_audit.json"
GOOD_VERDICT=$("$PY" -c 'import json;print(json.load(open("'"$CASE_OUTPUT_DIR"'/refit_audit.json"))["verdict"])')
echo "GOOD-OPS AUDIT VERDICT: $GOOD_VERDICT"
[ "$GOOD_VERDICT" = "PASS" ] || { echo "unexpected: good ops did not PASS"; exit 1; }

echo "== [7/9] NEGATIVE demo (BAD ops fabricate 97.1%): audit must FAIL with exit 1 =="
NEG="$CASE_WORK_DIR/negative_demo"
mkdir -p "$NEG"
"$PY" "$SKILL_DIR/scripts/refit_apply.py" \
  --model "$CASE_WORK_DIR/model.json" \
  --ops "$CASE_WORK_DIR/refit_ops_bad.json" \
  --src "$CASE_INPUT_DIR/starting-deck.pptx" \
  --out "$NEG/presentation_bad.pptx" \
  --change-record "$NEG/change_record_bad.json"
set +e
"$PY" "$SKILL_DIR/scripts/conserve_check.py" \
  --before "$CASE_WORK_DIR/model.json" \
  --after "$NEG/presentation_bad.pptx" \
  --terms "$CASE_WORK_DIR/terms.json" \
  --paper-text "$CASE_WORK_DIR/paper.txt" \
  --ops "$CASE_WORK_DIR/refit_ops_bad.json" \
  --out "$NEG/refit_audit_bad.json"
BAD_RC=$?
set -e
echo "negative-demo conserve_check exit code: $BAD_RC (expected 1)"
if [ "$BAD_RC" -ne 1 ]; then
  echo "NEGATIVE DEMO BROKEN: conserve_check should have exited 1"; exit 1
fi
BAD_VERDICT=$("$PY" -c 'import json;print(json.load(open("'"$NEG"'/refit_audit_bad.json"))["verdict"])')
echo "BAD-OPS AUDIT VERDICT: $BAD_VERDICT"
"$PY" - "$NEG/refit_audit_bad.json" <<'PYEOF'
import json, sys
audit = json.load(open(sys.argv[1]))
named = [l for l in audit["failures"] if "97.1" in l]
assert named, "expected the fabricated 97.1% to be named in the audit failures"
print("fabricated number named in audit:")
for l in named:
    print("  " + l)
PYEOF

echo "== [8/9] optional PDF export when soffice exists =="
if command -v soffice >/dev/null 2>&1; then
  soffice --headless --convert-to pdf --outdir "$CASE_OUTPUT_DIR" \
    "$CASE_OUTPUT_DIR/presentation.pptx" >/dev/null 2>&1 || \
    echo "(soffice conversion failed; continuing gracefully)"
else
  echo "(soffice not found; skipping PDF export — degrade gracefully)"
fi

echo "== [9/9] result.json (contract fields from case.json) =="
"$PY" "$SKILL_DIR/scripts/result_make.py" \
  --case "$CASE_INPUT_DIR/case.json" \
  --out "$CASE_OUTPUT_DIR/result.json" \
  --status success \
  --set-json 'editable_source="'"$CASE_OUTPUT_DIR"'/presentation.pptx"' \
  --set-json 'export_artifact="'"$CASE_OUTPUT_DIR"'/presentation.pdf"' \
  --set-json 'content_map={"0":"0 title (untouched)","1":"1 merged background+gap","2":"3 results re-voiced for advisor (was 3)","3":"NEW next-steps slide cloned from 0"}' \
  --set-json 'compliance_checks=["refit_audit.json verdict=PASS","terms.json locked=6","negative demo correctly flagged fabricated 97.1%"]' \
  --set-json 'synthetic_example=true' \
  --exception "synthetic demo only; negative-demo artifacts under work/negative_demo are not deliverables"
cp "$CASE_WORK_DIR/terms.json" "$CASE_OUTPUT_DIR/terms.json"

echo
echo "== deliverables =="
ls -la "$CASE_OUTPUT_DIR"
echo
echo "ALL STEPS OK (negative demo exited 1 by design)."
