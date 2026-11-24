#!/usr/bin/env bash
# run_example.sh — stat-assumption-tribunal 合成示例全流程演示。
# 任意工作目录下均可执行；所有中间产物写入 examples/synthetic_case/_out/。
# 期望：compare 退出码 2（改判 Mann-Whitney）；verify-claims 退出码 1（恰好 2 条断言 FAIL）。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOL="${BUNDLE_DIR}/scripts/stattool.py"
DATA="${SCRIPT_DIR}/synthetic_case/two_groups_syn.csv"
CLAIMS="${SCRIPT_DIR}/synthetic_case/claims_demo.json"
OUT="${SCRIPT_DIR}/synthetic_case/_out"
mkdir -p "${OUT}"

PY="${PYTHON:-python3}"
overall=0

echo "== 0. selftest（特殊函数数值自检）=="
"${PY}" "${TOOL}" selftest --out "${OUT}/selftest.json"
code=$?
echo "   selftest exit=${code}（期望 0）"
[ "${code}" -eq 0 ] || overall=1

echo "== 1. descriptive --group group（口径显式落盘）=="
"${PY}" "${TOOL}" descriptive --csv "${DATA}" --col value --group group \
    --out "${OUT}/descriptive_value_by_group.json"
code=$?
echo "   descriptive exit=${code}（期望 0）"
[ "${code}" -eq 0 ] || overall=1

echo "== 2. compare（前提裁决；B 组偏态，应改判 Mann-Whitney）=="
"${PY}" "${TOOL}" compare --csv "${DATA}" --group group --value value \
    --out "${OUT}/compare_decision.json"
code=$?
echo "   compare exit=${code}（期望 2 = rerouted，劝告而非失败）"
[ "${code}" -eq 2 ] || overall=1

echo "== 3. corr value vs dosage（Pearson + Spearman）=="
"${PY}" "${TOOL}" corr --csv "${DATA}" --x value --y dosage \
    --out "${OUT}/corr_value_dosage.json"
code=$?
echo "   corr exit=${code}（期望 0）"
[ "${code}" -eq 0 ] || overall=1

echo "== 4. verify-claims（6 条断言，恰 2 条故意写错）=="
"${PY}" "${TOOL}" verify-claims --claims "${CLAIMS}" --csv "${DATA}" \
    --out "${OUT}/verify_claims.json"
code=$?
echo "   verify-claims exit=${code}（期望 1 = 存在 FAIL 断言）"
n_fail=$("${PY}" -c "import json;print(json.load(open('${OUT}/verify_claims.json'))['summary']['fail'])")
echo "   FAIL 断言数=${n_fail}（期望 2）"
{ [ "${code}" -eq 1 ] && [ "${n_fail}" -eq 2 ]; } || overall=1

echo "----------------------------------------------------------"
if [ "${overall}" -eq 0 ]; then
  echo "EXAMPLE RUN: ALL EXPECTATIONS MET"
else
  echo "EXAMPLE RUN: EXPECTATION MISMATCH（见上方各步退出码）"
fi
exit "${overall}"
