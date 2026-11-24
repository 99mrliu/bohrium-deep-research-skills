#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for number-recompute-core.
# Inputs under examples/synthetic_case/ are fabricated; outputs are
# illustrative, NOT formal case results.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
WORK="$HERE/work"
OUT="$HERE/example_output"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== stage 0: ingest =="
python3 "$SKILL_DIR/scripts/ingest_text.py" \
  "$HERE/synthetic_case/paper.txt" "$WORK/pages.jsonl" || exit 1

echo "== stage 1: number ledger =="
python3 "$SKILL_DIR/scripts/number_ledger.py" \
  --pages "$WORK/pages.jsonl" --out "$WORK/numbers.jsonl" || exit 1

echo "== stage 2: recompute engine (expect hard contradictions, exit 1) =="
python3 "$SKILL_DIR/scripts/recompute.py" \
  --ledger "$WORK/numbers.jsonl" --pages "$WORK/pages.jsonl" \
  --out "$OUT/contradictions.json"
echo "recompute exit=$? (1 expected: planted N1/N2/N3/N5 hard contradictions + N4 note)"

cp "$WORK/numbers.jsonl" "$OUT/"
echo "== done; inspect $OUT/contradictions.json =="
exit 0
