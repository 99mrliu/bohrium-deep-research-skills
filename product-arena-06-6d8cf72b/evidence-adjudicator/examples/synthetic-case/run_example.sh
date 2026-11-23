#!/bin/sh
# 合成示例端到端运行脚本（SYNTHETIC EXAMPLE — 非正式案例）。
# 用法: sh run_example.sh <输出目录>
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
K=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:?"usage: sh run_example.sh <out-dir>"}
mkdir -p "$OUT/src" "$OUT/app-output"

python3 "$K/scripts/chunk_source.py" --text-file "$HERE/paper.txt" \
  --case-id synthetic-evidence-adjudicator-demo --out "$OUT/src"

python3 "$K/scripts/decompose_questions.py" --case "$HERE/case.json" \
  --task "$HERE/task.md" --out "$OUT/questions.json"

echo "--- demo retrieval for q1 (real runs do this per question) ---"
python3 "$K/scripts/retrieve_windows.py" --chunks "$OUT/src/chunks.json" \
  --question "微逆年发电量增益" --terms "8.2|micro-inverter|annual energy" --limit 3

python3 "$HERE/fill_demo_verdicts.py" --chunks "$OUT/src/chunks.json" \
  --out "$OUT/verdicts.json"

python3 "$K/scripts/adjudicate.py" --case "$HERE/case.json" \
  --ledger "$OUT/questions.json" --chunks "$OUT/src/chunks.json" \
  --verdicts "$OUT/verdicts.json" --out "$OUT/app-output"

cp "$OUT/questions.json" "$OUT/verdicts.json" "$OUT/app-output/"
echo "synthetic example finished; inspect $OUT/app-output/result.json"
