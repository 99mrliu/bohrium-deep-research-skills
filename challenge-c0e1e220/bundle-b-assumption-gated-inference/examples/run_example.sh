#!/usr/bin/env bash
# run_example.sh — 端到端自校验示例（合成数据，脚本内自断言，全过才 exit 0）
#  (a) 生成合成数据 → pipeline_b run → 断言 9 字段齐全 + 门控选择正确
#  (b) decision_audit 好例 → 必须 exit 0
#  (c) 埋雷 3 例：chosen_test 篡改 → TEST_MISMATCH；p 篡改 → P_MISMATCH；
#      正态性结论翻转 → ASSUMPTION_MISMATCH；均必须 exit 1 且命中对应违例码
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
SCRIPTS="$BUNDLE/scripts"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
IN="$TMP/input"; WORK="$TMP/work"; OUT="$TMP/output"
mkdir -p "$IN" "$WORK" "$OUT"

fail() { echo "EXAMPLE FAIL: $1"; exit 1; }

echo "== (0) 生成合成示例输入 =="
python3 "$HERE/make_synthetic.py" --out "$IN" || fail "make_synthetic"

echo "== (a) pipeline_b run =="
python3 "$SCRIPTS/pipeline_b.py" run --input-dir "$IN" --work-dir "$WORK" \
  --output-dir "$OUT" || fail "pipeline run exit!=0"
RESULT="$OUT/result.json"
python3 -m json.tool "$RESULT" > /dev/null || fail "result.json 不是合法 JSON"

python3 - "$RESULT" <<'PY' || fail "字段/门控断言"
import json, sys
r = json.load(open(sys.argv[1]))
req = ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
       "effect_size", "confidence_interval", "interpretation", "limitations"]
missing = [k for k in req if k not in r]
assert not missing, "缺字段: %s" % missing
assert r["status"] == "ok", "status=%s" % r["status"]
assert r["decision_log"], "decision_log 为空"
two = [e for e in r["decision_log"] if e["design"] == "two_group"]
k = [e for e in r["decision_log"] if e["design"] == "k_group"]
assert len(two) == 1 and len(k) == 1, "分析数异常: %d two, %d k" % (len(two), len(k))
e2 = two[0]
assert e2["chosen_test"] == "mannwhitney_u", \
    "右偏两组应选 mannwhitney_u，实际 %s" % e2["chosen_test"]
assert any(c.startswith("NORMALITY_FAIL") for c in e2["reason_codes"]), \
    "reason_codes 缺 NORMALITY_FAIL: %s" % e2["reason_codes"]
e3 = k[0]
assert e3["chosen_test"] in ("anova", "welch_anova"), \
    "三组近似正态应选 anova/welch_anova，实际 %s" % e3["chosen_test"]
print("断言通过: 9 字段齐全; 右偏两组 -> mannwhitney_u (NORMALITY_FAIL); "
      "三组 -> %s" % e3["chosen_test"])
PY

echo "== (b) decision_audit 好例（期望 exit 0） =="
python3 "$SCRIPTS/decision_audit.py" --input-dir "$IN" --result "$RESULT" \
  | tee "$TMP/audit_pass.txt" || fail "好例审计未通过"

echo "== (c1) 埋雷：chosen_test 改成 student_t（期望 TEST_MISMATCH, exit 1） =="
python3 - "$RESULT" "$TMP/bad_test.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
for e in r["decision_log"]:
    if e["design"] == "two_group":
        e["chosen_test"] = "student_t"
json.dump(r, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY
OUT1=$(python3 "$SCRIPTS/decision_audit.py" --input-dir "$IN" --result "$TMP/bad_test.json")
RC=$?
echo "$OUT1" | head -3
[ $RC -eq 1 ] || fail "埋雷 c1 未返回 exit 1 (rc=$RC)"
echo "$OUT1" | grep -q "TEST_MISMATCH" || fail "埋雷 c1 未命中 TEST_MISMATCH"

echo "== (c2) 埋雷：三组分析 p 改大 0.01（期望 P_MISMATCH, exit 1） =="
python3 - "$RESULT" "$TMP/bad_p.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
for e in r["decision_log"]:
    if e["design"] == "k_group":
        e["test_result"]["p"] = min(1.0, e["test_result"]["p"] + 0.01)
json.dump(r, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY
OUT2=$(python3 "$SCRIPTS/decision_audit.py" --input-dir "$IN" --result "$TMP/bad_p.json")
RC=$?
echo "$OUT2" | head -3
[ $RC -eq 1 ] || fail "埋雷 c2 未返回 exit 1 (rc=$RC)"
echo "$OUT2" | grep -q "P_MISMATCH" || fail "埋雷 c2 未命中 P_MISMATCH"

echo "== (c3) 埋雷：正态性结论翻转（期望 ASSUMPTION_MISMATCH, exit 1） =="
python3 - "$RESULT" "$TMP/bad_asm.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
g = r["decision_log"][0]["groups"][0]["normality"]
g["conclusion"] = "non_normal" if g["conclusion"] == "normal" else "normal"
json.dump(r, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY
OUT3=$(python3 "$SCRIPTS/decision_audit.py" --input-dir "$IN" --result "$TMP/bad_asm.json")
RC=$?
echo "$OUT3" | head -3
[ $RC -eq 1 ] || fail "埋雷 c3 未返回 exit 1 (rc=$RC)"
echo "$OUT3" | grep -q "ASSUMPTION_MISMATCH" || fail "埋雷 c3 未命中 ASSUMPTION_MISMATCH"

echo "== (d) 刷新 example_output/（真实文本产物） =="
EXOUT="$HERE/example_output"
if [ -w "$EXOUT" ]; then
  cp "$RESULT" "$EXOUT/result.json"
  cp "$TMP/audit_pass.txt" "$EXOUT/audit_pass.txt"
  python3 - "$RESULT" > "$EXOUT/decision_log_excerpt.md" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print("# decision_log 摘录（合成示例真实产物）\n")
for e in r["decision_log"]:
    tr = e["test_result"]
    print("## %s — %s @ %s（%s）" % (e["analysis_id"],
          e["data"]["outcome_column"]["name"],
          e["data"]["group_column"]["name"], e["design"]))
    print("- 各组 n 与正态性: " + "; ".join(
        "%s n=%d K2_p=%s -> %s" % (g["label"], g["n"],
        ("%.4f" % g["normality"]["p"]) if g["normality"]["p"] is not None else "NA",
        g["normality"]["conclusion"]) for g in e["groups"]))
    print("- Levene(median): W=%.4f, p=%.4f -> %s" % (
        e["levene"]["statistic"], e["levene"]["p"], e["levene"]["conclusion"]))
    print("- reason_codes: `%s`" % "`, `".join(e["reason_codes"]))
    print("- 被否决: " + "; ".join("%s(%s)" % (c["test"], c["reason"])
          for c in e["rejected_candidates"]))
    print("- **chosen_test = %s**: %s=%.4f, df=%s, p=%.4g, alpha=%.2f\n" % (
        e["chosen_test"], tr["statistic_name"], tr["statistic"], tr["df"],
        tr["p"], tr["alpha"]))
PY
  echo "example_output 已刷新: result.json / decision_log_excerpt.md / audit_pass.txt"
else
  echo "example_output 不可写，跳过刷新"
fi

echo "EXAMPLE PASS: 全部断言通过（好例 exit 0；3 个埋雷均 exit 1 且命中违例码）"
exit 0
