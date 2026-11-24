#!/usr/bin/env bash
# run_example.sh — 一键跑通 gap-tribunal 三个脚本（合成示例，非正式案例结果）。
# 产物写入 examples/expected/。
# 注意：本示例刻意制造缺口、冲突与套话，hedge_scan 预期以退出码 2（FAIL）结束，
# 这是演示的一部分，不代表脚本错误。
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CASE="$HERE/case"
OUT="$HERE/expected"
mkdir -p "$OUT"

echo "== [1/3] gap_audit =="
python3 "$ROOT/scripts/gap_audit.py" --materials "$CASE" --out-dir "$OUT"
rc1=$?
echo "exit=$rc1"

echo "== [2/3] conflict_matrix =="
python3 "$ROOT/scripts/conflict_matrix.py" --materials "$CASE" --out-dir "$OUT"
rc2=$?
echo "exit=$rc2"

echo "== [3/3] hedge_scan（预期 FAIL，演示告警） =="
python3 "$ROOT/scripts/hedge_scan.py" --md "$CASE/draft.md" --materials "$CASE" \
    --gaps "$OUT/gaps.json" --out-dir "$OUT"
rc3=$?
echo "exit=$rc3 (2=FAIL 为预期)"

echo
echo "产物（examples/expected/）："
ls -1 "$OUT"
echo "完成。gap_audit/conflict_matrix 退出码应为 0；hedge_scan 退出码 2 为预期演示。"
