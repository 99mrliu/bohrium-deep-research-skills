#!/usr/bin/env bash
# 合成示例（synthetic），非正式案例结果。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="${1:-$SCRIPT_DIR/output}"

mkdir -p "$OUT/work/pages" "$OUT/work/gate" "$OUT/output"

echo "[1/3] inventory"
python3 "$SKILL_DIR/scripts/inventory.py" \
  --input "$SCRIPT_DIR/input" \
  --work "$OUT/work" \
  --output "$OUT/output" || exit $?

echo "[2/3] extract text"
python3 "$SKILL_DIR/scripts/pdf_text.py" \
  --input "$SCRIPT_DIR/input/paper.txt" \
  --out "$OUT/work/pages/pages.jsonl" || exit $?

echo "[3/3] evidence gate (a FAIL is expected for the fabricated target)"
python3 "$SKILL_DIR/scripts/gate.py" \
  --targets "$SCRIPT_DIR/input/targets.json" \
  --pages "$OUT/work/pages/pages.jsonl" \
  --out "$OUT/work/gate"
GATE_STATUS=$?

echo "gate exit code: $GATE_STATUS"
echo "example output: $OUT"
exit "$GATE_STATUS"
