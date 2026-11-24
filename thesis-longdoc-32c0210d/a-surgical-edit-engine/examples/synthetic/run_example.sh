#!/bin/bash
# run_example.sh — 合成示例一键端到端：compile -> apply -> verify -> make_result -> 对比 expected
# 在 macOS /bin/bash + 系统 python3（仅标准库）下运行。本示例全部为合成数据。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$HERE/../.." && pwd)"
IN="$HERE/input"
WORK="$HERE/work"
OUT="$HERE/output"
NOTE="SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== 1/4 compile_workorder =="
python3 "$SKILL_ROOT/scripts/compile_workorder.py" \
  --workorder "$IN/organizer-edit-workorder.json" \
  --case "$IN/case.json" \
  --chapters "$IN/chapters" \
  --out "$WORK/ops.json" \
  --note "$NOTE"

echo "== 2/4 apply_ops =="
python3 "$SKILL_ROOT/scripts/apply_ops.py" \
  --ops "$WORK/ops.json" \
  --src "$IN/chapters" \
  --work "$WORK/chapters" \
  --change-log "$WORK/change_log.json"

echo "== 3/4 verify_acceptance =="
python3 "$SKILL_ROOT/scripts/verify_acceptance.py" \
  --workorder "$IN/organizer-edit-workorder.json" \
  --ops "$WORK/ops.json" \
  --chapters "$WORK/chapters" \
  --out "$WORK/acceptance_report.json" \
  --note "$NOTE"

echo "== 4/4 make_result =="
python3 "$SKILL_ROOT/scripts/make_result.py" \
  --case "$IN/case.json" \
  --work "$WORK" \
  --chapters "$WORK/chapters" \
  --out "$OUT" \
  --note "$NOTE"

echo "== 对比 expected/ =="
ok=1
for f in ops.json change_log.json acceptance_report.json; do
  if diff -u "$HERE/expected/$f" "$WORK/$f" >/dev/null; then
    echo "  MATCH  $f"
  else
    echo "  DIFF   $f （与 expected 不一致）"; ok=0
  fi
done
if diff -u "$HERE/expected/result.json" "$OUT/result.json" >/dev/null; then
  echo "  MATCH  result.json"
else
  echo "  DIFF   result.json （与 expected 不一致）"; ok=0
fi

if [ "$ok" -eq 1 ]; then
  echo "EXAMPLE PASS: 全部产物与 expected/ 一致"
else
  echo "EXAMPLE FAIL: 存在不一致产物" >&2
  exit 1
fi
