#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for claim-citation-aligner.
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
python3 "$SKILL_DIR/scripts/ingest_pages.py" \
  "$HERE/synthetic_case/paper.txt" "$WORK/pages.jsonl" || exit 1

echo "== stage 1: citation scan =="
python3 "$SKILL_DIR/scripts/citation_scan.py" \
  --pages "$WORK/pages.jsonl" --out "$WORK/citations.json" || exit 1

echo "== stage 2.5a: matrix_check on the good synthetic matrix (expect PASS) =="
python3 "$SKILL_DIR/scripts/matrix_check.py" \
  --pages "$WORK/pages.jsonl" --scan "$WORK/citations.json" \
  --matrix "$HERE/synthetic_case/alignment_matrix.jsonl" \
  --out "$OUT/matrix_report_good.json"
echo "exit=$? (0 expected)"

echo "== stage 2.5b: matrix_check on the booby-trapped matrix (expect FAIL) =="
python3 "$SKILL_DIR/scripts/matrix_check.py" \
  --pages "$WORK/pages.jsonl" --scan "$WORK/citations.json" \
  --matrix "$HERE/synthetic_case/alignment_matrix_bad.jsonl" \
  --out "$OUT/matrix_report_bad.json"
echo "exit=$? (1 expected: C2/C4/C6/C7 violations planted)"

cp "$WORK/citations.json" "$OUT/"
echo "== done; inspect $OUT =="
exit 0
