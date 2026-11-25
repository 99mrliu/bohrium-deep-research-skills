#!/usr/bin/env bash
# 合成示例 / non-official / SYNTHETIC EXAMPLE — not an official answer.
set -euo pipefail

if [ "$#" -gt 1 ]; then
  printf 'Usage: bash examples/synthetic/run_example.sh [OUTPUT_ROOT]\n' >&2
  exit 2
fi

EXAMPLE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILL_ROOT="$(CDPATH= cd -- "$EXAMPLE_DIR/../.." && pwd)"
OUTPUT_ROOT="${1:-$EXAMPLE_DIR/output}"

python3 "$SKILL_ROOT/scripts/argument_loom.py" assemble \
  --case "$EXAMPLE_DIR/case.json" \
  --source "$EXAMPLE_DIR/sources/paper.json" \
  --graph "$EXAMPLE_DIR/graph.input.json" \
  --output-dir "$OUTPUT_ROOT"
python3 "$SKILL_ROOT/scripts/argument_loom.py" check-result \
  --case "$EXAMPLE_DIR/case.json" \
  --result "$OUTPUT_ROOT/result.json" \
  --output "$OUTPUT_ROOT/contract-audit.json"

printf 'SYNTHETIC EXAMPLE outputs: %s\n' "$OUTPUT_ROOT"
