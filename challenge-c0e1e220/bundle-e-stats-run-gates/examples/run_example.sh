#!/bin/bash
# run_example.sh — stats-run-gates 端到端合成示例（明确标注：合成示例，数据由 make_synthetic.py 人工生成）
# (a) 好例：生成 → run → decide --confirm-all → finalize → gate_check/lint/manifest check/replay_diff 全 exit 0
# (b) 埋雷：result_bad.json（status="success" 非法、缺 hypothesis_test、case_id 错）
#     → contract_lint 必须 exit 1 且命中 INVALID_STATUS / MISSING_FIELD / CASE_ID_MISMATCH
# (c) 埋雷：report.md 篡改一个 p 值 → gate_check 必须 exit 1 且命中 G6 REPORT_NUMBER_DRIFT
# 全部断言通过才 exit 0。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
SCR="$SKILL_DIR/scripts"
TMP="$(mktemp -d /tmp/stats_run_gates_example.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
IN="$TMP/input"; WORK="$TMP/work"; OUT="$TMP/output"
LOG="$TMP/checks.log"
: > "$LOG"
FAILS=0

note() { echo "[example] $*" | tee -a "$LOG"; }
bad()  { echo "[example][ASSERT-FAIL] $*" | tee -a "$LOG"; FAILS=$((FAILS+1)); }

note "== 0. 生成合成示例数据 =="
python3 "$HERE/make_synthetic.py" --out "$IN" >>"$LOG" 2>&1 || bad "make_synthetic 失败"
mkdir -p "$WORK" "$OUT"

note "== 1a. 好例：pipeline run =="
python3 "$SCR/pipeline_e.py" run --input "$IN" --work "$WORK" --output "$OUT" >>"$LOG" 2>&1 \
  || bad "pipeline run 非零退出"
note "== 1b. decide --confirm-all + finalize =="
python3 "$SCR/pipeline_e.py" decide --work "$WORK" --confirm-all >>"$LOG" 2>&1 || bad "decide 失败"
python3 "$SCR/pipeline_e.py" finalize --input "$IN" --work "$WORK" --output "$OUT" >>"$LOG" 2>&1 || bad "finalize 失败"
python3 -m json.tool "$OUT/result.json" >/dev/null 2>&1 || bad "result.json 非法 JSON"

note "== 1c. gate_check（期望 exit 0）=="
python3 "$SCR/gate_check.py" --input "$IN" --work "$WORK" --output "$OUT" >>"$LOG" 2>&1
[ $? -eq 0 ] || bad "gate_check 好例未通过"

note "== 1d. contract_lint（期望 exit 0）=="
python3 "$SCR/contract_lint.py" --case "$IN/case.json" --result "$OUT/result.json" >>"$LOG" 2>&1
[ $? -eq 0 ] || bad "contract_lint 好例未通过"

note "== 1e. run_manifest check（期望 exit 0）=="
python3 "$SCR/run_manifest.py" check --input "$IN" --work "$WORK" --output "$OUT" >>"$LOG" 2>&1
[ $? -eq 0 ] || bad "run_manifest check 未通过"

note "== 1f. replay_diff 影子复跑（期望 exit 0，逐字节一致）=="
python3 "$SCR/replay_diff.py" --input "$IN" --work "$WORK" --output "$OUT" >>"$LOG" 2>&1
[ $? -eq 0 ] || bad "replay_diff 未通过（产物非确定）"

note "== 2. 埋雷 b：坏 result.json（INVALID_STATUS + MISSING_FIELD + CASE_ID_MISMATCH）=="
python3 - "$OUT/result.json" "$TMP/result_bad.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
r["status"] = "success"          # 非法枚举
r.pop("hypothesis_test", None)   # 缺契约字段
r["case_id"] = "case-WRONG"      # case_id 不一致
json.dump(r, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
B_OUT="$TMP/lint_bad.txt"
python3 "$SCR/contract_lint.py" --case "$IN/case.json" --result "$TMP/result_bad.json" >"$B_OUT" 2>&1
[ $? -eq 1 ] || bad "contract_lint 埋雷 b 未 exit 1"
for code in INVALID_STATUS MISSING_FIELD CASE_ID_MISMATCH; do
  grep -q "$code" "$B_OUT" || bad "埋雷 b 未命中 $code"
done
cat "$B_OUT" >>"$LOG"

note "== 3. 埋雷 c：report.md 篡改一个 p 值（期望 G6 REPORT_NUMBER_DRIFT exit 1）=="
cp -R "$OUT" "$TMP/output_bad"
python3 - "$TMP/output_bad/report.md" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t2 = re.sub(r"p = \d+\.\d+", "p = 0.0000", t, count=1)  # 0.0000 不可能出现在合法 token 集
assert t2 != t, "未找到可篡改的 p token"
open(p, "w", encoding="utf-8").write(t2)
PY
C_OUT="$TMP/gate_bad.txt"
python3 "$SCR/gate_check.py" --input "$IN" --work "$WORK" --output "$TMP/output_bad" >"$C_OUT" 2>&1
[ $? -eq 1 ] || bad "gate_check 埋雷 c 未 exit 1"
grep -q "G6" "$C_OUT" || bad "埋雷 c 未命中 G6"
grep -q "REPORT_NUMBER_DRIFT" "$C_OUT" || bad "埋雷 c 未命中 REPORT_NUMBER_DRIFT"
cat "$C_OUT" >>"$LOG"

note "== 4. 归档真实产物到 example_output/ =="
EX="$HERE/example_output"
mkdir -p "$EX"
cp "$WORK/manifest.json" "$EX/manifest.json"
cp "$WORK/stage_02_clean.json" "$EX/stage_02_clean.json"
cp "$WORK/stage_04_inference.json" "$EX/stage_04_inference.json"
cp "$WORK/digest.md" "$EX/digest.md"
cp "$OUT/result.json" "$EX/result.json"
cp "$OUT/report.md" "$EX/report.md"
cp "$LOG" "$EX/checks.log"

if [ "$FAILS" -gt 0 ]; then
  note "RESULT: FAIL（$FAILS 项断言失败）"
  exit 1
fi
note "RESULT: PASS（好例全门通过；埋雷 b/c 均按预期拦截）"
exit 0
