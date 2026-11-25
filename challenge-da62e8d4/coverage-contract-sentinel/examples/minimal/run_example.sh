#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="$(cd "$HERE/../.." && pwd)"
DEFAULT_OUT="$(cd "$HERE/../../../.." && pwd)/verification/coverage-contract-sentinel/example-run"
OUT="${1:-$DEFAULT_OUT}"
TOOL="$SKILL/scripts/coverage_contract.py"
POS="$OUT/positive"
NEG="$OUT/negative"
if [[ -e "$POS/coverage.json" || -e "$NEG/coverage.json" ]]; then
  echo "Refusing existing example state; choose a new output directory." >&2
  exit 2
fi
mkdir -p "$POS/inputs" "$OUT"
cp "$HERE/case.json" "$HERE/paper_excerpt.md" "$POS/inputs/"
python3 "$HERE/generate_synthetic.py" --output-dir "$POS/synthetic_logs"
python3 "$TOOL" init --case "$POS/inputs/case.json" --workdir "$POS" --with-png
python3 "$TOOL" register requirements --payload "$HERE/requirements.json" --workdir "$POS"
python3 "$TOOL" register evidence --payload "$HERE/evidence.json" --base-dir "$POS" --workdir "$POS"
python3 "$TOOL" register answers --payload "$HERE/answers.json" --workdir "$POS"
python3 "$TOOL" finalize --workdir "$POS" | tee "$OUT/positive_finalize.log"
python3 - "$POS/result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
delivery = result["delivery"]
assert delivery["contract_status"] == "PASS", delivery
assert delivery["coverage_status"] == "partial", delivery
assert delivery["scientific_status"] == "degraded", delivery
assert result["status"] == "partial", result["status"]
assert set(result) == {
    "case_id", "status", "sources", "uncertainty", "change_records", "delivery",
    "question_response", "method_comparison", "released_data_note",
}
state = json.load(open(sys.argv[1].replace("result.json", "coverage.json"), encoding="utf-8"))
assert result["sources"] == [
    {"id": item["id"], "path": item["path"], "hash": item["sha256"],
     "locator": item["locator"], "kind": item["kind"]}
    for item in state["evidence"]
]
assert all(set(("path", "hash", "locator", "kind")) <= set(item) for item in result["sources"])
assert result["uncertainty"]["scientific_notes"] == delivery["scientific_notes"]
assert result["uncertainty"]["coverage_gaps"] == delivery["coverage_diagnostics"]
assert result["uncertainty"]["unavailable_reasons"][0]["field"] == "released_data_note"
assert [item["operation"] for item in result["change_records"]] == [
    "init", "register", "register", "register", "finalize"
]
assert result["change_records"][-1]["atomic_state"] == {
    "finalized": True, "contract_status": "PASS", "coverage_status": "partial",
    "scientific_status": "degraded", "status": "partial",
}
assert "unavailable" in result["released_data_note"]
assert set(("candidate_a", "candidate_b", "difference_attribution")) <= set(result["method_comparison"]["answer_fragment"])
assert "output_contract" not in result
print("positive assertions: partial / PASS / partial / degraded; flat standards, sources, uncertainty, changes retained")
PY

# Negative control: identical known evidence ledger, but the answered field deliberately has no evidence_ids.
python3 "$TOOL" init --case "$POS/inputs/case.json" --workdir "$NEG"
python3 "$TOOL" register requirements --payload "$HERE/requirements.json" --workdir "$NEG"
python3 "$TOOL" register evidence --payload "$HERE/evidence.json" --base-dir "$POS" --workdir "$NEG"
python3 "$TOOL" register answers --payload "$HERE/negative_answers.json" --workdir "$NEG"
set +e
python3 "$TOOL" finalize --workdir "$NEG" >"$OUT/negative_finalize.log" 2>&1
NEGATIVE_EXIT=$?
set -e
cat "$OUT/negative_finalize.log"
if [[ "$NEGATIVE_EXIT" -ne 2 ]]; then
  echo "negative control unexpectedly exited $NEGATIVE_EXIT" >&2
  exit 1
fi
python3 - "$NEG/result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
delivery = result["delivery"]
assert delivery["contract_status"] == "FAIL", delivery
assert result["status"] in {"unable", "partial"}, result["status"]
assert result["status"] == {"complete": "success", "degraded": "partial", "unavailable": "unable"}[
    delivery["scientific_status"]
]
assert result["uncertainty"]["coverage_gaps"]["fields_without_answer"]
assert result["change_records"][-1]["operation"] == "finalize"
assert result["change_records"][-1]["details"]["exit_code"] == 2
assert result["change_records"][-1]["atomic_state"]["contract_status"] == "FAIL"
assert any("evidence_ids" in item for item in delivery["contract_errors"]), delivery
print("negative assertions: missing-evidence answer rejected with exit 2; flat status and uncertainty retained")
PY
printf 'SVG: %s\n' "$POS/coverage.svg"
printf 'PNG: %s\n' "$POS/coverage.png"
printf 'example checks complete\n'
