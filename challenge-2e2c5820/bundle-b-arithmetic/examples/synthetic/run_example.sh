#!/usr/bin/env bash
# run_example.sh — 对合成示例的 3 个方案版本运行完整实算流水线
# 用法: bash run_example.sh   （可在任意 cwd 下运行；脚本内部切到自身目录）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${HERE}/../.." && pwd)"
SCRIPTS="${SKILL_ROOT}/scripts"
CASE="${HERE}/case.json"
OUT="${HERE}/output"
PY="${PYTHON:-python3}"

mkdir -p "${OUT}"

echo "== [0] 结构探针 =="
"${PY}" "${SCRIPTS}/inspect_case.py" "${CASE}" "${OUT}/inspect_map.json"

for v in 1 2 3; do
  EXT="${HERE}/extraction_v${v}.json"
  echo "== [${v}] 校验抽取 extraction_v${v}.json =="
  "${PY}" "${SCRIPTS}/validate_extraction.py" "${EXT}"

  echo "== [${v}] 预算复算 =="
  "${PY}" "${SCRIPTS}/recalc_budget.py" "${EXT}" "${CASE}" "${OUT}/budget_v${v}.md" \
      --json-out "${OUT}/budget_v${v}.json"

  echo "== [${v}] 进度实算（时限自动取自 case.json 预约合同） =="
  "${PY}" "${SCRIPTS}/recalc_schedule.py" "${EXT}" "${OUT}/schedule_v${v}.md" \
      --case "${CASE}" --json-out "${OUT}/schedule_v${v}.json"

  echo "== [${v}] 参数域判定 =="
  "${PY}" "${SCRIPTS}/check_domains.py" "${EXT}" "${CASE}" "${OUT}/domains_v${v}.md" \
      --json-out "${OUT}/domains_v${v}.json"
done

echo "== [装配] result.json =="
"${PY}" "${SCRIPTS}/assemble_result.py" --case "${CASE}" --artifacts "${OUT}" \
    --out "${OUT}/result.json" --status complete \
    --note "合成示例全流水线运行：3 版抽取均通过校验，全部结论由脚本实算"

echo "== 完成。产物位于 ${OUT} =="
ls -1 "${OUT}"
