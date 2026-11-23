#!/usr/bin/env bash
# Run the mml-forensics pipeline end-to-end on the SYNTHETIC example fixture.
# The fixture and all outputs are synthetic demonstrations of the interface,
# not platform case results. Stdlib only; no network.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${FX_RUN_ROOT:-/tmp/mml-forensics-example}"
IN="$ROOT/input"
WORK="$ROOT/app/work"
OUT="$ROOT/app/output"
rm -rf "$ROOT"
mkdir -p "$IN" "$WORK" "$OUT"
cp -r "$HERE/fixture/input/." "$IN/"

echo "== bootstrap =="
python3 "$BUNDLE/scripts/case_bootstrap.py" --input "$IN" --work "$WORK" --out "$OUT"

echo "== forensic scan =="
python3 "$BUNDLE/scripts/forensic_scan.py" --input "$IN" --work "$WORK"

echo "== cross-layer check =="
python3 "$BUNDLE/scripts/crosscheck_layers.py" --case "$IN/case.json" --input "$IN" --work "$WORK"

echo "== merge into result.json =="
python3 "$BUNDLE/scripts/merge_result.py" --case "$IN/case.json" --input "$IN" --work "$WORK" --out "$OUT"

echo "== verify result.json contract =="
python3 - "$OUT/result.json" "$IN/case.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
case = json.load(open(sys.argv[2]))
need = case["output_contract"]["required_fields"]
missing = [f for f in need if f not in r]
assert not missing, "missing fields: %s" % missing
assert r["status"] in case["output_contract"]["status_enum"]
print("status=%s verified=%s" % (r["status"], r["answers"]["authenticity_verdict"]["verified_formulas"]))
PY
echo "outputs under $OUT"
