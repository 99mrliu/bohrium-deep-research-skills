#!/usr/bin/env bash
# End-to-end SYNTHETIC EXAMPLE for grounded-intro-ledger.
# Runs the full pipeline on the invented demo case and writes real outputs
# into examples/sample-output/. Safe to re-run; it overwrites sample-output.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
CASE="$HERE/synthetic-case/case.json"
DRAFT="$HERE/synthetic-case/filled/introduction.md"
CLAIMS="$HERE/synthetic-case/filled/claims.json"
OUT="$HERE/sample-output"
WORK="$OUT/work"

rm -rf "$OUT"
mkdir -p "$WORK"

echo "== Phase 1: build evidence store =="
python3 "$SKILL_DIR/scripts/extract_sources.py" --case "$CASE" --out-dir "$WORK/evidence"

echo "== Phase 3a: bind claims to verbatim quotes =="
python3 "$SKILL_DIR/scripts/bind_claims.py" --store "$WORK/evidence/evidence_store.json" \
  --claims "$CLAIMS" --out "$WORK/bindings_report.json"

echo "== Phase 3b: grounding audit of the draft =="
cp "$DRAFT" "$OUT/introduction.md"
python3 "$SKILL_DIR/scripts/verify_grounding.py" --store "$WORK/evidence/evidence_store.json" \
  --draft "$OUT/introduction.md" --claims "$CLAIMS" --out "$OUT/verification.json"

echo "== also demonstrate the claims scaffold generator =="
python3 "$SKILL_DIR/scripts/bind_claims.py" --store "$WORK/evidence/evidence_store.json" \
  --scaffold "$DRAFT" --out "$WORK/claims_skeleton.json"

echo
echo "All outputs under $OUT — SYNTHETIC EXAMPLE, invented material only."
