#!/bin/bash
# run_example.sh — 端到端运行合成示例 (全程本地, 无网络)
# 管线: 语料 jsonl -> 段落索引 -> 候选抽取 -> 机检 agent 确认的测量记录 -> 渲染台账/矩阵/result 骨架
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
EX="$ROOT/examples"
OUT="$EX/output"
mkdir -p "$OUT"

echo "== [0] 合并语料为段落索引 =="
cat "$EX"/corpus/*.jsonl > "$OUT/paras-index.jsonl"
wc -l "$OUT/paras-index.jsonl"

echo "== [1] 候选抽取 (机器提出, 不判读) =="
python3 "$ROOT/scripts/extract_candidates.py" --paras "$OUT/paras-index.jsonl" -o "$OUT/candidates.jsonl"

echo "== [2] 机检 agent 已确认的测量记录 (口径随值走: reported 必带 metric_definition) =="
python3 "$ROOT/scripts/validate_measurements.py" "$EX/sample_measurements.jsonl" \
    --paras "$OUT/paras-index.jsonl"

echo "== [3] 渲染台账 + 比较矩阵 + result 骨架 =="
python3 "$ROOT/scripts/render_ledger.py" "$EX/sample_measurements.jsonl" \
    --case "$EX/comparison-workorder.json" \
    --workorder "$EX/comparison-workorder.json" \
    --outdir "$OUT"

echo "== 产物 =="
ls -la "$OUT"
echo "OK"
