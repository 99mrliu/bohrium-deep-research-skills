#!/usr/bin/env bash
# 端到端合成示例（非正式案例结果）：
# decompose(骨架) -> validate/stats(填好的矩阵) -> apply_edits -> letter_build -> coverage_check -> make_result
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
CASE="$HERE/case"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "== 1) decompose：意见 -> 矩阵骨架（演示用，正式流程由 Agent 核对填写）"
python3 "$SKILL_DIR/scripts/decompose.py" --comments "$CASE/materials/reviewer-comments.md" \
  --case "$CASE/case.json" --out "$OUT/matrix_skeleton.json"

echo "== 2) 使用已填好的示例矩阵 examples/matrix.json，校验 + 统计"
cp "$HERE/matrix.json" "$OUT/matrix.json"
python3 "$SKILL_DIR/scripts/matrix.py" validate "$OUT/matrix.json"
python3 "$SKILL_DIR/scripts/matrix.py" stats "$OUT/matrix.json"

echo "== 3) apply_edits：锚点落稿"
python3 "$SKILL_DIR/scripts/apply_edits.py" --manuscript "$CASE/materials/manuscript-baseline.md" \
  --edits "$HERE/edits.json" --outdir "$OUT"

echo "== 4) letter_build：矩阵+改动 -> 回复信 + 证据清单"
python3 "$SKILL_DIR/scripts/letter_build.py" --matrix "$OUT/matrix.json" \
  --changes "$OUT/changes.json" --outdir "$OUT"

echo "== 5) coverage_check：矩阵↔信↔改动 三对齐核验"
python3 "$SKILL_DIR/scripts/coverage_check.py" --matrix "$OUT/matrix.json" \
  --letter "$OUT/response-letter.md" --changes "$OUT/changes.json" \
  --evidence "$OUT/evidence-checklist.md" --out "$OUT/coverage_report.json"

echo "== 6) make_result：result.json（字段名取自 case.json 的 output_contract）"
python3 "$SKILL_DIR/scripts/make_result.py" --case "$CASE/case.json" --status partial \
  --sources "examples/case/materials/manuscript-baseline.md,examples/case/materials/reviewer-comments.md" \
  --uncertainty "合成示例，非正式案例结果；R2 外部验证实验在本演练中无法真实补做（基线为摘要、无原始数据），已以局限性声明+证据清单替代说明；status=partial 以示界限。" \
  --artifact revised_manuscript="$OUT/revised-manuscript.md" \
  --artifact response_letter="$OUT/response-letter.md" \
  --artifact change_locations="$OUT/changes.json" \
  --artifact evidence_checklist="$OUT/evidence-checklist.md" \
  --change-records "$OUT/changes.json" \
  --out "$OUT/result.json"

echo "EXAMPLE RUN OK -> $OUT"
