#!/bin/sh
# 合成示例端到端运行脚本（SYNTHETIC EXAMPLE — 非正式案例）。
# 用法: sh run_example.sh <输出目录>
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
K=$(CDPATH= cd -- "$HERE/../.." && pwd)
OUT=${1:?"usage: sh run_example.sh <out-dir>"}
mkdir -p "$OUT"

python3 "$HERE/fill_demo_notes.py" --paper "$HERE/paper.txt" --case "$HERE/case.json" \
  --out-notes "$OUT/notes.json" --out-result "$OUT/result.json"

python3 "$K/scripts/render_notes.py" --notes "$OUT/notes.json" --out "$OUT/notes.md"

python3 "$K/scripts/render_preview.py" --md "$OUT/notes.md" --notes "$OUT/notes.json" \
  --out-html "$OUT/preview.html" --out-png "$OUT/preview.png"

python3 "$K/scripts/reuse_pack.py" --notes "$OUT/notes.json" \
  --inputs "$HERE/paper.txt" --artifacts "$OUT/result.json" "$OUT/notes.md" \
  --out "$OUT"

python3 "$K/scripts/check_delivery.py" --out "$OUT" --case "$HERE/case.json"

echo "synthetic example finished; inspect $OUT/ (notes.md, preview.html, manifest.json)"
