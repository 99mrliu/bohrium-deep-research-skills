#!/usr/bin/env bash
# Run the contract-gatekeeper QC loop end-to-end on SYNTHETIC fixtures.
# All inputs and outputs are synthetic demonstrations of the interface.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${CG_RUN_ROOT:-/tmp/contract-gatekeeper-example}"

run_xml_branch() {
  local IN="$1" WORK="$2" OUT="$3"
  echo "== [xml branch] triage =="
  python3 "$BUNDLE/scripts/triage_case.py" --input "$IN" --work "$WORK" --out "$OUT"
  echo "== [xml branch] plan =="
  python3 "$BUNDLE/scripts/workplan.py" --work "$WORK"

  echo "== [xml branch] agent writes a DEFECTIVE interim result (answers nulled, claims success) =="
  python3 - "$OUT/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
r["answers"] = None                 # nulled without a named reason
r["status"] = "success"             # claimed
json.dump(r, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
  echo "== [xml branch] lint (must FAIL) =="
  if python3 "$BUNDLE/scripts/contract_lint.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"; then
    echo "ERROR: lint should have failed on the defective result" >&2; exit 1
  fi
  echo "== [xml branch] gate (must downgrade success -> partial) =="
  python3 "$BUNDLE/scripts/finalize_gate.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"

  echo "== [xml branch] agent repairs (names the null reason) =="
  python3 - "$OUT/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
r["answers"] = {"note": "synthetic interim analysis result"}
r["status"] = "success"
json.dump(r, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
  echo "== [xml branch] lint (must pass) =="
  python3 "$BUNDLE/scripts/contract_lint.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"
  echo "== [xml branch] gate (must keep success) =="
  python3 "$BUNDLE/scripts/finalize_gate.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"
}

run_metrics_branch() {
  local IN="$1" WORK="$2" OUT="$3"
  echo "== [metrics branch] triage =="
  python3 "$BUNDLE/scripts/triage_case.py" --input "$IN" --work "$WORK" --out "$OUT"
  echo "== [metrics branch] agent restates explicit metrics, marks formula tasks insufficient =="
  python3 - "$OUT/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
r["status"] = "insufficient_evidence"
r["answers"] = {
  "restated_metrics": [{"name": "test_accuracy", "value": 0.913,
                        "condition": "held-out split"}],
  "formula_level_tasks": "insufficient_evidence: no formula representation, "
                         "no per-item predictions, no recalculable raw data",
}
r["uncertainty"]["missing_objects"] = [
  "formula representation", "per-item predictions", "recalculable raw data"]
json.dump(r, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
  echo "== [metrics branch] lint + gate (must keep insufficient_evidence) =="
  python3 "$BUNDLE/scripts/contract_lint.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"
  python3 "$BUNDLE/scripts/finalize_gate.py" --case "$IN/case.json" --work "$WORK" --out "$OUT"
}

rm -rf "$ROOT"
A="$ROOT/xml"; mkdir -p "$A/app/work" "$A/app/output"
cp -r "$HERE/fixture/input-xml/." "$A/"
run_xml_branch "$A" "$A/app/work" "$A/app/output"

B="$ROOT/metrics"; mkdir -p "$B/app/work" "$B/app/output"
cp -r "$HERE/fixture/input-metrics/." "$B/"
run_metrics_branch "$B" "$B/app/work" "$B/app/output"

echo "== summary =="
python3 - <<PY
import json
for name, p in [("xml", "$A/app/output/result.json"), ("metrics", "$B/app/output/result.json")]:
    r = json.load(open(p))
    print("%s branch: status=%s" % (name, r["status"]))
PY
echo "outputs under $ROOT"
