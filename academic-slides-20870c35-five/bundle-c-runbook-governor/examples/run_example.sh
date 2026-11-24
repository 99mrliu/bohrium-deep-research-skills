#!/usr/bin/env bash
# SYNTHETIC EXAMPLE / 合成示例 —— deck-runbook-governor 全流程一键演示。
# 用 set +e 捕获每步真实退出码，末尾汇总 EXPECTED vs ACTUAL，全部一致则整体 exit 0。
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT="$BUNDLE_DIR/scripts/contract_init.py"
GATE="$BUNDLE_DIR/scripts/delivery_gate.py"
CKPT="$BUNDLE_DIR/scripts/checkpoint.py"
CASE="$SCRIPT_DIR/case.json"
MATERIALS="$SCRIPT_DIR/materials"
ARTIFACTS="$SCRIPT_DIR/demo_artifacts"
OUT="$SCRIPT_DIR/output_demo"
WORK="$OUT"   # 快照存于 $OUT/checkpoints/ 下，产物与日志一并保留在 examples/output_demo/

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

step "1. contract_init（期望 exit 0，contract.json 含预期点路径）"
python3 "$INIT" --case "$CASE" --out "$OUT" --materials-dir "$MATERIALS"
ec=$?; record 1 0 "$ec" "contract_init"
ok=yes
for dp in "compliance_checks.template_conformance" "compliance_checks.render_checks" "editable_deck" "export_preview" "content_map" "exceptions"; do
  grep -q "\"$dp\"" "$OUT/contract.json" || { ok=no; echo "缺失点路径：$dp"; }
done
grep -q '"audience"' "$OUT/contract.json" || { ok=no; echo "缺失 work_order.audience"; }
grep -q '"sha256"' "$OUT/contract.json" || { ok=no; echo "缺失材料 SHA-256"; }
record 1a yes "$ok" "contract.json 点路径/work_order/SHA-256"

step "2. checkpoint save p0-intake（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" save p0-intake
ec=$?; record 2 0 "$ec" "checkpoint save p0-intake"

step "3. 拷入合成产物 + good_result.json，delivery_gate（期望 exit 0）"
cp -R "$ARTIFACTS/." "$OUT/"
cp "$SCRIPT_DIR/good_result.json" "$OUT/result.json"
python3 "$GATE" --case "$CASE" --out "$OUT" 2>&1 | tee "$OUT/gate_good.log"
ec=${PIPESTATUS[0]}; record 3 0 "$ec" "delivery_gate good"

step "4. checkpoint save p5-delivery（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" save p5-delivery
ec=$?; record 4 0 "$ec" "checkpoint save p5-delivery"

step "5. 拷入 bad_result.json，delivery_gate（期望 exit 1，违例恰好为 D2/D3/D4）"
cp "$SCRIPT_DIR/bad_result.json" "$OUT/result.json"
python3 "$GATE" --case "$CASE" --out "$OUT" > "$OUT/gate_bad.log" 2>&1
ec=$?
cat "$OUT/gate_bad.log"
record 5 1 "$ec" "delivery_gate bad"
for code in D2 D3 D4; do
  if grep -q "^$code:" "$OUT/gate_bad.log"; then
    record "5-$code" present present "bad 输出含 $code"
  else
    record "5-$code" present MISSING "bad 输出缺 $code"
  fi
done
for code in D1 D5 D6; do
  if grep -q "^$code:" "$OUT/gate_bad.log"; then
    record "5-no$code" absent PRESENT "bad 输出不应含 $code"
  else
    record "5-no$code" absent absent "bad 输出不含 $code"
  fi
done

step "6. checkpoint list（期望 exit 0，两个快照）"
python3 "$CKPT" --work "$WORK" list
ec=$?; record 6 0 "$ec" "checkpoint list"

step "7. recover p5-delivery（期望 exit 0），随后复检（期望 exit 0）"
python3 "$CKPT" --out "$OUT" --work "$WORK" recover p5-delivery
ec=$?; record 7 0 "$ec" "checkpoint recover p5-delivery"
python3 "$GATE" --case "$CASE" --out "$OUT" > "$OUT/gate_recovered.log" 2>&1
ec=$?
cat "$OUT/gate_recovered.log"
record 8 0 "$ec" "delivery_gate recovered(=good)"

step "8. 篡改快照内文件 → verify 拒绝（期望 exit 1 且点名文件）；还原后 verify（期望 exit 0）"
VICTIM="$OUT/checkpoints/p5-delivery/result.json"
cp "$VICTIM" "$OUT/_tamper_backup.json"
printf '\n{"tampered": true}\n' >> "$VICTIM"
python3 "$CKPT" --work "$WORK" verify p5-delivery > "$OUT/verify_tampered.log" 2>&1
ec=$?
cat "$OUT/verify_tampered.log"
record 9 1 "$ec" "verify tampered"
if grep -q "result.json" "$OUT/verify_tampered.log"; then
  record 9a present present "篡改报告点名 result.json"
else
  record 9a present MISSING "篡改报告未点名 result.json"
fi
python3 "$CKPT" --out "$OUT" --work "$WORK" recover p5-delivery > "$OUT/recover_tampered.log" 2>&1
ec=$?
cat "$OUT/recover_tampered.log"
record 9b 1 "$ec" "recover tampered 同样被拒绝"
cp "$OUT/_tamper_backup.json" "$VICTIM"
rm -f "$OUT/_tamper_backup.json"
python3 "$CKPT" --work "$WORK" verify p5-delivery
ec=$?; record 10 0 "$ec" "verify restored"

step "9. 损坏 case.json → contract_init（期望 exit 2 且写出 blocked result.json）"
mkdir -p "$OUT/broken_case" "$OUT/broken_out"
printf '{ "case_id": "SYNTH-BROKEN", ' > "$OUT/broken_case/case.json"
python3 "$INIT" --case "$OUT/broken_case/case.json" --out "$OUT/broken_out" > "$OUT/init_broken.log" 2>&1
ec=$?
cat "$OUT/init_broken.log"
record 11 2 "$ec" "contract_init broken"
if grep -q '"blocked_reason"' "$OUT/broken_out/result.json" && grep -q '"blocked"' "$OUT/broken_out/result.json"; then
  record 11a present present "blocked result.json 含 blocked_reason"
else
  record 11a present MISSING "blocked result.json 缺 blocked_reason"
fi

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
