#!/usr/bin/env bash
# SYNTHETIC EXAMPLE — slide-qa-rehearsal 问答预演工程一键演示（全合成夹具）。
# 步骤：qa_seed 播种并断言覆盖 limitations/preliminary/objections（含确定性复跑 diff）；
#       qa_gate 对 good 题库期望 exit 0；对 bad 埋雷题库期望 exit 1 且逐个精确报码
#       G1/G2/G3/G4/G5；输入缺失时期望 exit 2。全部符合则打印 ALL EXPECTATIONS MET。
# 用 set +e 捕获每步真实退出码，末尾汇总 EXPECTED vs ACTUAL。
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED="$BUNDLE_DIR/scripts/qa_seed.py"
GATE="$BUNDLE_DIR/scripts/qa_gate.py"
CLAIMS="$SCRIPT_DIR/claims.json"
AUDIENCE="$SCRIPT_DIR/audience.json"
DECK="$SCRIPT_DIR/deck_plan.json"
GOOD="$SCRIPT_DIR/qa_bank_good.json"
BAD="$SCRIPT_DIR/qa_bank_bad.json"
OUT="$SCRIPT_DIR/output_demo"

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

step "1. qa_seed 播种（期望 exit 0）"
python3 "$SEED" --claims "$CLAIMS" --audience "$AUDIENCE" --out "$OUT/qa_bank_seed.json" \
  2>&1 | tee "$OUT/seed.log"
ec=${PIPESTATUS[0]}; record 1 0 "$ec" "qa_seed exit"

step "2. 断言种子覆盖 limitations / preliminary(C-04) / objections(OB-1..3)"
for pat in '"category": "limitation"' '"C-04"' '"OB-1"' '"OB-2"' '"OB-3"'; do
  if grep -q "$pat" "$OUT/qa_bank_seed.json"; then
    record "2-$pat" present present "seed 覆盖 $pat"
  else
    record "2-$pat" present MISSING "seed 缺 $pat"
  fi
done

step "3. qa_seed 确定性复跑（两次输出须逐字节一致）"
python3 "$SEED" --claims "$CLAIMS" --audience "$AUDIENCE" --out "$OUT/qa_bank_seed_2.json" \
  > /dev/null 2>&1
if diff -q "$OUT/qa_bank_seed.json" "$OUT/qa_bank_seed_2.json" > /dev/null; then
  record 3 identical identical "seed 确定性"
else
  record 3 identical DIFFERENT "seed 确定性"
fi
rm -f "$OUT/qa_bank_seed_2.json"

step "4. qa_gate 对 good 题库（期望 exit 0）"
python3 "$GATE" --bank "$GOOD" --deck "$DECK" --claims "$CLAIMS" --audience "$AUDIENCE" \
  2>&1 | tee "$OUT/gate_good.log"
ec=${PIPESTATUS[0]}; record 4 0 "$ec" "qa_gate good"

step "5. qa_gate 对 bad 埋雷题库（期望 exit 1，输出含 G1/G2/G3/G4/G5）"
python3 "$GATE" --bank "$BAD" --deck "$DECK" --claims "$CLAIMS" --audience "$AUDIENCE" \
  > "$OUT/gate_bad.log" 2>&1
ec=$?
cat "$OUT/gate_bad.log"
record 5 1 "$ec" "qa_gate bad"
for code in G1 G2 G3 G4 G5; do
  if grep -q "^$code: " "$OUT/gate_bad.log"; then
    record "5-$code" present present "bad 输出含 $code"
  else
    record "5-$code" present MISSING "bad 输出缺 $code"
  fi
done

step "6. qa_gate 输入缺失（期望 exit 2）"
python3 "$GATE" --bank "$OUT/no_such_bank.json" --deck "$DECK" --claims "$CLAIMS" \
  --audience "$AUDIENCE" > "$OUT/gate_missing.log" 2>&1
ec=$?
cat "$OUT/gate_missing.log"
record 6 2 "$ec" "qa_gate missing input"

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
