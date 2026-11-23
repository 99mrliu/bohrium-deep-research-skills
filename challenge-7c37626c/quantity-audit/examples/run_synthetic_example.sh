#!/usr/bin/env bash
# Run the quantity-audit pipeline end-to-end on the SYNTHETIC example claims.
# All inputs and outputs are synthetic demonstrations of the interface.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${QA_RUN_ROOT:-/tmp/quantity-audit-example}"
IN="$ROOT/input"
WORK="$ROOT/app/work"
OUT="$ROOT/app/output"
rm -rf "$ROOT"
mkdir -p "$IN" "$WORK" "$OUT"
cp -r "$HERE/fixture/input/." "$IN/"

echo "== bootstrap (early partial result.json) =="
python3 "$BUNDLE/scripts/case_bootstrap.py" --input "$IN" --work "$WORK" --out "$OUT"

echo "== agent step: build claims.json from the (synthetic) paper =="
# In a real run the agent extracts values from the materials. Here the
# synthetic claims ship with the example and are copied verbatim.
cp "$HERE/fixture/claims.json" "$WORK/claims.json"

echo "== run the audit engine =="
python3 "$BUNDLE/scripts/recalc_audit.py" --claims "$WORK/claims.json" --work "$WORK" --out "$OUT"

echo "== verify result.json contract =="
python3 - "$OUT/result.json" "$IN/case.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
case = json.load(open(sys.argv[2]))
need = case["output_contract"]["required_fields"]
missing = [f for f in need if f not in r]
assert not missing, "missing fields: %s" % missing
assert r["status"] in case["output_contract"]["status_enum"]
print("status=%s audit=%s" % (r["status"], r["answers"]["audit"]["verdict_counts"]))
PY
echo "outputs under $OUT"
