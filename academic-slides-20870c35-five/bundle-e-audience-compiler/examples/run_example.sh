#!/usr/bin/env bash
# run_example.sh — audience-spec-compiler 合成示例一键演示（全部输入为 SYNTHETIC EXAMPLE）。
# 从 bundle 根目录运行：bash examples/run_example.sh
#
# 分步预期（per-gate expectations）：
#   STEP 1  SKILL.md frontmatter 恰含 name+description 且 name=audience-spec-compiler → exit 0
#   STEP 2  workorder_compile 合成工作订单（评审委员会/12 分钟/10 页/mixed/en）→ exit 0，
#           且 talk_spec.json 含全部 derived 杠杆键
#   STEP 3  storyboard_good.json（10 主+2 备、conclusion 0 基 idx=4、背景 20%、
#           估计 ~11.6 min、result/comparison 页均有 exhibit）→ exit 0，无任何 S 码
#   STEP 4  storyboard_bad.json 埋雷 → exit 1，且精确打印且仅打印：
#           S1（12 主页超出 [10,10]）、S3（估计 ~15.2 min 超出 [612,828]s）、
#           S4（review 场合 conclusion 0 基 idx=11 > ceil(12/3)=4）、
#           S5（背景比例 6/12=50% 超出 [0.15,0.30]）、S6（S10 result 页无 exhibit）；
#           断言 S2 不出现（埋雷集之外不得有意外违例）
#   STEP 5  schema 错误（坏 JSON）→ exit 2
# 全部满足则末尾打印 ALL EXPECTATIONS MET；日志保留在 examples/output_demo/。

set +e
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output_demo"
mkdir -p "$OUT"

PASS_COUNT=0
FAIL_COUNT=0

step() {
  # $1 = 期望退出码, $2 = 步骤名, 余下为命令
  local expected="$1"; local name="$2"; shift 2
  echo "================================================================"
  echo "STEP: $name"
  echo "CMD : $*"
  "$@"
  local actual=$?
  echo "EXIT: $actual (expected $expected)"
  if [ "$actual" -eq "$expected" ]; then
    echo "RESULT: OK"; PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "RESULT: MISMATCH"; FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo
}

expect_grep() {
  # $1 = 日志文件, $2 = 模式, $3 = 说明
  if grep -q "$2" "$1"; then
    echo "ASSERT OK: $3"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "ASSERT FAIL: $3 (pattern '$2' not found in $1)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

expect_no_grep() {
  if grep -q "$2" "$1"; then
    echo "ASSERT FAIL: $3 (pattern '$2' unexpectedly found in $1)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  else
    echo "ASSERT OK: $3"
    PASS_COUNT=$((PASS_COUNT + 1))
  fi
}

# ---- STEP 1: SKILL.md frontmatter（PyYAML 可用则用，否则 stdlib 兜底） ------
step 0 "SKILL.md frontmatter 恰含 name+description" \
  python3 - "$BUNDLE/SKILL.md" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
assert m, "frontmatter missing"
body = m.group(1)
try:
    import yaml
    data = yaml.safe_load(body)
    keys = set(data.keys())
    name = data.get("name")
except ImportError:
    keys = {ln.split(":", 1)[0].strip() for ln in body.splitlines()
            if ln and not ln.startswith((" ", "\t"))}
    name = dict(ln.split(":", 1) for ln in body.splitlines()
                if ln and not ln.startswith((" ", "\t")))["name"].strip()
assert keys == {"name", "description"}, "frontmatter keys must be exactly name+description, got %s" % keys
assert name == "audience-spec-compiler", "unexpected name: %r" % name
print("frontmatter OK: name=%s, keys=%s" % (name, sorted(keys)))
PY

# ---- STEP 2: 编译工作订单 ----------------------------------------------------
step 0 "workorder_compile：合成订单编译为 talk_spec.json" \
  python3 "$BUNDLE/scripts/workorder_compile.py" \
    --case "$HERE/case.json" --task "$HERE/task.md" \
    --output "$OUT/talk_spec.json" | tee "$OUT/compile.log"

for key in background_ratio_min background_ratio_max conclusion_position \
           per_slide_seconds total_time_band_seconds wpm cjk_cpm; do
  expect_grep "$OUT/talk_spec.json" "\"$key\"" "talk_spec 含 derived 杠杆键 $key"
done
expect_grep "$OUT/talk_spec.json" '"background_ratio_min": 0.15' "mixed 听众带下限 0.15"
expect_grep "$OUT/talk_spec.json" '"background_ratio_max": 0.3'  "mixed 听众带上限 0.30"
expect_grep "$OUT/talk_spec.json" '"rule": "conclusion_first"'   "review 场合结论先行规则"
expect_grep "$OUT/talk_spec.json" '"per_slide_seconds": 72.0'    "每页时间预算 72s = 720s/10"

# ---- STEP 3: good storyboard 应全过 ------------------------------------------
step 0 "storyboard_gate：good storyboard（10 主+2 备）应通过" \
  bash -c "set -o pipefail; python3 '$BUNDLE/scripts/storyboard_gate.py' \
    --storyboard '$HERE/storyboard_good.json' --spec '$OUT/talk_spec.json' \
    | tee '$OUT/gate_good.log'"
expect_no_grep "$OUT/gate_good.log" "GATE FAILED" "good storyboard 无任何违例码"

# ---- STEP 4: bad storyboard 应精确开火 S1/S3/S4/S5/S6 -------------------------
step 1 "storyboard_gate：bad storyboard 埋雷应变例" \
  bash -c "set -o pipefail; python3 '$BUNDLE/scripts/storyboard_gate.py' \
    --storyboard '$HERE/storyboard_bad.json' --spec '$OUT/talk_spec.json' \
    | tee '$OUT/gate_bad.log'"
for code in S1 S3 S4 S5 S6; do
  expect_grep "$OUT/gate_bad.log" "^$code: " "bad storyboard 精确报码 $code"
done
expect_no_grep "$OUT/gate_bad.log" "^S2: " "bad storyboard 不得意外触发 S2（埋雷集之外）"
expect_grep "$OUT/gate_bad.log" "GATE FAILED: S1 S3 S4 S5 S6" "bad storyboard 违例集合恰为 S1 S3 S4 S5 S6"

# ---- STEP 5: schema 错误应 exit 2 ---------------------------------------------
echo '{"slides": "not-a-list"}' > "$OUT/broken_storyboard.json"
step 2 "storyboard_gate：schema 错误应 exit 2" \
  python3 "$BUNDLE/scripts/storyboard_gate.py" \
    --storyboard "$OUT/broken_storyboard.json" --spec "$OUT/talk_spec.json"

echo "================================================================"
echo "SUMMARY: OK=$PASS_COUNT FAIL=$FAIL_COUNT"
echo "ARTIFACTS kept in: $OUT"
ls -1 "$OUT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
echo "ALL EXPECTATIONS MET"
exit 0
