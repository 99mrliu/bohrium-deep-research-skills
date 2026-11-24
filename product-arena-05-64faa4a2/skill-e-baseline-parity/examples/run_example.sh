#!/usr/bin/env bash
# run_example.sh — 一键演示 baseline-parity 三个脚本（合成示例，非正式案例结果）
# 用法：bash examples/run_example.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CASE="$HERE/case"
OUT="$HERE/expected"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== ① baseline_mine：建基线台账 =="
python3 "$ROOT/scripts/baseline_mine.py" --input "$CASE" --out "$OUT" || {
  echo "baseline_mine 失败"; exit 1; }

echo
echo "== ② parity_check：同预算与统计协议核验 =="
python3 "$ROOT/scripts/parity_check.py" --input "$CASE" \
  --draft "$CASE/draft.md" --out "$OUT" || {
  echo "parity_check 失败"; exit 1; }

echo
echo "== ③ claim_check：比较性论断校验（无支撑论断 => 退出码非零） =="
python3 "$ROOT/scripts/claim_check.py" --draft "$CASE/draft.md" \
  --input "$CASE" --baselines "$OUT/baselines.json" --out "$OUT"
CLAIM_RC=$?
echo "claim_check 退出码 = $CLAIM_RC（1 表示发现无支撑论断，符合本示例预期）"

echo
echo "产物已写入 $OUT："
ls -1 "$OUT"
exit 0
