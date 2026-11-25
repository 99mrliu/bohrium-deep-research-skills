#!/bin/sh
# Portable synthetic demonstration with executable postconditions; writes only below examples/.
set -eu
export PYTHONDONTWRITEBYTECODE=1
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CASE="$SCRIPT_DIR/mock_case.json"
TASK="$SCRIPT_DIR/task.md"
MATERIALS="$SCRIPT_DIR/materials"
SPEC="$SCRIPT_DIR/protocol_spec.json"
WORK="$SCRIPT_DIR/work"
OUTPUT="$SCRIPT_DIR/output"
mkdir -p "$WORK" "$OUTPUT"
python3 "$ROOT/scripts/protocol_statechart.py" bootstrap \
  --case "$CASE" --task "$TASK" --materials-dir "$MATERIALS" \
  --work-dir "$WORK" --output-dir "$OUTPUT"
python3 "$ROOT/scripts/protocol_statechart.py" compile \
  --case "$CASE" --task "$TASK" --materials-dir "$MATERIALS" \
  --spec "$SPEC" --work-dir "$WORK" --output-dir "$OUTPUT"
python3 - "$CASE" "$SPEC" "$WORK" "$OUTPUT" <<'PY'
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

case_path, spec_path, work, output = map(Path, sys.argv[1:])
load = lambda path: json.loads(path.read_text(encoding="utf-8"))
case = load(case_path)
spec = load(spec_path)
bootstrap = load(work / "bootstrap_audit.json")
result = load(output / "result.json")
validation = load(output / "validation.json")
simulation = load(output / "simulation.json")
notice = "合成示例输出，非正式测评结果"

assert result["status"] == "complete", result["status"]
assert validation["status"] == "pass", validation["status"]
for field in case["output_contract"]["required_fields"]:
    assert field in result, f"missing required field: {field}"
assert result["case_id"] == case["case_id"]
assert result["output_notice"] == notice
assert not result["output_contract_unknown_fields"]

expected = {
    "nominal": ("T_SUCCESS", 9, "58", "16.4"),
    "recoverable_high_blank": ("T_SUCCESS", 12, "66", "17.1"),
    "persistent_qc_failure": ("T_QC_FAIL", 9, "26", "6.4"),
}
assert len(simulation["scenario_results"]) == 3
for scenario in simulation["scenario_results"]:
    terminal, visits, minutes, cost = expected[scenario["scenario_id"]]
    assert scenario["termination"]["terminal_id"] == terminal
    assert scenario["totals"] == {"duration_minutes": minutes, "cost": cost, "state_visits": visits}
assert simulation["decision_branch_coverage"]["complete"] is True
assert not simulation["decision_branch_coverage"]["untested_decision_branches"]
bound = simulation["envelope"]["conservative_graph_upper_bound"]
assert bound["duration_minutes"] == "66" and bound["cost"] == "17.1"
assert simulation["envelope"]["worst_case_supplied_scenario_envelope"] == {
    "max_cost": "17.1", "max_duration_minutes": "66",
    "note": "Max cost and max duration are component-wise maxima over supplied scenarios and need not belong to one path.",
}
budget = simulation["budget_deadline_audit"]
assert budget["currency"] == "CNY"
assert budget["cost"] == {"limit": "80", "upper_bound": "17.1", "within": True, "currency": "CNY"}
assert budget["deadline"]["unit"] == "days"
assert budget["deadline"]["limit_days"] == "1"
assert budget["deadline"]["upper_bound_minutes"] == "66"
assert budget["deadline"]["within"] is True
assert budget["deadline"]["booking_calendar_time_may_be_longer"] is True

candidates = {audit["candidate_id"]: audit for audit in result["candidate_assessment"]}
assert set(candidates) == {"C1_ARITHMETIC_ERROR", "C2_DOMAIN_ERROR", "C3_DOMAIN_AND_BUDGET_ERRORS"}
c1 = candidates["C1_ARITHMETIC_ERROR"]
assert c1["recomputed_total_cost"] == "16.4"
assert any("declared subtotal 1.8 != recomputed 1.9" in error for error in c1["errors"])
assert any("total_cost=15" in error for error in c1["errors"])
c2 = candidates["C2_DOMAIN_ERROR"]
assert any("off the Decimal step grid" in error for error in c2["errors"])
c3 = candidates["C3_DOMAIN_AND_BUDGET_ERRORS"]
assert c3["recomputed_total_cost"] == "90" and c3["over_budget"] is True
assert c3["est_days"] == "2" and c3["over_deadline_days"] is True
assert c3["recomputed_total_duration_minutes"] is None
assert any("exceeds budget_cap 80" in error for error in c3["errors"])
assert any("est_days 2 exceeds deadline_days 1" in error for error in c3["errors"])
assert any("outside [20, 40]" in error for error in c3["errors"])
assert any("outside [10, 30]" in error for error in c3["errors"])
assert all(candidate["revision_records"] for candidate in candidates.values())
assert result["revised_plan"]["candidate_revisions"] == spec["candidate_revisions"]
assert any(isinstance(item, dict) and item.get("topic") == "calendar_time" for item in result["uncertainty"])
assert any(isinstance(item, dict) and item.get("owner") == "resource_owner" for item in result["confirmation_items"])

register = bootstrap["resource_register"]
assert register["contract_present"] is True
assert len(register["note_objects"]) == 2
assert register["note_only_equipment_ids"] == ["EQ_COLORIMETER"]
assert register["known_ids"]["equipment"] == ["EQ_BALANCE", "EQ_COLORIMETER", "EQ_PIPETTE", "EQ_THERMOSTAT"]
assert len(register["equipment"]) == 4 and not register["conflicts"]
assert any("EQ_COLORIMETER" in state.get("equipment", []) for state in spec["states"])
assert validation["resource_register"]["note_only_equipment_ids"] == ["EQ_COLORIMETER"]
planning_sources = [source for source in result["sources"] if source["role"] == "agent_authored_planning_evidence"]
assert len(planning_sources) == 2 and all(source["source_locators"] for source in planning_sources)
assert any("not scientific proof" in source.get("evidence_scope", "") for source in result["sources"])

svg_path = output / "statechart.svg"
root = ET.parse(svg_path).getroot()
assert root.tag.endswith("svg")
assert notice in svg_path.read_text(encoding="utf-8")
for name in ("plan.json", "validation.json", "simulation.json", "result.json"):
    assert load(output / name)["output_notice"] == notice
for name in ("plan.md", "path_report.md", "statechart.svg"):
    assert notice in (output / name).read_text(encoding="utf-8")
print("example assertions: PASS (status, fields, exact paths, candidate defects, note resources, metadata, SVG, synthetic notices)")
PY
printf '%s\n' "Synthetic example generated and verified under $OUTPUT"
printf '%s\n' "合成示例输出，非正式测评结果；所有仿真结果均未实测。"
