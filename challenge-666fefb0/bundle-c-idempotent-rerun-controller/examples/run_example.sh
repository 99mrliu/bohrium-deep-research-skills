#!/bin/bash
# 合成示例端到端运行脚本：演示 崩溃注入→续跑→幂等证书→回滚 全过程
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(cd "$HERE/.." && pwd)
FIX="$HERE/fixture"
R="python3 $SKILL/scripts/run_case.py"

if [ ! -f "$FIX/input/case.json" ]; then
  python3 "$HERE/make_fixture.py"
fi
rm -rf "$FIX/work" "$FIX/out"
mkdir -p "$FIX/work" "$FIX/out"

echo '--- 1. init ---'
$R init --input "$FIX/input" --work "$FIX/work" --out "$FIX/out"
cp "$HERE/decisions.synthetic.json" "$FIX/work/decisions.json"

echo '--- 2. plan ---'
$R plan --work "$FIX/work" --out "$FIX/out"

echo '--- 3. apply with INJECTED CRASH after 3 ops (exit code 3 expected) ---'
set +e
$R apply --work "$FIX/work" --out "$FIX/out" --stop-after 3
echo "exit=$? (3 = simulated crash, journal stays consistent)"
set -e

echo '--- 4. resume apply ---'
$R apply --work "$FIX/work" --out "$FIX/out"

echo '--- 5. verify ---'
$R verify --work "$FIX/work" --out "$FIX/out"

echo '--- 6. certify idempotency ---'
$R certify --work "$FIX/work" --out "$FIX/out"

echo '--- 7. finalize ---'
$R finalize --work "$FIX/work" --out "$FIX/out"

echo '--- 8. undo demo (rollback, then rebuild) ---'
$R undo --work "$FIX/work" --out "$FIX/out"
$R apply --work "$FIX/work" --out "$FIX/out"
$R verify --work "$FIX/work" --out "$FIX/out"
echo 'rollback-then-rebuild OK'
