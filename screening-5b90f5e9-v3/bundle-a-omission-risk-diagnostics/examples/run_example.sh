#!/usr/bin/env bash
# run_example.sh — 用合成示例（非真实评测案例）端到端跑通 omission-risk-diagnostics。
# 以 examples/run/{input,work,output} 模拟评测时的 /input、/app/work、/app/output。
# 不用 set -e：逐步捕获并打印每个脚本的真实 exit code。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/../scripts"
IN="$HERE/run/input"
WORK="$HERE/run/work"
OUT="$HERE/run/output"

mkdir -p "$IN" "$WORK" "$OUT"
cp "$HERE/input/case.json" "$HERE/input/records.json" "$HERE/input/judgments.json" "$IN/"

run_step () {
  local name="$1"; shift
  echo "=== $name ==="
  python3 "$SCRIPTS/$name" --input-dir "$IN" --work "$WORK" --output-dir "$OUT"
  local code=$?
  echo "exit_code=$code"
  return 0
}

run_step scaffold_result.py
run_step mine_near_misses.py
run_step fragility_report.py
run_step facet_coverage.py
run_step omission_statement.py
run_step selfcheck.py

echo "--- 产物清单 ---"
ls -1 "$WORK" "$OUT"
