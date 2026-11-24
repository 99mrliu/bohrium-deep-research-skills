#!/usr/bin/env bash
# run_example.sh — 端到端合成示例:intake → 保底 partial → coverage 对账 → 预算账。
# 输出全部写入 examples/output/。本示例使用合成示意案例,非正式测评结果。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$(cd "${HERE}/.." && pwd)"
OUT="${HERE}/output"
WORK="${OUT}/work"

rm -rf "${OUT}"
mkdir -p "${WORK}"

echo "=== [1/4] case_intake:实例化 checklist + 落保底 partial result.json ==="
python3 "${BUNDLE}/scripts/case_intake.py" \
  --case "${HERE}/mock_case.json" \
  --task "${HERE}/mock_task.md" \
  --materials "${HERE}/mock_paper.txt" \
  --checklist-out "${WORK}/checklist.json" \
  --result-out "${OUT}/result.json"

# 保底快照:留存 intake 刚落盘的 partial 骨架,证明任何中断都有合法部分结果
cp "${OUT}/result.json" "${WORK}/result_skeleton_snapshot.json"

echo "=== [2/4] budget_log:记录 intake 相位开销 ==="
python3 "${BUNDLE}/scripts/budget_log.py" \
  --log "${WORK}/budget.jsonl" --phase intake --seconds 4 --requests 1 \
  --note "intake 由脚本完成,模型请求仅 1 次(发起审查)"

echo "=== [3/4] budget_log:记录逐面审查相位(故意只审了引用+伦理两面) ==="
python3 "${BUNDLE}/scripts/budget_log.py" \
  --log "${WORK}/budget.jsonl" --phase "review:citation+ethics" --seconds 120 --requests 9 \
  --note "隐私面被遗漏,用于演示覆盖矩阵抓漏"

echo "=== [4/4] coverage_check:覆盖矩阵对账,更新 result.json ==="
python3 "${BUNDLE}/scripts/coverage_check.py" \
  --checklist "${WORK}/checklist.json" \
  --findings "${HERE}/mock_findings.json" \
  --result-in "${OUT}/result.json" \
  --result-out "${OUT}/result.json" \
  --matrix-out "${OUT}/coverage_matrix.json"

python3 "${BUNDLE}/scripts/budget_log.py" --log "${WORK}/budget.jsonl" --status

echo
echo "=== 输出文件 ==="
ls -l "${OUT}" "${WORK}"
echo
echo "=== result.json 状态摘要 ==="
python3 -c "
import json
r = json.load(open('${OUT}/result.json', encoding='utf-8'))
print('status       :', r['status'])
print('coverage_pct :', r['summary']['coverage_pct'])
print('not_reviewed :', [n['facet'] for n in r['not_reviewed']])
print('findings     :', r['summary']['findings_count'])
"
