#!/bin/bash
# run_example.sh — 合成示例端到端自校验（interpretation-tribunal）
#
# 数据由 make_synthetic.py 现场合成（大样本小差异，"显著但不重要"场景），
# 非真实实验数据。流程：
#   (a) pipeline run 好例 -> 断言 result.json 9 字段 + claims 非空 +
#       report.md 结果解释章节结论句全部带 [ev:]；
#   (b) wording_lint + claim_bind 好例 exit 0；
#   (c) 埋雷：BANNED_PHRASE / P_WORDING / CI_MISREAD / DANGLING_EVIDENCE /
#       NUMBER_MISMATCH / UNHEDGED_PARTIAL 各自必须命中（exit 1）；
# 全部断言通过本脚本才 exit 0，否则 exit 1。
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL_DIR=$(cd "$HERE/.." && pwd)
PY=${PYTHON:-python3}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/input" "$TMP/work" "$TMP/output" "$TMP/bad"

FAILS=0
note() { echo "[run_example] $*"; }
check() { # check <描述> <实际值> <期望值>
  if [ "$2" = "$3" ]; then
    note "PASS: $1"
  else
    note "FAIL: $1（实际=$2 期望=$3）"
    FAILS=$((FAILS + 1))
  fi
}
grep_check() { # grep_check <描述> <模式> <文件>
  if grep -q "$2" "$3"; then
    note "PASS: $1"
  else
    note "FAIL: $1（未找到模式 $2）"
    FAILS=$((FAILS + 1))
  fi
}

# ---------------------------------------------------------------- (a) 好例
note "== 步骤 1：生成合成示例数据 =="
$PY "$HERE/make_synthetic.py" --out "$TMP/input" || exit 1

note "== 步骤 2：pipeline run（好例）=="
$PY "$SKILL_DIR/scripts/pipeline_d.py" run \
  --input "$TMP/input" --work "$TMP/work" --output "$TMP/output" \
  >"$TMP/pipeline.log" 2>&1
check "pipeline run exit 0" "$?" "0"

note "== 步骤 3：断言 result.json 9 字段 + claims 非空 =="
$PY - "$TMP/output/result.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
req = ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
       "effect_size", "confidence_interval", "interpretation", "limitations"]
missing = [k for k in req if k not in r]
assert not missing, "缺字段: %s" % missing
assert r["claims"], "claims 为空"
assert all(k in r["claims"][0] for k in
           ["id", "outcome", "comparison", "direction", "significant",
            "p", "alpha", "effect_size", "practical_note", "sentence"]), \
    "claim 字段不全"
print("[run_example] PASS: result.json 9 字段齐全，claims=%d" % len(r["claims"]))
EOF
check "result.json 结构断言" "$?" "0"

note "== 步骤 4：断言结果解释章节结论句全部带 [ev:] =="
$PY - "$TMP/output/report.md" <<'EOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
sec = re.search(r"^#{1,6}\s*.*结果解释.*?\n(.*?)(?=^#{1,6}\s)",
                text, re.S | re.M)
assert sec, "未找到结果解释章节"
bad = []
for line in sec.group(1).splitlines():
    if line.strip().startswith("|"):
        continue
    for s in re.split(r"(?<=[。！？])(?!\[ev:)", line):
        if re.search(r"统计学意义|效应量|置信区间为", s) and \
           not re.search(r"\[ev:[A-Za-z0-9_\-]+\]", s):
            bad.append(s[:50])
assert not bad, "存在无 [ev:] 标签的结论句: %s" % bad
print("[run_example] PASS: 结论句全部带 [ev:] 标签")
EOF
check "结论句 [ev:] 断言" "$?" "0"

# ---------------------------------------------------------------- (b) 两项 lint 好例
note "== 步骤 5：wording_lint / claim_bind 好例 exit 0 =="
$PY "$SKILL_DIR/scripts/wording_lint.py" --file "$TMP/output/report.md" \
  --result "$TMP/output/result.json" >"$TMP/lint_good.log" 2>&1
check "wording_lint 好例 exit 0" "$?" "0"
$PY "$SKILL_DIR/scripts/claim_bind.py" --report "$TMP/output/report.md" \
  --result "$TMP/output/result.json" >"$TMP/bind_good.log" 2>&1
check "claim_bind 好例 exit 0" "$?" "0"

# ---------------------------------------------------------------- (c) 埋雷
note "== 步骤 6：埋雷 1 —— 「证明该处理有效」=="
$PY - "$TMP/output/report.md" "$TMP/bad/report_banned.md" <<'EOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
bad = ("在 α=0.05 水平下，处理组的 score 差异被证明有效（p=0.0001），"
       "统计上显著因此该处理值得推广。")
new, n = re.subn(r"在 α=0\.05 水平下，[^。]*具有统计学意义（[^）]*）",
                 bad, text, count=1)
