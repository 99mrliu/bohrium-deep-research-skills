#!/usr/bin/env bash
# run_example.sh — 合成示例端到端演示（SYNTHETIC EXAMPLE）
# 用法：bash run_example.sh [输出目录，默认 ./out]
set -euo pipefail

OUT="${1:-./out}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/../scripts"
WORK="$OUT/work"
mkdir -p "$WORK" "$OUT"

echo "== [1/6] graph_init（含 --init-result 先写合法部分 result.json） =="
python3 "$SCRIPTS/graph_init.py" \
  --case "$HERE/case.json" --task "$HERE/task.md" \
  --materials "$HERE/source_excerpt.txt" \
  --out "$WORK/graph.json" \
  --init-result --result-out "$OUT/result.json"

echo "== [2/6] graph_link：故意含 1 条孤儿论断 + 1 条错锚点证据 =="
python3 "$SCRIPTS/graph_link.py" \
  --graph "$WORK/graph.json" \
  --answers "$HERE/agent_answers.json" \
  --report "$WORK/link_report_raw.json"
echo "-- 预期：orphans=1, fail=1, conflicts=1（见上方日志与 link_report_raw.json）"

echo "== [3/6] 修复后重新 init + link（agent_answers_fixed.json） =="
python3 "$SCRIPTS/graph_init.py" \
  --case "$HERE/case.json" --task "$HERE/task.md" \
  --materials "$HERE/source_excerpt.txt" \
  --out "$WORK/graph.json"
python3 "$SCRIPTS/graph_link.py" \
  --graph "$WORK/graph.json" \
  --answers "$HERE/agent_answers_fixed.json" \
  --report "$WORK/link_report_fixed.json"
echo "-- 预期：orphans=0, fail=0, conflicts=1"

echo "== [4/6] graph_query：全部预置查询 =="
python3 "$SCRIPTS/graph_query.py" \
  --graph "$WORK/graph.json" \
  --out-json "$WORK/query_report.json" \
  --out-md "$WORK/query_report.md"

echo "== [5/6] 准备合同字段工作文件并 graph_export 交付 =="
cat > "$WORK/result_fields.json" <<'JSON'
{
  "answer_q1": "287 mV（摘录 A，doc1.para1）。",
  "answer_q2": "Tafel 斜率 41 mV/dec，电荷转移动力学较快（摘录 B，doc1.para2）。",
  "answer_q3": "两处来源冲突：摘录 A 报 287 mV（doc1.para1），汇总表报 312 mV（doc1.para4）；应并列报告并注明分歧，见冲突 conf-1。",
  "confidence_note": "q1/q2 单源一致，置信度高；q3 存在 numeric_mismatch 冲突，置信度中等。",
  "uncertainty": ["q3 两源数值不一致，无法从给定材料裁决哪个更可信"],
  "change_records": [
    {"seq": 1, "action": "init", "detail": "graph_init 建图"},
    {"seq": 2, "action": "link", "detail": "graph_link 挂接并核验 5 条论断"},
    {"seq": 3, "action": "repair", "detail": "孤儿论断改诚实标记，错锚点论断改写为原文可查表述"}
  ]
}
JSON
python3 "$SCRIPTS/graph_export.py" \
  --graph "$WORK/graph.json" \
  --case "$HERE/case.json" \
  --work-file "$WORK/result_fields.json" \
  --outdir "$OUT"

echo "== [6/6] 完成。请目检： =="
echo "  - $OUT/evidence_graph.json 中 conflicts 应含 1 条 numeric_mismatch（287 vs 312 mV）"
echo "  - $WORK/query_report.md 中覆盖矩阵、conf-1、未引用锚点 doc1.para3"
echo "  - $OUT/result.json 含 output_contract 四字段 + status=成功"
ls -la "$OUT"
