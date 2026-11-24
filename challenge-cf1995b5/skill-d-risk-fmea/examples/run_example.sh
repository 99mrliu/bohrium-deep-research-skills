#!/usr/bin/env bash
# run_example.sh — exp-risk-fmea 端到端示例：map -> audit -> decision_tree -> render -> 装配 plan/result
# 用法：bash examples/run_example.sh   （输出写入 examples/output/）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$HERE")"
PY="${PYTHON:-python3}"
OUT="$HERE/output"
NOTE="合成示例输出，非正式测评结果"
mkdir -p "$OUT"

echo "== [1/5] map: 步骤表 -> risk_map.json =="
"$PY" "$SKILL_DIR/scripts/risk_fmea.py" map \
  --case "$HERE/mock_case.json" \
  --steps "$HERE/plan_steps.json" \
  --library "$SKILL_DIR/references/failure_mode_library.md" \
  --out "$OUT/risk_map.json" \
  --note "$NOTE"

echo "== [2/5] audit: 风险完备性审查 -> audit_report.json =="
"$PY" "$SKILL_DIR/scripts/risk_fmea.py" audit \
  --risk-map "$OUT/risk_map.json" \
  --confirmations "$HERE/confirmation_items.json" \
  --out "$OUT/audit_report.json" \
  --note "$NOTE"

echo "== [3/5] decision_tree: 高 RPN -> anomaly_tree.md =="
"$PY" "$SKILL_DIR/scripts/risk_fmea.py" decision_tree \
  --risk-map "$OUT/risk_map.json" \
  --out "$OUT/anomaly_tree.md" \
  --note "$NOTE"

echo "== [4/5] render: 风险章节 -> risk_section.md =="
"$PY" "$SKILL_DIR/scripts/risk_fmea.py" render \
  --risk-map "$OUT/risk_map.json" \
  --out "$OUT/risk_section.md" \
  --note "$NOTE"

echo "== [5/5] 装配 plan.json / plan.md / result.json（示例装配器） =="
"$PY" "$HERE/make_example_plan.py" \
  --case "$HERE/mock_case.json" \
  --steps "$HERE/plan_steps.json" \
  --risk-map "$OUT/risk_map.json" \
  --audit "$OUT/audit_report.json" \
  --risk-section "$OUT/risk_section.md" \
  --confirmations "$HERE/confirmation_items.json" \
  --out-dir "$OUT"

echo "== 完成，输出： =="
ls -la "$OUT"
