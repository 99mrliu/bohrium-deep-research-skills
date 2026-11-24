#!/bin/sh
# 合成示例（非正式案例）：端到端跑 claimledger 三步管线。
# 产物写入 examples/minimal/outputs/work/，可目检。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/outputs/work"
mkdir -p "$WORK"
PY="${PYTHON:-python3}"

echo "== 1. anchor =="
"$PY" "$HERE/../../scripts/claimledger.py" anchor \
  --paper "$HERE/inputs/synthetic_paper.txt" --work "$WORK" || true

echo "== 2. scaffold =="
"$PY" "$HERE/../../scripts/claimledger.py" scaffold --work "$WORK"

echo "== 3a. lint：填入一份'演示填法'（含两处故意违规：伪造 quote + 把转述定成作者错误）=="
"$PY" "$HERE/inputs/fill_demo.py" --work "$WORK" --out "$WORK/claims_demo_bad.json"
if "$PY" "$HERE/../../scripts/claimledger.py" lint --work "$WORK" \
    --claims "$WORK/claims_demo_bad.json"; then
  echo "ERROR: 预期 lint 拦下违规但没有"; exit 1
else
  echo "OK: lint 按预期拦下违规（exit=$?）"
fi

echo "== 3b. lint：修正后的填法应通过 =="
"$PY" "$HERE/inputs/fill_demo.py" --work "$WORK" --out "$WORK/claims_demo_ok.json" --fix
"$PY" "$HERE/../../scripts/claimledger.py" lint --work "$WORK" \
  --claims "$WORK/claims_demo_ok.json"
echo "== 合成示例完成：产物在 $WORK =="
