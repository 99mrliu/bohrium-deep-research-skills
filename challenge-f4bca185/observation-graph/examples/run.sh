#!/bin/sh
set -eu
# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/.." && pwd)
python3 "$ROOT/scripts/observation_graph.py" \
  --input "$HERE/synthetic-input" \
  --work "$HERE/synthetic-work" \
  --output "$HERE/synthetic-output" \
  --case "$HERE/synthetic-input/case.json" \
  --task "$HERE/synthetic-input/task.json"
