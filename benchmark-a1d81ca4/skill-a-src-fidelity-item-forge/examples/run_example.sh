#!/usr/bin/env bash
# 合成示例：真实执行“索引→门禁→裁决→导出”，再演示 fail→修正→pass。
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
SCRIPTS="../scripts"
OUT="${1:-$SCRIPT_DIR/out}"
mkdir -p "$OUT"

echo "[0] 先锁定合法部分结果"
python3 "$SCRIPTS/export_result.py" --case "$SCRIPT_DIR/case.json" --work-dir "$OUT" --output-dir "$OUT" --init || exit 1

echo "[1] 建立源索引"
python3 "$SCRIPTS/source_index.py" --input-dir "$SCRIPT_DIR" --include source_excerpt.txt --output "$OUT/source_index.json" || exit 1

echo "[2A] 使用含错误锚点的工作计划起草并门禁"
python3 "$SCRIPTS/item_forge.py" --task "$SCRIPT_DIR/task.md" --work-plan "$SCRIPT_DIR/work_plan.json" --verdicts /nonexistent/verdicts.json --output "$OUT/items_validated.json" --expected-count 2 || exit 1

echo "[3A] 执行引文机器核验（预期 q2 fail）"
python3 "$SCRIPTS/quote_gate.py" --work-file "$OUT/items_validated.json" --index "$OUT/source_index.json" --output "$OUT/verdicts.json" || exit 1
python3 "$SCRIPTS/item_forge.py" --task "$SCRIPT_DIR/task.md" --work-plan "$SCRIPT_DIR/work_plan.json" --verdicts "$OUT/verdicts.json" --output "$OUT/items_validated.json" --expected-count 2 || exit 1
python3 "$SCRIPTS/export_result.py" --case "$SCRIPT_DIR/case.json" --work-dir "$OUT" --output-dir "$OUT" || exit 1
cp "$OUT/result.json" "$OUT/result_before_fix.json"
cp "$OUT/verdicts.json" "$OUT/verdicts_before_fix.json"
cp "$OUT/failure_analysis.md" "$OUT/failure_analysis_before_fix.md"

echo "[2B] 使用修正后的工作计划重跑门禁"
python3 "$SCRIPTS/item_forge.py" --task "$SCRIPT_DIR/task.md" --work-plan "$SCRIPT_DIR/work_plan_fixed.json" --verdicts "$OUT/verdicts.json" --output "$OUT/items_validated.json" --expected-count 2 || exit 1
python3 "$SCRIPTS/quote_gate.py" --work-file "$OUT/items_validated.json" --index "$OUT/source_index.json" --output "$OUT/verdicts.json" || exit 1
python3 "$SCRIPTS/item_forge.py" --task "$SCRIPT_DIR/task.md" --work-plan "$SCRIPT_DIR/work_plan_fixed.json" --verdicts "$OUT/verdicts.json" --output "$OUT/items_validated.json" --expected-count 2 || exit 1

echo "[5] 导出最终结果"
python3 "$SCRIPTS/export_result.py" --case "$SCRIPT_DIR/case.json" --work-dir "$OUT" --output-dir "$OUT" || exit 1

echo "完成：$OUT"
echo "fail 演示：$OUT/verdicts_before_fix.json"
echo "最终裁决：$OUT/verdicts.json"
