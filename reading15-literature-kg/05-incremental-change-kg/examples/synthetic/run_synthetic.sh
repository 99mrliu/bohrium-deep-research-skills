#!/bin/bash
# run_synthetic.sh — 一键运行 SYNTHETIC 合成示例（仅演示接口，非正式案例结果）。
# 用法: bash examples/synthetic/run_synthetic.sh
set -euo pipefail
HERE_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE_DIR/../../scripts"
IN="$HERE_DIR/input"
CAND="$HERE_DIR/candidates"
WORK="$(mktemp -d /tmp/kg-synth-work.XXXXXX)"
OUT="$HERE_DIR/output"
rm -rf "$OUT"; mkdir -p "$OUT"
trap 'rm -rf "$WORK"' EXIT

echo "== [1/6] 校验 baseline 候选 =="
python3 "$SCRIPTS/kg_verify.py" --input-dir "$IN" --candidates "$CAND/baseline-candidates.json"

echo "== [2/6] 构建并封存 baseline v1 =="
python3 "$SCRIPTS/kg_apply.py" init --input-dir "$IN" \
    --candidates "$CAND/baseline-candidates.json" --work-dir "$WORK"

echo "== [3/6] 校验变更集（对照封存基线） =="
python3 "$SCRIPTS/kg_verify.py" --input-dir "$IN" \
    --changeset "$CAND/changeset.json" --graph "$WORK/graph-v1.json"

echo "== [4/6] 应用变更集 v1 -> v2 =="
python3 "$SCRIPTS/kg_apply.py" apply --input-dir "$IN" \
    --work-dir "$WORK" --changeset "$CAND/changeset.json"

echo "== [5/6] 版本差异 + 真实执行查询 =="
python3 "$SCRIPTS/kg_diff.py" --baseline "$WORK/graph-v1.json" \
    --current "$WORK/graph-v2.json" --out "$WORK/diff.json"
python3 "$SCRIPTS/kg_query.py" --baseline "$WORK/graph-v1.json" \
    --current "$WORK/graph-v2.json" \
    --spec "$HERE_DIR/queries/query-specs.json" --out "$WORK/queries.json"

echo "== [6/6] 装配输出 =="
python3 "$SCRIPTS/kg_assemble.py" --input-dir "$IN" --work-dir "$WORK" --output-dir "$OUT"
echo "SYNTHETIC 输出已写入 $OUT"
