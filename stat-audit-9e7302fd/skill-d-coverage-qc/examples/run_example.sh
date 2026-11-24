#!/usr/bin/env bash
# 【合成示例】run_example.sh — 一键演示两道质量门:
#   门1 ledger_check.py:有效台账应 PASS,篡改台账应 FAIL;
#   门2 journal_check.py:有效日志应 PASS,哈希被改的日志应 FAIL。
# 运行: bash examples/run_example.sh   (可在任意目录调用)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
OUT="$HERE/expected_output"
PY="${PYTHON:-python3}"
fails=0

expect() {  # expect <期望码> <实际码> <名称>
  if [ "$1" -eq "$2" ]; then
    echo "OK   $3 (退出码 $2,符合期望)"
  else
    echo "BAD  $3 (期望 $1,实际 $2)"
    fails=$((fails + 1))
  fi
}

echo "== [1/4] 有效台账:应通过 =="
"$PY" "$SKILL_DIR/scripts/ledger_check.py" "$HERE/ledger_valid.json" \
  > "$OUT/ledger_check_valid_stdout.txt" 2>&1
expect 0 $? "ledger_check ledger_valid.json"

echo "== [2/4] 篡改台账(五数对账错+幽灵finding):应失败 =="
"$PY" "$SKILL_DIR/scripts/ledger_check.py" "$HERE/ledger_tampered.json" \
  > /dev/null 2> "$OUT/ledger_check_tampered_stderr.txt"
expect 1 $? "ledger_check ledger_tampered.json"

echo "== [3/4] 有效运行日志(哈希与台账引用齐全):应通过 =="
"$PY" "$SKILL_DIR/scripts/journal_check.py" "$HERE/run_journal.jsonl" \
  --output-dir "$OUT" --input-dir "$HERE" --ledger "$HERE/ledger_valid.json" \
  > "$OUT/journal_check_valid_stdout.txt" 2>&1
expect 0 $? "journal_check run_journal.jsonl"

echo "== [4/4] 哈希被改的运行日志:应失败 =="
"$PY" "$SKILL_DIR/scripts/journal_check.py" "$HERE/run_journal_broken.jsonl" \
  --output-dir "$OUT" --input-dir "$HERE" --ledger "$HERE/ledger_valid.json" \
  > /dev/null 2> "$OUT/journal_check_broken_stderr.txt"
expect 1 $? "journal_check run_journal_broken.jsonl"

echo "--------------------------------------------------------"
if [ "$fails" -eq 0 ]; then
  echo "全部 4 项符合期望:两道质量门均为真(PASS 真通过、FAIL 真拦截)。"
  exit 0
else
  echo "$fails 项不符合期望,请检查 scripts/ 与 examples/。"
  exit 1
fi
