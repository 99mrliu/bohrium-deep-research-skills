#!/bin/sh
# 合成示例端到端运行脚本（SYNTHETIC EXAMPLE — 非正式案例）。
# 用法: sh run_example.sh <输出目录>   例: sh run_example.sh /tmp/sfn-demo
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
K=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:?"usage: sh run_example.sh <out-dir>"}
mkdir -p "$OUT/scan" "$OUT/app-output"

python3 "$K/scripts/fidelity_scan.py" --text-file "$HERE/paper.txt" \
  --case-id synthetic-source-fidelity-demo --out "$OUT/scan"

python3 "$HERE/fill_demo_notes.py" --scan "$OUT/scan" --out "$OUT/notes.json"

python3 "$K/scripts/anchor_check.py" --notes "$OUT/notes.json" \
  --source "$OUT/scan/source.json" --out "$OUT/anchor-report.json"

python3 "$K/scripts/make_result.py" --case "$HERE/case.json" \
  --notes "$OUT/notes.json" --scan "$OUT/scan" \
  --anchor-report "$OUT/anchor-report.json" --out "$OUT/app-output"

echo "synthetic example finished; inspect $OUT/app-output/result.json"
