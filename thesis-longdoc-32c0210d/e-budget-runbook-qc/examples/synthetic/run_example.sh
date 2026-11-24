#!/bin/bash
# run_example.sh — budget-runbook-qc 合成示例一键端到端演示
# macOS /bin/bash + 系统 python3 (仅标准库)。输出确定性: 相对秒数、无绝对路径。
# 用法:
#   ./run_example.sh           跑通全流程并与 expected/ 逐字节比对
#   ./run_example.sh --freeze  用本次真实运行固化 expected/（构建者专用）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(cd "$HERE/../../scripts" && pwd)"
INPUT="$HERE/input"
WORK="$HERE/work"
OUT="$HERE/output"
EXPECTED="$HERE/expected"
FREEZE=0
[ "${1:-}" = "--freeze" ] && FREEZE=1

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"
NOTE='SYNTHETIC EXAMPLE — 合成示例，非正式案例结果'

echo "== [1/10] budget init (900s / 64 requests) =="
python3 "$SCRIPTS/budget_ledger.py" init --workdir "$WORK" --seconds 900 --requests 64

echo "== [2/10] 读取 case.json + workorder (真实运行中为模型任务), tick 5s =="
python3 "$SCRIPTS/budget_ledger.py" tick --workdir "$WORK" --seconds 5 --note "read case.json and workorder"

echo "== [3/10] checkpoint init -> 立即写 partial result.json =="
python3 "$SCRIPTS/checkpoint.py" init --workdir "$WORK" --outdir "$OUT" --case "$INPUT/case.json"
echo "--- partial result.json (骨架) ---"
cat "$OUT/result.json"

cp -R "$INPUT/chapters" "$WORK/chapters"

echo "== [4/10] 基线验收 (未编辑时 item1 应 FAIL) =="
if python3 "$SCRIPTS/qc_gates.py" run \
    --workorder "$INPUT/organizer-edit-workorder.json" \
    --chapters "$WORK/chapters" --workdir "$WORK"; then
  echo "!! 基线不应全过"; exit 1
else
  echo "(预期内的基线 FAIL, 继续)"
fi

echo "== [5/10] workorder item 1: 术语统一 (机械替换由 sed 完成) =="
python3 "$SCRIPTS/budget_ledger.py" tick --workdir "$WORK" --request --seconds 25 --note "item1 terminology edit"
sed -i '' 's/隔膜/隔板/g' "$WORK"/chapters/*.md
python3 "$SCRIPTS/checkpoint.py" promote --workdir "$WORK" --outdir "$OUT" \
  --field 'change_record=["item1: 全文“隔膜”→“隔板” (sed 机械替换, 全部章节)"]'

echo "== [6/10] workorder item 2: 图表引用核对 (无需编辑, 仅记录) =="
python3 "$SCRIPTS/budget_ledger.py" tick --workdir "$WORK" --request --seconds 20 --note "item2 figure/table ref check"
python3 "$SCRIPTS/checkpoint.py" promote --workdir "$WORK" --outdir "$OUT" \
  --field 'consistency_report={"figure_table_refs":"图1 引用(01,02章)与图题(03章)一致, 无表引用"}'

echo "== [7/10] 终验: qc_gates 应全 PASS =="
python3 "$SCRIPTS/qc_gates.py" run \
  --workorder "$INPUT/organizer-edit-workorder.json" \
  --chapters "$WORK/chapters" --workdir "$WORK"

echo "== [8/10] assemble + 补 uncertainty + finalize =="
python3 "$SCRIPTS/checkpoint.py" assemble --workdir "$WORK" --outdir "$OUT" --chapters "$WORK/chapters"
python3 "$SCRIPTS/checkpoint.py" promote --workdir "$WORK" --outdir "$OUT" \
  --field 'uncertainty="合成示例无实质不确定性; 真实案例须在此写明限制与未验证项"'
python3 "$SCRIPTS/checkpoint.py" promote --workdir "$WORK" --outdir "$OUT" \
  --field 'sources=["input/chapters/01-intro.md","input/chapters/02-method.md","input/chapters/03-results.md"]'
python3 "$SCRIPTS/checkpoint.py" finalize --workdir "$WORK" --outdir "$OUT"
python3 "$SCRIPTS/checkpoint.py" validate --workdir "$WORK" --outdir "$OUT" --case "$INPUT/case.json"

echo "== [9/10] 受控故障注入演练 =="
python3 "$SCRIPTS/fault_inject.py" run --workdir "$WORK" --outdir "$OUT" \
  --case "$INPUT/case.json" --workorder "$INPUT/organizer-edit-workorder.json" \
  --chapters "$WORK/chapters" --note "$NOTE"

echo "== [10/10] 预算结算 =="
python3 "$SCRIPTS/budget_ledger.py" status --workdir "$WORK"

FILES="budget.json checkpoint.log gates_report.json fault_report.json"
if [ "$FREEZE" = "1" ]; then
  mkdir -p "$EXPECTED"
  for f in $FILES; do cp "$WORK/$f" "$EXPECTED/$f"; done
  cp "$OUT/result.json" "$EXPECTED/result.json"
  echo "FROZEN: expected/ 已由本次真实运行固化"
else
  ok=1
  for f in $FILES; do
    if ! diff -u "$EXPECTED/$f" "$WORK/$f"; then echo "DIFF in $f"; ok=0; fi
  done
  if ! diff -u "$EXPECTED/result.json" "$OUT/result.json"; then echo "DIFF in result.json"; ok=0; fi
  if [ "$ok" = "1" ]; then
    echo "EXAMPLE RUN: PASS (产物与 expected/ 逐字节一致)"
  else
    echo "EXAMPLE RUN: FAIL (与 expected/ 不一致)"; exit 1
  fi
fi
