#!/usr/bin/env bash
# 一键运行合成示例：command_mine -> step_table -> repro_check
# 注意：draft.md 故意含有缺陷（写错 --lr、省略 --seed、压缩步骤、缺种子说明），
# 因此 repro_check 预期输出 FAIL，这是正确行为，不是脚本错误。
set -u

BUNDLE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BUNDLE_ROOT"

CASE_DIR="examples/case"
OUT_DIR="examples/expected"
mkdir -p "$OUT_DIR"

echo "== [1/3] command_mine =="
python3 scripts/command_mine.py --case "$CASE_DIR" --out "$OUT_DIR" || exit 1

echo "== [2/3] step_table =="
python3 scripts/step_table.py --commands "$OUT_DIR/commands.json" --out "$OUT_DIR/steps.md" || exit 1

echo "== [3/3] repro_check（对含缺陷的 draft.md，预期 FAIL）=="
python3 scripts/repro_check.py --chapter "$CASE_DIR/draft.md" \
    --commands "$OUT_DIR/commands.json" --steps "$OUT_DIR/steps.md" --out "$OUT_DIR"
RC=$?

echo "== 完成：产物见 $OUT_DIR/ =="
if [ "$RC" -eq 1 ]; then
    echo "repro_check 返回 FAIL（预期行为：draft.md 中故意写错了 flag 且缺少种子）。"
else
    echo "repro_check 返回码 $RC（对缺陷草稿预期为 1，请检查脚本逻辑）。"
fi
exit 0
