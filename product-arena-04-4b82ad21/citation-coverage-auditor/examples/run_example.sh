#!/usr/bin/env bash
# run_example.sh - SYNTHETIC EXAMPLE pipeline for the citation-coverage-auditor skill.
# Runs all four scripts on the bundled synthetic case and writes every output
# into examples/sample-output/. Relative paths only; run from anywhere.
set -euo pipefail

cd "$(dirname "$0")"
SKILL_DIR=".."
CASE_DIR="synthetic-case"
OUT="sample-output"
mkdir -p "$OUT"

echo "== 1/4 bib_parse: normalize + cross-check the two bibliography representations"
python3 "$SKILL_DIR/scripts/bib_parse.py" \
  --json "$CASE_DIR/material/references.json" \
  --md   "$CASE_DIR/material/references.md" \
  --out-dir "$OUT"

echo "== 2/4 numbering_check: Vancouver numbering by first appearance (no --fix)"
python3 "$SKILL_DIR/scripts/numbering_check.py" \
  --bib   "$OUT/bib.json" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --out   "$OUT/numbering_report.json"

echo "== 3/4 coverage_ledger: coverage of topics / closest works / recency"
python3 "$SKILL_DIR/scripts/coverage_ledger.py" \
  --case  "$CASE_DIR/case.json" \
  --bib   "$OUT/bib.json" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --out-dir "$OUT"

echo "== 4/4 claimcite_check: claim-to-citation correspondence"
python3 "$SKILL_DIR/scripts/claimcite_check.py" \
  --draft "$CASE_DIR/filled/introduction.md" \
  --claims "$CASE_DIR/filled/claims.json" \
  --bib   "$OUT/bib.json" \
  --out   "$OUT/claimcite_report.json"

echo "ALL CHECKS PASSED (synthetic demo). Outputs are in examples/sample-output/."
