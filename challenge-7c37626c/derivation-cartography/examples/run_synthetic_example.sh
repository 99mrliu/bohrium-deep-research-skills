#!/usr/bin/env bash
# Run the derivation-cartography pipeline end-to-end on the SYNTHETIC fixture.
# All inputs and outputs are synthetic demonstrations of the interface.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${DC_RUN_ROOT:-/tmp/derivation-cartography-example}"
IN="$ROOT/input"
WORK="$ROOT/app/work"
OUT="$ROOT/app/output"
rm -rf "$ROOT"
mkdir -p "$IN" "$WORK" "$OUT"
cp -r "$HERE/fixture/input/." "$IN/"

echo "== bootstrap =="
python3 "$BUNDLE/scripts/case_bootstrap.py" --input "$IN" --work "$WORK" --out "$OUT"

echo "== build the formula dependency graph =="
python3 "$BUNDLE/scripts/graph_build.py" --case "$IN/case.json" --input "$IN" --work "$WORK"

echo "== assumption radar =="
python3 "$BUNDLE/scripts/assumption_radar.py" --case "$IN/case.json" --input "$IN" --work "$WORK"

echo "== agent step: write steps.json (synthetic fixture ships one) =="
cp "$HERE/fixture/steps.json" "$WORK/steps.json"

echo "== fail-closed step gate =="
python3 "$BUNDLE/scripts/step_gate.py" --work "$WORK" --out "$OUT"

echo "== verify result.json contract =="
python3 - "$OUT/result.json" "$IN/case.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
case = json.load(open(sys.argv[2]))
need = case["output_contract"]["required_fields"]
missing = [f for f in need if f not in r]
assert not missing, "missing fields: %s" % missing
assert r["status"] in case["output_contract"]["status_enum"]
dm = r["answers"]["derivation_map"]
print("status=%s graph=%s defective=%s" % (r["status"], dm["graph_summary"], r["uncertainty"]["defective_steps"]))
PY
echo "outputs under $OUT"
