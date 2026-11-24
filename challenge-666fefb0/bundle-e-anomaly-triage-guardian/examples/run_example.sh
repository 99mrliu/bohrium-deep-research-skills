#!/bin/bash
# 合成示例端到端运行脚本：init(盘点+分诊) -> (预写回答代替模型) -> finalize(归档+隔离)
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

echo '--- init (inventory + triage) ---'
$R init --input "$FIX/input" --work "$FIX/work" --out "$FIX/out"
cp "$HERE/answers.synthetic.json" "$FIX/work/answers.json"
echo '--- finalize (archive healthy + quarantine anomalies) ---'
$R finalize --work "$FIX/work" --out "$FIX/out"
echo '--- quarantine tree ---'
find "$FIX/out/library/_quarantine" -type f | sort
echo '--- rerun idempotency check ---'
$R finalize --work "$FIX/work" --out "$FIX/out"
