#!/usr/bin/env bash
# run_example.sh — exp-schedule-forge 端到端合成示例
# 流程：throughput 体检 3 个候选 + 修订方案 → schedule 排程（预期超期）
#       → repair 修复选项 → 采纳修复后重排 schedule（预期 28 天可行）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${SCHEDULE_FORGE:-$HERE/../scripts/schedule_forge.py}"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "=== [1/4] throughput：候选 v1/v2/v3 + 用户修订方案 rev1 ==="
python3 "$SCRIPT" throughput \
  --case "$HERE/mock_case.json" \
  --plan "$HERE/plan_revised.json" \
  --outdir "$OUT" --synthetic

echo "=== [2/4] schedule：rev1 步骤表排程（预期超期被抓出） ==="
python3 "$SCRIPT" schedule \
  --case "$HERE/mock_case.json" \
  --steps "$HERE/plan_revised.json" \
  --start 2026-01-05 \
  --outdir "$OUT" --synthetic
mv "$OUT/schedule.json" "$OUT/schedule_rev1.json"
mv "$OUT/gantt.md"    "$OUT/gantt_rev1.md"
mv "$OUT/cashflow.md" "$OUT/cashflow_rev1.md"

echo "=== [3/4] repair：超期修复选项表 ==="
python3 "$SCRIPT" repair \
  --case "$HERE/mock_case.json" \
  --steps "$HERE/plan_revised.json" \
  --outdir "$OUT" --synthetic

echo "=== [4/4] schedule：采纳修复后的 rev2 重排（预期 28 天，deadline 内） ==="
python3 "$SCRIPT" schedule \
  --case "$HERE/mock_case.json" \
  --steps "$HERE/plan_repaired.json" \
  --start 2026-01-05 \
  --outdir "$OUT" --synthetic

echo "=== 完成，输出位于 $OUT ==="
ls -la "$OUT"
