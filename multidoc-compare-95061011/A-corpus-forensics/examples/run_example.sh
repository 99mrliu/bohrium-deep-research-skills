#!/usr/bin/env bash
# run_example.sh — 端到端运行合成示例（语料取证 -> 相关性门控 -> 锚定机检 -> 矩阵渲染）
# 全部内容为合成示例，非任何正式案例结果。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../scripts"
OUT="$HERE/output"
mkdir -p "$OUT"

echo "== [1/4] build_registry: 语料取证注册表（指纹/近重复/多版本/段落锚定） =="
python3 "$SCRIPTS/build_registry.py" "$HERE/corpus" --out "$OUT"

echo "== [2/4] parse_audit: 独立解析保真审计（与注册表内嵌审计互为印证） =="
python3 "$SCRIPTS/parse_audit.py" "$HERE/corpus" -o "$OUT/parse-audit.json"

echo "== [3/4] relevance_gate: 工单维度词相关性门控 =="
python3 "$SCRIPTS/relevance_gate.py" --registry "$OUT" \
    --workorder "$HERE/comparison-workorder.json" --out "$OUT/relevance.json"

echo "== [4/4] verify_anchors + render_matrix: 机检示例单元格并渲染矩阵 =="
python3 "$SCRIPTS/verify_anchors.py" --registry "$OUT" \
    --cells "$HERE/sample_cells.jsonl" --relevance "$OUT/relevance.json" \
    | tee "$OUT/verify-report.txt"
python3 "$SCRIPTS/render_matrix.py" --registry "$OUT" \
    --cells "$HERE/sample_cells.jsonl" --out "$OUT/comparison-matrix.md"

echo
echo "Done. Artifacts in $OUT:"
echo "  registry.json  <DOCID>.paragraphs.jsonl  parse-audit.json"
echo "  relevance.json  verify-report.txt  comparison-matrix.md"
