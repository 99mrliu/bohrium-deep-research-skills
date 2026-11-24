#!/usr/bin/env bash
# 【合成示例】contract-forge-audit 端到端演示：
#   scaffold（编译契约+骨架）→ render（渲染审查单三件套）→ validate（合格/损坏双路径）
# 用法: bash examples/run_example.sh
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${EXAMPLE_DIR}/.." && pwd)"
SCRIPTS="${SKILL_DIR}/scripts"
OUT="${EXAMPLE_DIR}/run_output"

echo "== [0/5] 清理并创建输出目录: ${OUT}"
rm -rf "${OUT}"
mkdir -p "${OUT}"

echo "== [1/5] contract_scaffold: 从 synthetic_case.json 编译契约并生成 result.json 骨架"
python3 "${SCRIPTS}/contract_scaffold.py" \
  --case "${EXAMPLE_DIR}/synthetic_case.json" \
  --outdir "${OUT}"
# 校验骨架确含 PENDING 哨兵
grep -q 'PENDING::summary' "${OUT}/result.json"
grep -q '"fallback": false' "${OUT}/contract_schema.json"
echo "   骨架含 PENDING 哨兵、schema fallback=false  ✓"

echo "== [2/5] render_audit_sheet: findings.jsonl → md + html + json 同源三件套"
python3 "${SCRIPTS}/render_audit_sheet.py" \
  "${EXAMPLE_DIR}/findings.jsonl" \
  --outdir "${OUT}"
grep -q 'F-001' "${OUT}/audit_sheet.md"
grep -q '待复核' "${OUT}/audit_sheet.html"
echo "   三件套含全部 finding  ✓"

echo "== [3/5] contract_validate: 合格 result.json 应通过（exit 0）"
python3 "${SCRIPTS}/contract_validate.py" \
  --result "${EXAMPLE_DIR}/result_completed.json" \
  --schema "${OUT}/contract_schema.json" \
  --case "${EXAMPLE_DIR}/synthetic_case.json" \
  --report "${OUT}/validation_report.json"
echo "   合格件校验通过  ✓"

echo "== [4/5] contract_validate: 故意损坏的 result.json 应失败（exit != 0）"
set +e
python3 "${SCRIPTS}/contract_validate.py" \
  --result "${EXAMPLE_DIR}/broken_result.json" \
  --schema "${OUT}/contract_schema.json" \
  --case "${EXAMPLE_DIR}/synthetic_case.json" \
  --report "${OUT}/broken_validation_report.json" \
  2> "${OUT}/broken_validate_stderr.txt"
BROKEN_RC=$?
set -e
if [ "${BROKEN_RC}" -eq 0 ]; then
  echo "!! 损坏件竟通过校验，示例失败" >&2
  exit 1
fi
grep -q 'VIOLATION' "${OUT}/broken_validate_stderr.txt"
echo "   损坏件被检出（exit=${BROKEN_RC}），stderr 已存 ${OUT}/broken_validate_stderr.txt  ✓"

echo "== [5/5] 与 expected_output 对照（信息性 diff，不因差异失败）"
diff -r "${EXAMPLE_DIR}/expected_output" "${OUT}" \
  && echo "   与 expected_output 完全一致  ✓" \
  || echo "   （与 expected_output 存在差异，请人工核对）"

echo "== 合成示例端到端运行完成 =="
