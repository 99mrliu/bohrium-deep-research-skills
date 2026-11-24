#!/usr/bin/env bash
# facet-gap-atlas 合成示例驱动脚本（非正式测试案例）。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/output"
rm -rf "$OUT"; mkdir -p "$OUT"

echo "=== 1) validate 好记录（预期 exit 0，0 错误）==="
python3 "$HERE/../scripts/atlas.py" validate \
    --records "$HERE/input/records_good.jsonl" > "$OUT/validate_good.json"
echo "exit=$?"

echo "=== 2) validate 坏记录（预期 exit 1：缺字段/枚举越界/年份非法）==="
python3 "$HERE/../scripts/atlas.py" validate \
    --records "$HERE/input/records_bad.jsonl" > "$OUT/validate_bad.json" 2>&1
echo "exit=$?"

echo "=== 3) gap 空白分析（task × method_family）==="
python3 "$HERE/../scripts/atlas.py" gap \
    --records "$HERE/input/records_good.jsonl" \
    --facets task,method_family --out "$OUT/atlas"
echo "exit=$?"

echo "=== 产物 ==="
find "$OUT" -type f | sort
