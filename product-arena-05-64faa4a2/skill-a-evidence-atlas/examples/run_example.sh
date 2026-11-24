#!/usr/bin/env bash
# 合成示例一键运行（合成示例，非正式案例结果）：
#   ① atlas_scan 扫描 examples/case 建台账 → ② ledger_check 校验 draft.md
# 产物写入 examples/expected/。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
CASE="${HERE}/case"
OUT="${HERE}/expected"
mkdir -p "${OUT}"

echo "== ① atlas_scan：扫描 ${CASE} =="
python3 "${ROOT}/scripts/atlas_scan.py" --input "${CASE}" --out "${OUT}" || exit 2

echo ""
echo "== ② ledger_check：校验 ${CASE}/draft.md =="
python3 "${ROOT}/scripts/ledger_check.py" "${CASE}/draft.md" "${OUT}/atlas.json" --out "${OUT}"
RC=$?

echo ""
if [ "${RC}" -eq 1 ]; then
  echo "ledger_check 退出码 1：符合预期 —— draft.md 中存在 UNSOURCED 数值（编造的 dropout 比率）。"
elif [ "${RC}" -eq 0 ]; then
  echo "ledger_check 退出码 0：全部 BOUND（对本示例而言属异常，请检查）。"
else
  echo "ledger_check 退出码 ${RC}：运行错误。" >&2
  exit "${RC}"
fi
echo "产物已写入 ${OUT}（atlas.json / atlas.md / ledger_report.md / ledger_report.json）"
exit 0
