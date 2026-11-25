#!/usr/bin/env bash
# SYNTHETIC example runner; no network, packages, or binary source fixtures.
set -euo pipefail
EXAMPLE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILL_DIR="$(CDPATH= cd -- "$EXAMPLE_DIR/../.." && pwd)"
OUTPUT_ROOT="${1:-$EXAMPLE_DIR/output}"
mkdir -p -- "$OUTPUT_ROOT"
cp -- "$EXAMPLE_DIR/original_page.svg" "$OUTPUT_ROOT/original_page.svg"
cp -- "$EXAMPLE_DIR/original_cell_crop.svg" "$OUTPUT_ROOT/original_cell_crop.svg"
export PYTHONDONTWRITEBYTECODE=1
python3 "$SKILL_DIR/scripts/atlas_tool.py" validate \
  --atlas "$EXAMPLE_DIR/atlas.json" \
  --text-source "$EXAMPLE_DIR/source.txt" \
  --image-root "$OUTPUT_ROOT" \
  --audit "$OUTPUT_ROOT/audit_report.json"
python3 "$SKILL_DIR/scripts/atlas_tool.py" build \
  --atlas "$EXAMPLE_DIR/atlas.json" \
  --text-source "$EXAMPLE_DIR/source.txt" \
  --case "$EXAMPLE_DIR/case.json" \
  --image-root "$OUTPUT_ROOT" \
  --output-dir "$OUTPUT_ROOT"
printf 'SYNTHETIC atlas generated in %s\n' "$OUTPUT_ROOT"
printf 'Direct inspected-cell evidence is reviewed; absent-body and reading-order limitations keep the result partial.\n'
