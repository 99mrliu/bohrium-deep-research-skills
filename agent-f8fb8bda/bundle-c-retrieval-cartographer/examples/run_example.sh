#!/usr/bin/env bash
# run_example.sh — dr-retrieval-cartographer 合成示例一键演示。
# 全程 set +e，逐步捕获真实退出码，末尾汇总 EXPECTED vs ACTUAL。
# 所有内容为合成示例（synthetic），不访问网络，仅依赖 Python3 标准库。

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
    echo "RESULT: OK"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "RESULT: MISMATCH"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo
}

step 0 "decompose：六要素抽取 + SQ 骨架" \
  python3 "$BUNDLE/scripts/decompose.py" \
    --task "$HERE/task.md" \
    --case "$HERE/case.json" \
    --output "$OUT/decomposition.json"

step 0 "plan_check：合规计划（6 action / 2 波次）应通过" \
  python3 "$BUNDLE/scripts/plan_check.py" \
    --plan "$HERE/good_plan.json" \
    --decomp "$OUT/decomposition.json"

step 1 "plan_check：埋雷计划（P1 成环 + P3 重复检索式 + P5 超预算）应开火" \
  python3 "$BUNDLE/scripts/plan_check.py" \
    --plan "$HERE/bad_plan.json" \
    --decomp "$HERE/bad_decomp.json" \
    --max-actions 6

step 0 "coverage：导出覆盖矩阵与研究空白" \
  python3 "$BUNDLE/scripts/coverage.py" \
    --log "$HERE/search_log.jsonl" \
    --decomp "$OUT/decomposition.json" \
    --out-dir "$OUT"

step 1 "coverage --gaps-file：对 not_searched 方向声称空白应开火" \
  python3 "$BUNDLE/scripts/coverage.py" \
    --log "$HERE/search_log.jsonl" \
    --decomp "$OUT/decomposition.json" \
    --out-dir "$OUT" \
    --gaps-file "$HERE/bad_gaps.md"

echo "================================================================"
echo "SUMMARY: OK=$PASS_COUNT MISMATCH=$FAIL_COUNT"
echo "ARTIFACTS kept in: $OUT"
ls -1 "$OUT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
