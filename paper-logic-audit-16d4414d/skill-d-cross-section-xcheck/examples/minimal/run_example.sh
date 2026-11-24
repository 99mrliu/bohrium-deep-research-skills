#!/bin/sh
# 合成示例（非正式案例）：端到端跑 xcheck 三步管线。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/outputs/work"
mkdir -p "$WORK"
PY="${PYTHON:-python3}"

echo "== 1. scan =="
"$PY" "$HERE/../../scripts/xcheck.py" scan \
  --paper "$HERE/inputs/synthetic_paper.txt" --work "$WORK"

echo "== 2. xcheck（X1–X4 跨章候选）=="
"$PY" "$HERE/../../scripts/xcheck.py" xcheck --work "$WORK"

echo "== 3a. verify：伪造 quote + 缺 side_b 应被拦下 =="
if "$PY" "$HERE/../../scripts/xcheck.py" verify --work "$WORK" \
    --findings "$HERE/inputs/demo_findings_bad.json"; then
  echo "ERROR: 预期 verify 拦下违规但没有"; exit 1
else
  echo "OK: verify 按预期拦下违规"
fi

echo "== 3b. verify：双侧锚定的合规 findings 通过 =="
"$PY" "$HERE/../../scripts/xcheck.py" verify --work "$WORK" \
  --findings "$HERE/inputs/demo_findings_ok.json"
echo "== 合成示例完成：产物在 $WORK =="
