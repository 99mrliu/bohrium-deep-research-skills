#!/usr/bin/env bash
# exp-design-synthesizer 合成示例：enumerate -> score -> select 端到端
# 用法: bash examples/run_example.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$DIR/output"
mkdir -p "$OUT"

NOTICE="合成示例输出，非正式测评结果"

echo "== 1) enumerate: 展开有限参数域 =="
python3 "$DIR/../scripts/design_space.py" enumerate \
  --case "$DIR/mock_case.json" \
  --out "$OUT/design_space.json" \
  --notice "$NOTICE"

echo "== 2) enumerate(缩减): 每因子最多 3 水平 =="
python3 "$DIR/../scripts/design_space.py" enumerate \
  --case "$DIR/mock_case.json" \
  --levels 3 \
  --out "$OUT/design_space_3lvl.json" \
  --notice "$NOTICE"

echo "== 3) score: 3 个候选方案 + 4 个新策略 逐点核算 =="
python3 "$DIR/../scripts/design_space.py" score \
  --case "$DIR/mock_case.json" \
  --strategies "$DIR/strategies.json" \
  --out "$OUT/design_table.json" \
  --notice "$NOTICE"

echo "== 4) select: 在 feasible 设计中选优 =="
python3 "$DIR/../scripts/design_space.py" select \
  --table "$OUT/design_table.json" \
  --out "$OUT/selection.json" \
  --notice "$NOTICE"

echo "完成。输出见 $OUT/"
