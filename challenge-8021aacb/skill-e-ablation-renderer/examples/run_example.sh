#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   机械基线 -> 结构图解析 -> 渲染 SVG/HTML -> 双程对照增益报告
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

python3 "$SKILL/scripts/base_pass.py" "$HERE/input/ms.md" "$WORK/base_diag.json"
cp "$HERE/curated_diagnosis.json" "$OUT/diagnosis.json"
python3 "$SKILL/scripts/outline_graph.py" "$HERE/input/ms.md" "$OUT/graph.json"
python3 "$SKILL/scripts/render_maps.py" "$OUT/graph.json" "$OUT/diagnosis.json" "$OUT"
python3 "$SKILL/scripts/gain_compare.py" "$WORK/base_diag.json" "$OUT/diagnosis.json" "$OUT/gain_report.md"
echo "--- gain_report.md 头部 ---"
head -12 "$OUT/gain_report.md"
