#!/bin/sh
# 合成示例端到端运行脚本（SYNTHETIC EXAMPLE — 非正式案例）。
# 用法: sh run_example.sh <输出目录>
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
K=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:?"usage: sh run_example.sh <out-dir>"}
mkdir -p "$OUT/sec" "$OUT/app-output"

python3 "$K/scripts/sectionize.py" --text-file "$HERE/paper.txt" \
  --case-id synthetic-knowledge-atom-demo --out "$OUT/sec"

python3 "$HERE/fill_demo_atoms.py" --sections "$OUT/sec/sections.json" \
  --out "$OUT/atoms.json"

python3 "$K/scripts/kb_lint.py" --atoms "$OUT/atoms.json" \
  --sections "$OUT/sec/sections.json" --out "$OUT/kb-lint.json"

python3 "$K/scripts/kb_index.py" --atoms "$OUT/atoms.json" --out "$OUT/app-output"

python3 "$K/scripts/assemble_result.py" --case "$HERE/case.json" \
  --atoms "$OUT/atoms.json" --lint "$OUT/kb-lint.json" --out "$OUT/app-output"

cp "$OUT/atoms.json" "$OUT/kb-lint.json" "$OUT/app-output/"
echo "synthetic example finished; inspect $OUT/app-output/"
