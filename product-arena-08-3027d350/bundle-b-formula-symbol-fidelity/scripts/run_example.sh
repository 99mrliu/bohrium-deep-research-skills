#!/bin/sh
# run_example.sh — regenerate examples/minimal/outputs from committed inputs.
# Usage: sh scripts/run_example.sh [OUT_DIR]   (default: examples/minimal/outputs)
set -eu
SKILL_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
EX="$SKILL_DIR/examples/minimal"
OUT="${1:-$EX/outputs}"
mkdir -p "$OUT"
python3 "$SKILL_DIR/scripts/math_detect.py" \
    --input "$EX/inputs/words.tsv" --out "$OUT/math_lines.jsonl"
python3 "$SKILL_DIR/scripts/symbol_fidelity.py" \
    --math-lines "$OUT/math_lines.jsonl" --input "$EX/inputs/words.tsv" \
    --out-dir "$OUT"
python3 "$SKILL_DIR/scripts/eq_index.py" \
    --linearized "$OUT/math_linearized.jsonl" \
    --inventory "$OUT/symbol_inventory.json" \
    --case "$EX/inputs/case.json" --out-dir "$OUT"
echo "run_example: outputs written to $OUT"
