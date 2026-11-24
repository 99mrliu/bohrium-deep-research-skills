#!/usr/bin/env bash
# run_example.sh — 在合成示例上跑通整条重算管线。
# 用法: bash examples/run_example.sh
# 说明: 输出写入 examples/expected_output/（已提交的真实运行产物，
#       重跑会原位重新生成；管线是确定性的，内容应保持一致）。
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$DIR/.." && pwd)"
OUT="$DIR/expected_output"
mkdir -p "$OUT"

echo "== 1/3 statmath 自检 =="
python3 "$SKILL_DIR/scripts/statmath.py"

echo "== 2/3 抽取统计量 =="
python3 "$SKILL_DIR/scripts/extract_stats.py" \
    "$DIR/synthetic_excerpt.txt" -o "$OUT/stats.jsonl"

echo "== 3/3 确定性重算 =="
python3 "$SKILL_DIR/scripts/recompute.py" \
    "$OUT/stats.jsonl" -o "$OUT/findings.jsonl"

echo
echo "== findings.jsonl 内容 =="
cat "$OUT/findings.jsonl"
echo
echo "示例运行完成。预期: F 显著性翻转(critical) / HR CI↔p 矛盾(critical) /"
echo "百分比不自洽(major) 被标记; 正确的 t、χ²、r 不被标记。"
