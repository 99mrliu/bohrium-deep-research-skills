#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for source-truth-gate.
# All inputs under examples/synthetic_case/ are fabricated for testing;
# outputs are illustrative, NOT formal case results.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
WORK="$HERE/work"
OUT="$HERE/example_output"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== stage 0: ingest =="
python3 "$SKILL_DIR/scripts/ingest_text.py" \
  --input "$HERE/synthetic_case/paper.txt" \
  --out "$WORK/pages.jsonl" --meta "$WORK/ingest_meta.json" || exit 1

echo "== stage 1a: extract references =="
python3 "$SKILL_DIR/scripts/extract_refs.py" \
  --pages "$WORK/pages.jsonl" --out "$WORK/refs.json" || exit 1

echo "== stage 1b: source gate (offline, synthetic snapshot) =="
python3 "$SKILL_DIR/scripts/verify_sources.py" \
  --refs "$WORK/refs.json" --snapshot "$HERE/synthetic_case/trusted_snapshot.json" \
  --out "$OUT/source_report.json"
GATE=$?
echo "gate exit code: $GATE (1 = hard alerts present, expected for this booby-trapped example)"

cp "$WORK/ingest_meta.json" "$WORK/refs.json" "$OUT/"
echo "== done; inspect $OUT/source_report.json =="
exit 0
