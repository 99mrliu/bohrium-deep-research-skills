#!/usr/bin/env bash
# run_example.sh — 端到端合成示例（合成示例，非正式案例结果）。
# 流水线：安全网 result.json → 锚点落稿 → forge 交付件 → 渲染预览 → HTML 审查包 → 最终 result.json
# 产物写入 examples/output/（运行产物，不属于 bundle 本体）。
set -euo pipefail

EX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="${SKILL:-$(cd "$EX_DIR/.." && pwd)}"
WORK="$EX_DIR/work"
OUT="$EX_DIR/output"
PY="${PYTHON:-python3}"

echo "== SKILL=$SKILL"
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"
cp "$EX_DIR/decisions.json" "$WORK/decisions.json"

echo "== [0] 预算安全网：先落合法 partial result.json"
"$PY" "$SKILL/scripts/make_result.py" --case "$EX_DIR/case/case.json" \
  --outdir "$OUT" --status partial \
  --uncertainty "处理进行中，交付件尚未生成（安全网占位）"

echo "== [1] apply_edits：最小锚点落稿"
"$PY" "$SKILL/scripts/apply_edits.py" \
  --baseline "$EX_DIR/materials/manuscript-baseline.md" \
  --edits "$EX_DIR/edits.json" --work "$WORK"

echo "== [2] forge_pack：同源锻造交付件"
"$PY" "$SKILL/scripts/forge_pack.py" --work "$WORK" --out "$OUT" --case "$EX_DIR/case/case.json"

echo "== [3] render_preview：渲染 PNG/PDF 预览（matplotlib 缺失时降级不阻断）"
"$PY" "$SKILL/scripts/render_preview.py" --outdir "$OUT/preview" \
  "$OUT/revised-manuscript.md" "$OUT/response-letter.md" "$OUT/change_record.md"

echo "== [4] html_pack：生成自包含 review_pack.html"
"$PY" "$SKILL/scripts/html_pack.py" --work "$WORK" --out "$OUT" --case "$EX_DIR/case/case.json"

echo "== [5] make_result：最终 result.json（含 output_contract 全部字段）"
"$PY" "$SKILL/scripts/make_result.py" --case "$EX_DIR/case/case.json" \
  --outdir "$OUT" --status partial \
  --artifact revised_manuscript="$OUT/revised-manuscript.md" \
  --artifact response_letter="$OUT/response-letter.md" \
  --artifact change_locations="$OUT/change-locations.json" \
  --artifact evidence_checklist="$OUT/evidence-checklist.json" \
  --artifact preview="$OUT/preview" \
  --artifact review_pack="$OUT/review_pack.html" \
  --source "examples/materials/manuscript-baseline.md（合成基线）" \
  --source "examples/materials/reviewer-comments.md（合成意见摘要）" \
  --uncertainty "R1.2 所需对比数据未真实补跑，正文为【待补数据 EV-01】占位" \
  --uncertainty "信头信息为占位待填；回复基于意见摘要而非逐字原文" \
  --change-records "$WORK/changes.json"

echo "== 完成。产物清单："
ls -R "$OUT"
