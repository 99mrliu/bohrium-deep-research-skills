#!/bin/sh
# Reproduce the committed outputs of the synthetic minimal example.
# Python 3 standard library only. Synthetic data — not a real paper.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPTS="$HERE/../../scripts"

python3 "$SCRIPTS/heading_tree.py" \
  --pages "$HERE/inputs/pages.txt" \
  --out "$HERE/outputs"

python3 "$SCRIPTS/refs_parse.py" \
  --pages "$HERE/inputs/pages.txt" \
  --headings "$HERE/outputs/headings.json" \
  --out "$HERE/outputs"

python3 "$SCRIPTS/structure_report.py" \
  --pages "$HERE/inputs/pages.txt" \
  --headings "$HERE/outputs/headings.json" \
  --toc "$HERE/outputs/toc.json" \
  --refs "$HERE/outputs/references.json" \
  --case "$HERE/inputs/case.json" \
  --out "$HERE/outputs"
