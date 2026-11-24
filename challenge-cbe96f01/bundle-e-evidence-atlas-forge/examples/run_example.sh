#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for evidence-atlas-forge.
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
python3 "$SKILL_DIR/scripts/ingest.py" \
  "$HERE/synthetic_case/paper.txt" "$WORK/pages.jsonl" || exit 1

echo "== stage 2a: render good result (expect PASS, exit 0) =="
python3 "$SKILL_DIR/scripts/build_atlas.py" \
  --result "$HERE/synthetic_case/result_draft.json" \
  --pages "$WORK/pages.jsonl" --outdir "$OUT/atlas"
echo "render exit=$? (0 expected)"
python3 "$SKILL_DIR/scripts/page_maps.py" \
  --result "$HERE/synthetic_case/result_draft.json" \
  --pages "$WORK/pages.jsonl" --outdir "$OUT/atlas/pages"

echo "== stage 2b: render stale-evidence result (expect FAIL, exit 1) =="
python3 "$SKILL_DIR/scripts/build_atlas.py" \
  --result "$HERE/synthetic_case/result_stale.json" \
  --pages "$WORK/pages.jsonl" --outdir "$OUT/atlas_stale"
echo "render exit=$? (1 expected: VERIFICATION FAILED badge on planted card)"

echo "== done; open $OUT/atlas/report.html and $OUT/atlas/pages/index.html =="
exit 0
