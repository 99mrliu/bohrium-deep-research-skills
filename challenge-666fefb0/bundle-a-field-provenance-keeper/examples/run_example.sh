#!/bin/bash
# 合成示例端到端运行脚本：init -> (预写决策代替模型) -> lint -> finalize
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(cd "$HERE/.." && pwd)
FIX="$HERE/fixture"

if [ ! -f "$FIX/input/case.json" ]; then
  python3 "$HERE/make_fixture.py"
fi
rm -rf "$FIX/work" "$FIX/out"
mkdir -p "$FIX/work" "$FIX/out"

echo '--- init ---'
python3 "$SKILL/scripts/run_case.py" init --input "$FIX/input" --work "$FIX/work" --out "$FIX/out"

echo '--- install synthetic decisions (replaces the model step) ---'
cp "$HERE/decisions.synthetic.json" "$FIX/work/decisions.json"

echo '--- lint ---'
python3 "$SKILL/scripts/run_case.py" lint --work "$FIX/work"

echo '--- finalize ---'
python3 "$SKILL/scripts/run_case.py" finalize --work "$FIX/work" --out "$FIX/out"

echo '--- summary ---'
python3 - "$FIX/out/result.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print('status:', d['status'])
print('indexed:', len(d['library_index']), ' skipped:', len(d['skipped']),
      ' ops:', d['operations_log']['total_ops'])
print('uncertainties:', len(d['uncertainties']))
PY
