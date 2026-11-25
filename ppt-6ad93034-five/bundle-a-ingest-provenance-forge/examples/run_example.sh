#!/usr/bin/env bash
# End-to-end SYNTHETIC example for ingest-provenance-forge.
# Everything produced here is synthetic, not an official case result.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
export CASE_INPUT_DIR="$HERE/work/input"
export CASE_WORK_DIR="$HERE/work/work"
export CASE_OUTPUT_DIR="$HERE/work/app-output"
rm -rf "$HERE/work"
mkdir -p "$CASE_INPUT_DIR" "$CASE_WORK_DIR" "$CASE_OUTPUT_DIR"

echo "== 1/7 make_fixture: synthetic paper.pdf + case.json + task.md"
python3 "$HERE/make_fixture.py"

echo "== 2/7 pdf_ingest: render pages, extract spans, forensics"
python3 "$SKILL_DIR/scripts/pdf_ingest.py" --pdf "$CASE_INPUT_DIR/paper.pdf"

echo "== 3/7 figure_zones: caption zones + figure crops"
python3 "$SKILL_DIR/scripts/figure_zones.py"

echo "== 4/7 make_fixture --emit-plan: agent plan with REAL span ids"
python3 "$HERE/make_fixture.py" --emit-plan

echo "== 5/7 result_make: secure an early PARTIAL result.json"
python3 "$SKILL_DIR/scripts/result_make.py" --status partial \
  --exception "synthetic example: not an official case result"

echo "== 6/7 span_bind + build_deck: fail-closed verification, then build"
python3 "$SKILL_DIR/scripts/span_bind.py" --plan "$CASE_WORK_DIR/plan.json"
python3 "$SKILL_DIR/scripts/build_deck.py" \
  --plan "$CASE_WORK_DIR/plan.json" --bindings "$CASE_WORK_DIR/bindings.json"

echo "== 7/7 result_make: upgrade result.json in place"
EXPORT_ARTIFACT="null"
PDF_CHECK=false
if [ -f "$CASE_OUTPUT_DIR/presentation.pdf" ]; then
  EXPORT_ARTIFACT="\"$CASE_OUTPUT_DIR/presentation.pdf\""
  PDF_CHECK=true
fi
CONTENT_MAP="$(python3 - "$CASE_WORK_DIR/bindings.json" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
m = {}
for bid, e in b.get("evidence_map", {}).items():
    m.setdefault(bid.split("/")[0], []).append(e.get("footer", ""))
print(json.dumps(m))
PY
)"
EXTRA_EXC=()
if ! command -v soffice >/dev/null 2>&1 && ! command -v libreoffice >/dev/null 2>&1; then
  EXTRA_EXC+=(--exception "soffice/libreoffice not on PATH: PDF export and previews skipped")
fi
python3 "$SKILL_DIR/scripts/result_make.py" --status success \
  --set-json "editable_source=\"$CASE_OUTPUT_DIR/presentation.pptx\"" \
  --set-json "export_artifact=$EXPORT_ARTIFACT" \
  --set-json "content_map=$CONTENT_MAP" \
  --check spans_verified=true --check fail_closed_binding=true \
  --check pdf_exported=$PDF_CHECK \
  --set-json 'synthetic_example=true' \
  "${EXTRA_EXC[@]}"

echo
echo "== artifacts (synthetic example) =="
find "$HERE/work" -type f | sort | while read -r f; do
  printf "%10d  %s\n" "$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")" "$f"
done
