#!/bin/sh
# 合成示例（非正式案例）：端到端跑 evmap 三步管线。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/outputs/work"
mkdir -p "$WORK"
PY="${PYTHON:-python3}"

echo "== 1. scan =="
"$PY" "$HERE/../../scripts/evmap.py" scan \
  --paper "$HERE/inputs/synthetic_paper.txt" --work "$WORK"

echo "== 2. candidates（E1–E4 机械候选）=="
"$PY" "$HERE/../../scripts/evmap.py" candidates --work "$WORK"

echo "== 3a. verify：伪造 quote + 空建议的 findings 应被拦下 =="
if "$PY" "$HERE/../../scripts/evmap.py" verify --work "$WORK" \
    --findings "$HERE/inputs/demo_findings_bad.json"; then
  echo "ERROR: 预期 verify 拦下违规但没有"; exit 1
else
  echo "OK: verify 按预期拦下违规"
fi

echo "== 3b. verify：合规 findings 通过 =="
"$PY" "$HERE/../../scripts/evmap.py" verify --work "$WORK" \
  --findings "$HERE/inputs/demo_findings_ok.json"
echo "== 合成示例完成：产物在 $WORK =="
