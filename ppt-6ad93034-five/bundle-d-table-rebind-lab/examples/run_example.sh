#!/usr/bin/env bash
# run_example.sh - end-to-end SYNTHETIC demo of the table-rebind-lab skill.
# Runs the full pipeline on a fabricated paper and finishes with a NEGATIVE
# DEMO: an audit that MUST fail (exit 1) on a hallucinated "97.1%".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
BASE="$HERE/work"
IN="$BASE/input"
WORK="$BASE/work"
OUT="$BASE/app-output"

rm -rf "$BASE"
mkdir -p "$IN" "$WORK" "$OUT"
export CASE_INPUT_DIR="$IN" CASE_WORK_DIR="$WORK" CASE_OUTPUT_DIR="$OUT"
PY=python3

echo "=== 0. fixture (SYNTHETIC paper, case.json, task.md, spec, plans) ==="
$PY "$HERE/make_fixture.py" --base "$BASE"

echo "=== 0b. secure EARLY partial result.json ==="
$PY "$SKILL_DIR/scripts/result_make.py" --case "$IN/case.json" \
    --out "$OUT/result.json" --status partial \
    --exception "run in progress: early partial secured before pipeline"

echo "=== 1. table_mine (expect status mined) ==="
$PY "$SKILL_DIR/scripts/table_mine.py" --pdf "$IN/paper.pdf"
grep -q '"status": "mined"' "$WORK/tables.json" \
    || { echo "FAIL: table-1 was not mined"; exit 1; }

echo "=== 2. figure_harvest ==="
$PY "$SKILL_DIR/scripts/figure_harvest.py" --pdf "$IN/paper.pdf"

echo "=== 3. replot (matplotlib present; --example-mode) ==="
$PY "$SKILL_DIR/scripts/replot.py" --spec "$WORK/replot_spec.json" --example-mode

echo "=== 4. number_audit (good plan, expect PASS) ==="
$PY "$SKILL_DIR/scripts/number_audit.py" --plan "$WORK/plan.json" \
    --paper-text "$WORK/paper.txt" --tables "$WORK/tables.json" \
    --figures "$WORK/figures.json" --out "$OUT/number_audit.json"

echo "=== 5. build_deck ==="
$PY "$SKILL_DIR/scripts/build_deck.py" --plan "$WORK/plan.json" \
    --audit "$OUT/number_audit.json"

echo "=== 6. final result.json ==="
$PY "$SKILL_DIR/scripts/result_make.py" --case "$IN/case.json" \
    --out "$OUT/result.json" --status success \
    --set-json 'synthetic_example=true' \
    --set-json 'editable_source="presentation.pptx"' \
    --set-json 'compliance_checks={"number_audit":"PASS","native_table":true,"verbatim_replot":true,"no_pixel_estimation":true}' \
    --exception "soffice absent on this machine: presentation.pdf/previews skipped (pptx is the deliverable)"

echo "=== 7. NEGATIVE DEMO: hallucinated number must fail the audit ==="
set +e
NEG="$($PY "$SKILL_DIR/scripts/number_audit.py" --plan "$WORK/plan_bad.json" \
    --paper-text "$WORK/paper.txt" --tables "$WORK/tables.json" \
    --figures "$WORK/figures.json" --out "$WORK/number_audit_bad.json" 2>&1)"
NEG_CODE=$?
set -e
echo "$NEG"
if [ "$NEG_CODE" -ne 1 ]; then
    echo "NEGATIVE DEMO FAILED: expected exit 1, got $NEG_CODE"; exit 1
fi
echo "$NEG" | grep -q "97.1" \
    || { echo "NEGATIVE DEMO FAILED: message does not name 97.1"; exit 1; }
echo "negative demo OK: audit exit 1 naming the hallucinated 97.1%"

echo "=== 8. artifacts ==="
find "$WORK" "$OUT" -type f | sort
echo "=== run_example.sh DONE (synthetic demo) ==="
