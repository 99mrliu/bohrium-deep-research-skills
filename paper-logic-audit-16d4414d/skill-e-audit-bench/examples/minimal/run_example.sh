#!/bin/sh
# 合成示例（非正式案例）：端到端演示"基准自测 → 评分 → 真实案例门禁"。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$HERE/../../bench"
SCRIPTS="$HERE/../../scripts/bench.py"
OUT="$HERE/outputs"
RUNS="$OUT/runs.jsonl"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"
rm -f "$RUNS" "$OUT"/grade_*.json

echo "== 1. 合格 findings 跑三篇基准 =="
"$PY" "$SCRIPTS" grade --bench "$BENCH" --paper p1 \
  --findings "$HERE/inputs/demo_findings_p1_good.json" --runs "$RUNS"
"$PY" "$SCRIPTS" grade --bench "$BENCH" --paper p2 \
  --findings "$HERE/inputs/demo_findings_p2_good.json" --runs "$RUNS"
"$PY" "$SCRIPTS" grade --bench "$BENCH" --paper p3 \
  --findings "$HERE/inputs/demo_findings_p3_good.json" --runs "$RUNS"

echo "== 2. 复跑 p1 检验 STABLE =="
"$PY" "$SCRIPTS" grade --bench "$BENCH" --paper p1 \
  --findings "$HERE/inputs/demo_findings_p1_good.json" --runs "$RUNS"

echo "== 3. 弱 findings（漏报+误报+伪造 quote）应召回不足并标出违规 =="
if "$PY" "$SCRIPTS" grade --bench "$BENCH" --paper p1 \
    --findings "$HERE/inputs/demo_findings_p1_weak.json" --runs "$RUNS"; then
  echo "NOTE: 弱 findings 未触发召回告警（检查阈值）"
else
  echo "OK: 弱 findings 被标出（exit=$?）"
fi

echo "== 4. 真实案例侧门禁：anchor + verify =="
"$PY" "$SCRIPTS" anchor --paper "$BENCH/p1.txt" --work "$OUT/work_p1"
"$PY" "$SCRIPTS" verify --work "$OUT/work_p1" \
  --findings "$HERE/inputs/demo_findings_p1_good.json"
if "$PY" "$SCRIPTS" verify --work "$OUT/work_p1" \
    --findings "$HERE/inputs/demo_findings_p1_weak.json"; then
  echo "ERROR: 预期 verify 拦下伪造 quote 但没有"; exit 1
else
  echo "OK: verify 拦下伪造 quote"
fi
echo "== 合成示例完成：产物在 $OUT =="
