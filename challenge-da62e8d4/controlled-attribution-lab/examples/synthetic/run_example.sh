#!/bin/sh
# Execute both candidates and both scientific outcomes, then a zero-run negative control.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /absolute/or/relative/verification-output" >&2
  exit 64
fi

EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNNER="$EXAMPLE_DIR/../../scripts/controlled_attribution.py"
OUTPUT_ROOT=$1
POSITIVE="$OUTPUT_ROOT/positive"
NEGATIVE="$OUTPUT_ROOT/confounded"

python3 "$RUNNER" --plan "$EXAMPLE_DIR/plan.json" --output-dir "$POSITIVE"

set +e
python3 "$RUNNER" --plan "$EXAMPLE_DIR/confounded_plan.json" --output-dir "$NEGATIVE"
NEGATIVE_CODE=$?
set -e
if [ "$NEGATIVE_CODE" -ne 2 ]; then
  echo "confounded plan returned $NEGATIVE_CODE; expected 2" >&2
  exit 1
fi

python3 - "$POSITIVE" "$NEGATIVE" "$EXAMPLE_DIR" <<'PY'
import json
from pathlib import Path
import sys

positive = Path(sys.argv[1])
negative = Path(sys.argv[2])
result = json.loads((positive / "result.json").read_text(encoding="utf-8"))
report = json.loads((positive / "intervention_report.json").read_text(encoding="utf-8"))
observed = {item["variant_id"]: item["status"] for item in report["conclusions"]}
expected = {
    "A_steps_4_to_40": "supported",
    "A_steps_4_to_2": "falsified",
    "B_seed_only": "inconclusive",
}
assert result["status"] == "success", result["status"]
assert result["execution_status"] == "complete", result["execution_status"]
assert result["execution_command_count"] == 13
assert observed == expected, observed
assert all(value in {"supported", "falsified", "inconclusive"} for value in observed.values())
assert {run["candidate"] for run in json.loads((positive / "runs/index.json").read_text(encoding="utf-8"))["runs"]} == {"A", "B"}
assert result["case_id"] == "synthetic-single-parameter-bug"
case_input = json.loads((Path(sys.argv[3]) / "case.json").read_text(encoding="utf-8"))
contract_fields = [item["name"] for item in case_input["output_contract"]["fields"]]
for key in (*contract_fields, "case_id", "status", "execution_status", "sources", "uncertainty", "change_records"):
    assert key in result, key
assert "output_contract" not in result
assert result["evidence_boundary"]["value"]["statement"]
assert result["attribution_summary"]["conclusions"]
assert result["candidate_comparison"]["candidate_summaries"]
assert result["evidence_delivery_complete"] is True

negative_result = json.loads((negative / "result.json").read_text(encoding="utf-8"))
negative_index = json.loads((negative / "runs/index.json").read_text(encoding="utf-8"))
assert negative_result["status"] == "unable"
assert negative_result["execution_status"] == "rejected"
assert negative_result["execution_command_count"] == 0
assert all(key in negative_result for key in contract_fields)
assert all(
    "unavailable" in negative_result[key]
    for key in ("reproduction_summary", "candidate_comparison", "attribution_summary")
)
assert negative_result["change_records"] == []
assert negative_index["execution_command_count"] == 0
assert negative_index["runs"] == []
assert not any(path.is_dir() for path in (negative / "runs").glob("*") if path.name != "index.json")
print(json.dumps({"positive": observed, "positive_status": result["status"], "positive_execution_status": result["execution_status"], "negative_status": negative_result["status"], "negative_execution_status": negative_result["execution_status"], "negative_executed": 0}, ensure_ascii=False, sort_keys=True))
PY
