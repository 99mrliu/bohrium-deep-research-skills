#!/usr/bin/env bash
# run_example.sh — 端到端最小合成示例（模拟 /input -> /app/work -> /app/output）
# 依次演示：契约优先 -> 渲染+自校验 -> 契约 lint -> 字节确定性 -> 复跑证明
set -euo pipefail
cd "$(dirname "$0")/.."

EX=examples
WORK="$EX/work"      # 模拟 /app/work
OUT="$EX/output"     # 模拟 /app/output
SNAP="$EX/.snapshot"

rm -rf "$WORK" "$OUT" "$SNAP"
mkdir -p "$WORK" "$OUT" "$SNAP"

echo "== [1/6] init_contract：契约优先，骨架先落盘 =="
python3 scripts/init_contract.py --case "$EX/case.json" --workdir "$WORK" --outdir "$OUT"

echo "== [2/6] 写入记录（真实任务中由 agent 从语料抽取；此处用合成示例记录）=="
cp "$EX/sample_records/cells.jsonl" "$EX/sample_records/decisions.jsonl" "$WORK"/

echo "== [3/6] render_all：渲染 + markdown 数字回解析自校验 =="
python3 scripts/render_all.py --workdir "$WORK" --outdir "$OUT"

echo "== [4/6] contract_lint：契约强校验 =="
python3 scripts/contract_lint.py --case "$EX/case.json" --workdir "$WORK" --outdir "$OUT"

echo "== [5/6] 字节确定性：快照 -> --force 强制重渲染 -> diff 应为空 =="
cp "$OUT/comparison-matrix.md" "$OUT/integration-report.md" "$OUT/result.json" "$SNAP"/
python3 scripts/render_all.py --force --workdir "$WORK" --outdir "$OUT"
for f in comparison-matrix.md integration-report.md result.json; do
  if diff -q "$SNAP/$f" "$OUT/$f" >/dev/null; then
    echo "  DETERMINISTIC: $f（两次渲染字节一致）"
  else
    echo "  NON-DETERMINISTIC: $f（两次渲染不一致！）"
    exit 1
  fi
done

echo "== [6/6] replay：重跑渲染并与已交付产物逐字节比对 =="
python3 scripts/replay.py --workdir "$WORK" --outdir "$OUT"

rm -rf "$SNAP"
echo "== 全部通过：产物见 $OUT/（comparison-matrix.md / integration-report.md / result.json / replay-report.json）=="
