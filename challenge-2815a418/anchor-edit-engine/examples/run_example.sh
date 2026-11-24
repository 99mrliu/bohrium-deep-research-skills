#!/usr/bin/env bash
# run_example.sh — 端到端合成示例（非正式案例结果）：
#   anchor_map -> apply_edits -> locate_check -> make_result
# 产物写入 examples/output/，中间产物写入 examples/work/。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$HERE")"
CASE="$HERE/case"
WORK="$HERE/work"
OUT="$HERE/output"
mkdir -p "$WORK" "$OUT"

echo "== 0. prepare：先落合法的部分 result.json =="
python3 "$SKILL_ROOT/scripts/make_result.py" \
  --case "$CASE/case.json" \
  --out "$OUT/result.json" \
  --status partial \
  --source "materials/manuscript-baseline.md（合成基线）" \
  --source "materials/reviewer-comments.md（合成意见摘要）" \
  --uncertainty "合成示例，非正式案例结果" \
  --uncertainty "初始化：意见尚未处理"

echo "== 1. anchor_map：基线 -> 锚点图 =="
python3 "$SKILL_ROOT/scripts/anchor_map.py" \
  "$CASE/materials/manuscript-baseline.md" \
  --out "$WORK/anchors.json" --stats

echo "== 2. apply_edits：锚点落稿 =="
python3 "$SKILL_ROOT/scripts/apply_edits.py" \
  --baseline "$CASE/materials/manuscript-baseline.md" \
  --anchors "$WORK/anchors.json" \
  --edits "$HERE/edits.json" \
  --out "$OUT/revised-manuscript.md" \
  --changes "$OUT/changes.json" \
  --report "$WORK/apply_report.json"

echo "== 3. locate_check：回复信三方核验（示例信须与本步 changes.json 一致）=="
python3 "$SKILL_ROOT/scripts/locate_check.py" \
  --letter "$HERE/response-letter.md" \
  --changes "$OUT/changes.json" \
  --revised "$OUT/revised-manuscript.md" \
  --decisions "$HERE/decisions.json" \
  --report "$OUT/locate_report.json"

cp "$HERE/response-letter.md" "$OUT/response-letter.md"
cp "$HERE/evidence-checklist.md" "$OUT/evidence-checklist.md"

echo "== 4. make_result：更新为 success =="
python3 "$SKILL_ROOT/scripts/make_result.py" \
  --case "$CASE/case.json" \
  --out "$OUT/result.json" \
  --status success \
  --uncertainty "R2.1 置信区间因基线缺原始数据未补算，已下调结论强度代替" \
  --artifact revised_manuscript="$OUT/revised-manuscript.md" \
  --artifact response_letter="$OUT/response-letter.md" \
  --artifact change_locations="$OUT/changes.json" \
  --artifact evidence_checklist="$OUT/evidence-checklist.md" \
  --changes "$OUT/changes.json"

echo "EXAMPLE OK：产物在 $OUT"
