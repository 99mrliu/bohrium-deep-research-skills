#!/usr/bin/env bash
# run_example.sh — 端到端演示 Bundle D 工作流（合成示例，非正式案例数据）。
# 用法: bash run_example.sh    （任意 cwd 下均可运行；产物写入本目录 output/）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../../scripts"
OUT="$HERE/output"
PY=python3

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== 1/6 inspect_case =="
"$PY" "$SCRIPTS/inspect_case.py" "$HERE/case.json" "$OUT/inspection.json"

echo "== 2/6 score_matrix（决策矩阵+敏感性分析）=="
"$PY" "$SCRIPTS/score_matrix.py" "$HERE/scores.json" "$OUT"

echo "== 3/6 validate_risk_register（预期触发 1 条近似重复警告）=="
"$PY" "$SCRIPTS/validate_risk_register.py" "$HERE/risks.json" "$OUT/risk_register.md"

echo "== 4/6 ethics_path（v3 需办理 IACUC；v2 确认项）=="
"$PY" "$SCRIPTS/ethics_path.py" "$HERE/involvement.json" "$OUT/ethics_paths.md"

echo "== 5/6 check_conditions（总体裁决: 有条件可行）=="
"$PY" "$SCRIPTS/check_conditions.py" "$HERE/conditions.json" "有条件可行" "$OUT/conditions_list.md"

cat > "$OUT/overall_verdict.json" <<'EOF'
{"总体裁决": "有条件可行：v1 需先办结危化品 EHS 备案；v2 需先书面关闭动物涉及判定确认项并锁定设备档期；v3 需先办结 IACUC 审批与危化品 EHS 备案（均为阻断性条件，措辞为“需办理”，不代表已批准）。"}
EOF

echo "== 6/6 assemble_result =="
"$PY" "$SCRIPTS/assemble_result.py" --case "$HERE/case.json" --artifacts "$OUT" \
  --out "$OUT/result.json" --status complete \
  --note "合成示例运行：全部产物由合成输入生成，仅演示工作流，非正式案例结论。"

echo "RUN_EXAMPLE_OK 产物目录: $OUT"
