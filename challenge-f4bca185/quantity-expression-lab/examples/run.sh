#!/bin/sh
# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE
set -eu
export PYTHONDONTWRITEBYTECODE=1
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUT="$SCRIPT_DIR/synthetic-output"
python3 "$ROOT/scripts/quantity_expression_lab.py" \
  --input "$SCRIPT_DIR/synthetic-input" \
  --work "$SCRIPT_DIR/work" \
  --output "$OUT" \
  --case "$SCRIPT_DIR/synthetic-input/case.json" \
  --task "$SCRIPT_DIR/synthetic-input/task.md"
python3 "$ROOT/scripts/self_test.py"
printf '%s\n' 'SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE: outputs written under examples/synthetic-output.'
