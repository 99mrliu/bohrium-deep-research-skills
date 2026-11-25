#!/bin/sh
# Fully local, deterministic, synthetic plain-text example plus failure tests.
set -eu
export PYTHONDONTWRITEBYTECODE=1
EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$EXAMPLE_DIR/.." && pwd)
mkdir -p "$EXAMPLE_DIR/work" "$EXAMPLE_DIR/output"
python3 "$ROOT_DIR/scripts/run_case.py" \
  --input "$EXAMPLE_DIR/input" \
  --work "$EXAMPLE_DIR/work" \
  --output "$EXAMPLE_DIR/output" \
  --evidence "$EXAMPLE_DIR/input/evidence.json"
python3 "$EXAMPLE_DIR/tests/test_negative.py"
printf '%s\n' "Example outputs: $EXAMPLE_DIR/output"
