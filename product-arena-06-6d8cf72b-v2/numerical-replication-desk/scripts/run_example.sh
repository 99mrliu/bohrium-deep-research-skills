#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
  echo "usage: sh scripts/run_example.sh [output_directory]" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
EXAMPLE_DIR="$BUNDLE_DIR/examples/synthetic"
OUTPUT_DIR=${1:-"$EXAMPLE_DIR/output"}
mkdir -p "$OUTPUT_DIR"
export PYTHONDONTWRITEBYTECODE=1
python3 "$BUNDLE_DIR/scripts/nrd.py" run \
  --case "$EXAMPLE_DIR/case.json" \
  --task "$EXAMPLE_DIR/task.md" \
  --materials "$EXAMPLE_DIR/materials" \
  --output-dir "$OUTPUT_DIR" \
  --fail-on-mismatch
printf '%s\n' "SYNTHETIC example outputs written to: $OUTPUT_DIR"
