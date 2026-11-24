#!/bin/sh
# 合成示例一键复现脚本（合成示例，非正式案例数据）
# 依次运行 4 个脚本，产物写入 examples/synthetic/output/
set -e

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPTS="$HERE/../../scripts"
OUT="$HERE/output"
CASE="$HERE/case.json"
EVIDENCE="$HERE/evidence_ledger.jsonl"

mkdir -p "$OUT"

echo "== [1/4] build_plan_index =="
python3 "$SCRIPTS/build_plan_index.py" "$CASE" "$OUT"

echo "== [2/4] verify_anchors =="
python3 "$SCRIPTS/verify_anchors.py" "$OUT/plans.json" "$EVIDENCE" "$OUT"

echo "== [3/4] scan_contradictions =="
python3 "$SCRIPTS/scan_contradictions.py" "$OUT/plans.json" "$OUT/contradictions.md"

echo "== [4/4] assemble_result =="
python3 "$SCRIPTS/assemble_result.py" \
  --case "$CASE" \
  --anchors "$OUT/anchors_verified.json" \
  --contradictions "$OUT/contradictions.md" \
  --out "$OUT/result.json" \
  --status complete \
  --note "合成示例一键复现（非正式案例数据）" \
  --sources "$OUT/materials.json"

echo "== 全部完成，产物位于 $OUT =="
