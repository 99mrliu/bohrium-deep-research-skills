#!/usr/bin/env bash
# proposal-render-forge 合成示例端到端演示（非正式案例结果）：
#   契约初始化(partial) -> v1 渲染 md/svg/html -> 双跑 cmp 确定性校验
#   -> v1->v2 修订对照 + 修改记录表 -> 坏文档拦截演示 -> result 收尾
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

# 0. 读契约 -> 立即写 partial 骨架；此时 final 校验应判 partial 并点名缺项
python3 "$SKILL/scripts/result_tool.py" init "$HERE/input/case.json" "$WORK/result.json"
python3 "$SKILL/scripts/result_tool.py" final "$WORK/result.json" > "$OUT/final_validation.log"
cp "$WORK/result.json" "$OUT/result_partial.json"

# 1. v1 渲染：可编辑 Markdown（主交付）+ SVG/HTML 预览（纯文本）
python3 "$SKILL/scripts/render_markdown.py" "$HERE/input/document_v1.json" "$OUT/proposal.md"
python3 "$SKILL/scripts/render_preview.py" "$HERE/input/document_v1.json" "$OUT/preview.svg" "$OUT/preview.html"

# 2. 确定性校验：连跑两次 render_markdown，cmp 验证字节一致
python3 "$SKILL/scripts/render_markdown.py" "$HERE/input/document_v1.json" "$WORK/proposal_run2.md"
{
  echo "# 确定性校验：render_markdown 双跑 cmp"
  if cmp -s "$OUT/proposal.md" "$WORK/proposal_run2.md"; then
    echo "run1 vs run2: IDENTICAL ($(wc -c < "$OUT/proposal.md" | tr -d ' ') bytes) —— 确定性渲染通过"
  else
    echo "run1 vs run2: DIFFER —— 确定性渲染失败" >&2
    exit 1
  fi
} > "$OUT/determinism_check.txt"

# 3. 拦截演示：缺 meta 字段、缺第 6 节、schedule 缺表、悬挂引用的坏文档必须被拒
if python3 "$SKILL/scripts/render_markdown.py" "$HERE/input/document_bad.json" "$WORK/bad.md" > "$OUT/schema_fail.log" 2>&1; then
  echo "ERROR: 坏文档未被拦截" >&2
  exit 1
else
  echo "（坏文档按预期被拒绝，渲染器退出码 $?）" >> "$OUT/schema_fail.log"
fi

# 4. 修订留痕：v1 -> v2（模拟导师两处修改），重渲染 + diff 报告 + 修改记录表
python3 "$SKILL/scripts/render_markdown.py" "$HERE/input/document_v2.json" "$WORK/proposal_v2.md"
python3 "$SKILL/scripts/diff_ledger.py" diff "$HERE/input/document_v1.json" "$HERE/input/document_v2.json" "$OUT/diff_report.md"
python3 "$SKILL/scripts/diff_ledger.py" revisions "$HERE/input/document_v2.json" "$OUT/revision_table.md"

# 5. result 收尾：逐契约字段 set -> final 校验（应判 ok）-> 归档
R="$WORK/result.json"
python3 "$SKILL/scripts/result_tool.py" set "$R" proposal_draft "examples/expected/proposal.md"
python3 "$SKILL/scripts/result_tool.py" set "$R" preview_svg "examples/expected/preview.svg"
python3 "$SKILL/scripts/result_tool.py" set "$R" preview_html "examples/expected/preview.html"
python3 "$SKILL/scripts/result_tool.py" set "$R" diff_report "examples/expected/diff_report.md"
python3 "$SKILL/scripts/result_tool.py" set "$R" revision_table "examples/expected/revision_table.md"
python3 "$SKILL/scripts/result_tool.py" set "$R" sources '["examples/input/case.json","examples/input/task.md","examples/input/material_notes.md","examples/input/advisor_feedback.md","examples/input/document_v1.json","examples/input/document_v2.json"]'
python3 "$SKILL/scripts/result_tool.py" set "$R" uncertainty '["示例文献与材料均为合成，非真实出版物/数据源；v2 渲染产物存于 examples/work 未列入交付"]'
python3 "$SKILL/scripts/result_tool.py" final "$R" >> "$OUT/final_validation.log"
cp "$R" "$OUT/result.json"

echo "== 示例运行完成，产物清单 =="
ls -la "$OUT"
