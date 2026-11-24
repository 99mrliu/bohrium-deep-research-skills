#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   块库抽取 -> 坏 ops 校验拦截 -> 好 ops 校验通过 -> 模拟应用 -> 决策表
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

python3 "$SKILL/scripts/outline_extract.py" "$HERE/input/ms.md" "$WORK/blocks"
cp "$WORK/blocks/blocks.jsonl" "$WORK/blocks/outline.json" "$OUT/"

python3 "$SKILL/scripts/editop_check.py" "$WORK/blocks/blocks.jsonl" \
  "$HERE/ops_bad.json" "$OUT/editop_check_bad.json"
echo "bad ops check exit: $? (预期 1，演示拦截)"

python3 "$SKILL/scripts/editop_check.py" "$WORK/blocks/blocks.jsonl" \
  "$HERE/ops_valid.json" "$OUT/editop_check.json" || exit 1

python3 "$SKILL/scripts/apply_editops.py" "$WORK/blocks/blocks.jsonl" \
  "$HERE/ops_valid.json" "$OUT"
python3 "$SKILL/scripts/decision_sheet.py" "$HERE/ops_valid.json" \
  "$OUT/change_log.json" "$OUT/decision_sheet.md"
echo "--- revised_skeleton.md ---"
cat "$OUT/revised_skeleton.md"