assert n == 1, "未找到可替换的结论句"
open(sys.argv[2], "w", encoding="utf-8").write(new)
EOF
$PY "$SKILL_DIR/scripts/wording_lint.py" --file "$TMP/bad/report_banned.md" \
  --result "$TMP/output/result.json" >"$TMP/lint_m1.log" 2>&1
check "埋雷1 wording_lint exit 1" "$?" "1"
grep_check "埋雷1 命中 BANNED_PHRASE" "BANNED_PHRASE" "$TMP/lint_m1.log"
grep_check "埋雷1 命中 P_WORDING" "P_WORDING" "$TMP/lint_m1.log"

note "== 步骤 7：埋雷 2 —— CI 误读 =="
cp "$TMP/output/report.md" "$TMP/bad/report_ci.md"
echo "95% 的个体测量值落在该区间内。" >>"$TMP/bad/report_ci.md"
$PY "$SKILL_DIR/scripts/wording_lint.py" --file "$TMP/bad/report_ci.md" \
  --result "$TMP/output/result.json" >"$TMP/lint_m2.log" 2>&1
check "埋雷2 wording_lint exit 1" "$?" "1"
grep_check "埋雷2 命中 CI_MISREAD" "CI_MISREAD" "$TMP/lint_m2.log"

note "== 步骤 8：埋雷 3 —— 悬空证据标签 =="
$PY - "$TMP/output/report.md" "$TMP/bad/report_dangle.md" <<'EOF'
import sys
text = open(sys.argv[1], encoding="utf-8").read()
assert "[ev:H1]" in text
open(sys.argv[2], "w", encoding="utf-8").write(
    text.replace("[ev:H1]", "[ev:H99]", 1))
EOF
$PY "$SKILL_DIR/scripts/claim_bind.py" --report "$TMP/bad/report_dangle.md" \
  --result "$TMP/output/result.json" >"$TMP/bind_m3.log" 2>&1
check "埋雷3 claim_bind exit 1" "$?" "1"
grep_check "埋雷3 命中 DANGLING_EVIDENCE" "DANGLING_EVIDENCE" "$TMP/bind_m3.log"

note "== 步骤 9：埋雷 4 —— 句中 p 值与存储不一致 =="
$PY - "$TMP/output/report.md" "$TMP/bad/report_number.md" <<'EOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
# 只在「结果解释」章节的结论句里篡改 p 值（统计量表格不属于结论句）
m = re.search(r"^#{1,6}\s*.*结果解释", text, re.M)
assert m, "未找到结果解释章节"
head, tail = text[:m.start()], text[m.start():]
if "p<0.0001" in tail:
    tail = tail.replace("p<0.0001", "p=0.0312", 1)
else:
    tail, n = re.subn(r"p=0\.\d{4}", "p=0.0312", tail, count=1)
    assert n == 1, "结论句中未找到 p 值"
open(sys.argv[2], "w", encoding="utf-8").write(head + tail)
EOF
$PY "$SKILL_DIR/scripts/claim_bind.py" --report "$TMP/bad/report_number.md" \
  --result "$TMP/output/result.json" >"$TMP/bind_m4.log" 2>&1
check "埋雷4 claim_bind exit 1" "$?" "1"
grep_check "埋雷4 命中 NUMBER_MISMATCH" "NUMBER_MISMATCH" "$TMP/bind_m4.log"

note "== 步骤 10：埋雷 5 —— partial 状态缺少不确定性说明 =="
$PY - "$TMP/output/result.json" "$TMP/output/report.md" \
    "$TMP/bad/result_partial.json" "$TMP/bad/report_partial.md" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
r["status"] = "partial"
json.dump(r, open(sys.argv[3], "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
lines = open(sys.argv[2], encoding="utf-8").read().splitlines()
kept = [l for l in lines if "不确定" not in l]
open(sys.argv[4], "w", encoding="utf-8").write("\n".join(kept))
EOF
$PY "$SKILL_DIR/scripts/wording_lint.py" --file "$TMP/bad/report_partial.md" \
  --result "$TMP/bad/result_partial.json" >"$TMP/lint_m5.log" 2>&1
check "埋雷5 wording_lint exit 1" "$?" "1"
grep_check "埋雷5 命中 UNHEDGED_PARTIAL" "UNHEDGED_PARTIAL" "$TMP/lint_m5.log"

# ---------------------------------------------------------------- 归档好例产物
note "== 步骤 11：归档 example_output/（仅文本产物）=="
mkdir -p "$HERE/example_output"
cp "$TMP/input/case.json" "$TMP/input/task.md" "$TMP/input/synthetic.csv" \
   "$TMP/output/result.json" "$TMP/output/report.md" "$TMP/output/digest.md" \
   "$HERE/example_output/"
note "已写入 $HERE/example_output/"

echo "------------------------------------------------------------"
if [ "$FAILS" -eq 0 ]; then
  note "全部断言通过（好例 exit 0 + 5 组埋雷全部命中预期违例码）"
  exit 0
else
  note "共 $FAILS 项断言失败"
  exit 1
fi
