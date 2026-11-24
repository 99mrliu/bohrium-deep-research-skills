#!/usr/bin/env bash
# 合成示例端到端运行（semalign-contract）。所有数据为人工合成，输出不对应
# 任何正式案例结果。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CASE="$HERE/synthetic_case"
WORK="$HERE/work"
OUT="$HERE/out"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

CK="$HERE/../scripts/semalign.py"
echo "== 1) inspect：建档 + 契约 + 字段对齐 + result.json 骨架"
python3 "$CK" inspect --input "$CASE" --work "$WORK" --output "$OUT"

echo "== 2) fill_demo：扮演 Agent 完成真实计算并填充骨架"
python3 "$HERE/fill_demo.py" "$CASE" "$WORK" "$OUT"

echo "== 3) gate：交付前契约门"
python3 "$CK" gate --input "$CASE" --output "$OUT"

echo "== 产物 =="
ls -la "$WORK" "$OUT"
echo "== result.json =="
cat "$OUT/result.json"
