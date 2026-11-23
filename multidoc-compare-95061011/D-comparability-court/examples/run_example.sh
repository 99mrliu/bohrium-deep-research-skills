#!/usr/bin/env bash
# run_example.sh — comparability-court 最小合成示例端到端演示
# 流程：build_profiles → decide → pool（permit 例 + block 例各一次）→ render_court（含 lint）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/output"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "===== 1/4 build_profiles：校验条件档案（quote 逐字落地机检）====="
python3 "$ROOT/scripts/build_profiles.py" \
    --corpus "$HERE/corpus" \
    --profiles "$HERE/sample_profiles.jsonl" \
    --out "$OUT/profiles.json"

echo
echo "===== 2/4 decide：逐对 × 逐维度裁定 + 任务级总裁定 ====="
python3 "$ROOT/scripts/decide.py" \
    --profiles "$OUT/profiles.json" \
    --rules "$ROOT/references/comparability-rules.json" \
    --out "$OUT/decisions.jsonl"

echo
echo "===== 3/4 pool：合成守门（两个请求，演示 permit 与 block）====="
echo "--- 3a 定性对照请求（预期 PERMIT）---"
python3 "$ROOT/scripts/pool.py" \
    --decisions "$OUT/decisions.jsonl" \
    --request "$HERE/sample_synthesis_request_permit.json" \
    --rules "$ROOT/references/comparability-rules.json" \
    --out "$OUT/pool_permit.json"
echo
echo "--- 3b 跨污染物求均值请求（预期 BLOCK）---"
python3 "$ROOT/scripts/pool.py" \
    --decisions "$OUT/decisions.jsonl" \
    --request "$HERE/sample_synthesis_request_block.json" \
    --rules "$ROOT/references/comparability-rules.json" \
    --out "$OUT/pool_block.json"

echo
echo "===== 4/4 render_court：渲染矩阵/报告模板/result.json 并 lint ====="
python3 "$ROOT/scripts/render_court.py" \
    --decisions "$OUT/decisions.jsonl" \
    --profiles "$OUT/profiles.json" \
    --workorder "$HERE/comparison-workorder.json" \
    --case "$HERE/case.json" \
    --permits "$OUT/pool_permit.json" "$OUT/pool_block.json" \
    --outdir "$OUT"

echo
echo "===== 完成。产物位于 $OUT ====="
ls -1 "$OUT"
