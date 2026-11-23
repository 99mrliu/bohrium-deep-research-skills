#!/usr/bin/env bash
# run_example.sh — 端到端演示：agreement → adjudicate → checklist
# 输入 passA.json / passB.json 为手工构造的演示标注（非真实模型输出），
# 其中 C2 为定位分歧、C3 为 verdict 分歧、其余一致。
# 用法：bash examples/run_example.sh   （在 skill 根目录或任意目录执行均可）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${HERE}/.." && pwd)"
OUT="${HERE}/out"
mkdir -p "${OUT}"

echo "== [1/3] agreement.py：一致性度量 =="
python3 "${SKILL_ROOT}/scripts/agreement.py" \
    "${HERE}/passA.json" "${HERE}/passB.json" \
    -o "${OUT}/agreement-report.json"

echo
echo "== [2/3] adjudicate.py：保守仲裁 =="
python3 "${SKILL_ROOT}/scripts/adjudicate.py" \
    "${HERE}/passA.json" "${HERE}/passB.json" \
    "${OUT}/agreement-report.json" \
    -o "${OUT}/adjudicated.json" --log "${OUT}/adjudication-log.md"

echo
echo "== [3/3] checklist.py：生成可复用核验清单 =="
python3 "${SKILL_ROOT}/scripts/checklist.py" \
    "${HERE}/claims.json" \
    -o "${OUT}/checklist.csv" --md "${OUT}/checklist.md"

echo
echo "全部完成，产物位于 ${OUT}/"
ls -l "${OUT}"
