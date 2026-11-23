#!/bin/sh
# 合成示例端到端运行脚本（SYNTHETIC EXAMPLE — 非正式案例）。
# 演示流程：init 骨架 -> 写入含两处故意的违规的草稿 -> validate 抓出
# -> 修复 -> finalize success。用法: sh run_example.sh <输出目录>
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
K=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:?"usage: sh run_example.sh <out-dir>"}
mkdir -p "$OUT"

python3 "$K/scripts/pilot.py" init --case "$HERE/case.json" --out "$OUT"

python3 "$HERE/fill_demo_draft.py" --out "$OUT/result.json" --stage draft

python3 "$K/scripts/pilot.py" checkpoint --out "$OUT" --phase t40 \
  --note "draft written (synthetic demo)"

echo "--- validate #1: expect 2 deliberate problems ---"
python3 "$K/scripts/pilot.py" validate --case "$HERE/case.json" \
  --result "$OUT/result.json" --out "$OUT/validation-1.json" || true

python3 "$HERE/fill_demo_draft.py" --out "$OUT/result.json" --stage repaired

echo "--- validate #2 + finalize ---"
python3 "$K/scripts/pilot.py" validate --case "$HERE/case.json" \
  --result "$OUT/result.json" --out "$OUT/validation-2.json"

python3 "$K/scripts/pilot.py" finalize --case "$HERE/case.json" \
  --result "$OUT/result.json" --out "$OUT"

echo "synthetic example finished; inspect $OUT/result.json and audit-trail.jsonl"
