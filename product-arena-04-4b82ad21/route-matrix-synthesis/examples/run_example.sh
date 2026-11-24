#!/usr/bin/env bash
# run_example.sh -- end-to-end demo of the route-matrix-synthesis pipeline on
# the SYNTHETIC PermaLig case. Writes all outputs into examples/sample-output/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CASE_DIR="$SCRIPT_DIR/synthetic-case"
OUT_DIR="$SCRIPT_DIR/sample-output"
mkdir -p "$OUT_DIR"

echo "== 1/3 build_matrix.py: scaffold from the synthetic bibliography =="
python3 "$SKILL_DIR/scripts/build_matrix.py" \
  --case "$CASE_DIR/case.json" \
  --bib "$CASE_DIR/material/references.json" \
  --facts "$CASE_DIR/material/manuscript-facts.md" \
  --route-keywords "$SKILL_DIR/references/route_keywords.json" \
  --out-dir "$OUT_DIR"

echo "== 2/3 matrix_lint.py: verify the hand-filled matrix =="
python3 "$SKILL_DIR/scripts/matrix_lint.py" \
  --matrix "$CASE_DIR/filled/matrix.json" \
  --bib "$CASE_DIR/material/references.json" \
  --out "$OUT_DIR/lint_report.json"

echo "== 3/3 gap_check.py: verify the filled introduction's gap chain =="
python3 "$SKILL_DIR/scripts/gap_check.py" \
  --case "$CASE_DIR/case.json" \
  --matrix "$CASE_DIR/filled/matrix.json" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --out "$OUT_DIR/gap_report.json"

echo "All example runs passed. Outputs are in: $OUT_DIR"
