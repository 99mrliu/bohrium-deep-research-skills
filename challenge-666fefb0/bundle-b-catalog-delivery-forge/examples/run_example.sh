#!/bin/bash
# 合成示例端到端运行脚本：init -> (预写覆盖代替模型) -> finalize（含四件套渲染）
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(cd "$HERE/.." && pwd)
FIX="$HERE/fixture"

if [ ! -f "$FIX/input/case.json" ]; then
  python3 "$HERE/make_fixture.py"
fi
rm -rf "$FIX/work" "$FIX/out"
mkdir -p "$FIX/work" "$FIX/out"

echo '--- init (inventory + deterministic proposal) ---'
python3 "$SKILL/scripts/run_case.py" init --input "$FIX/input" --work "$FIX/work" --out "$FIX/out"

echo '--- install synthetic overrides (replaces the model step) ---'
cp "$HERE/overrides.synthetic.json" "$FIX/work/overrides.json"

echo '--- finalize (apply + render + result) ---'
python3 "$SKILL/scripts/run_case.py" finalize --work "$FIX/work" --out "$FIX/out"

echo '--- deliverables ---'
ls "$FIX/out"
