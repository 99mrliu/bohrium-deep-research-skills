#!/bin/bash
# 合成示例端到端运行脚本：init -> graph -> (预写裁决代替模型) -> finalize
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

echo '--- init ---'
$R init --input "$FIX/input" --work "$FIX/work" --out "$FIX/out"
echo '--- graph (multi-signal typed edges + canonical arbitration) ---'
$R graph --work "$FIX/work" --out "$FIX/out"
cp "$HERE/adjudication.synthetic.json" "$FIX/work/adjudication.json"
echo '--- finalize (archive + render graph + result) ---'
$R finalize --work "$FIX/work" --out "$FIX/out"
echo '--- graph.md preview ---'
head -40 "$FIX/out/graph.md"
