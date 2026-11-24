#!/usr/bin/env bash
# 合成示例 / synthetic —— dr-contract-forge 全流程一键演示。
# 用 set +e 捕获每步真实退出码，末尾汇总 EXPECTED vs ACTUAL，全部一致则整体 exit 0。
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT="$BUNDLE_DIR/scripts/contract_init.py"
CHECK="$BUNDLE_DIR/scripts/contract_check.py"
CKPT="$BUNDLE_DIR/scripts/checkpoint.py"
CASE="$SCRIPT_DIR/case.json"
MATERIALS="$SCRIPT_DIR/materials"
OUT="$SCRIPT_DIR/output_demo"
WORK="$OUT"   # 快照存于 $OUT/checkpoints/ 下，产物一并保留在 examples/output_demo/

LINES=()
record() { LINES+=("step=$1 | expected=$2 | actual=$3 | $4"); }
step()   { echo; echo "===== $* ====="; }

step "0. 清理并重建 output_demo"
: "${OUT:?OUT 为空，拒绝删除}"
case "$OUT" in
  *examples/output_demo) ;;
  *) echo "OUT 路径异常，拒绝删除：$OUT"; exit 2 ;;
esac
rm -rf "$OUT"
mkdir -p "$OUT"
echo "OUT=$OUT"

step "1. contract_init（期望 exit 0）"
python3 "$INIT" --case "$CASE" --out "$OUT" --materials-dir "$MATERIALS"
ec=$?; record 1 0 "$ec" "contract_init"

step "2. checkpoint save s1-init（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" save s1-init
ec=$?; record 2 0 "$ec" "checkpoint save s1-init"

step "3. 拷入 good_result.json，contract_check（期望 exit 0）"
cp "$SCRIPT_DIR/good_result.json" "$OUT/result.json"
python3 "$CHECK" --case "$CASE" --out "$OUT" 2>&1 | tee "$OUT/check_good.log"
ec=${PIPESTATUS[0]}; record 3 0 "$ec" "contract_check good"

step "4. checkpoint save s5-delivery（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" save s5-delivery
ec=$?; record 4 0 "$ec" "checkpoint save s5-delivery"

step "5. 拷入 bad_result.json，contract_check（期望 exit 1，输出含 F2/F4/F6）"
cp "$SCRIPT_DIR/bad_result.json" "$OUT/result.json"
python3 "$CHECK" --case "$CASE" --out "$OUT" > "$OUT/check_bad.log" 2>&1
ec=$?
cat "$OUT/check_bad.log"
record 5 1 "$ec" "contract_check bad"
for code in F2 F4 F6; do
  if grep -q "$code" "$OUT/check_bad.log"; then
    record "5-$code" present present "bad 输出含 $code"
  else
    record "5-$code" present MISSING "bad 输出缺 $code"
  fi
done

step "6. checkpoint list（期望 exit 0，两个快照）"
python3 "$CKPT" --work "$WORK" list
ec=$?; record 6 0 "$ec" "checkpoint list"

step "7. recover s5-delivery（期望 exit 0），随后复检（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" recover s5-delivery
ec=$?; record 7 0 "$ec" "checkpoint recover s5-delivery"
python3 "$CHECK" --case "$CASE" --out "$OUT" > "$OUT/check_recovered.log" 2>&1
ec=$?
cat "$OUT/check_recovered.log"
record 8 0 "$ec" "contract_check recovered(=good)"

echo
echo "================ 汇总 EXPECTED vs ACTUAL ================"
fail=0
for line in "${LINES[@]}"; do
  echo "$line"
  rest="${line#*expected=}"; exp="${rest%% *}"
  rest="${line#*actual=}";   act="${rest%% *}"
  if [ "$exp" != "$act" ]; then fail=1; fi
done
echo "========================================================"
if [ "$fail" -eq 0 ]; then
  echo "ALL EXPECTATIONS MET"
  exit 0
else
  echo "EXPECTATION MISMATCH"
  exit 1
fi
