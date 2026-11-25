#!/bin/sh
set -eu

# All fixtures and expected labels are synthetic. No output is written to the bundle
# unless the caller explicitly chooses such an output directory.
EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLE_DIR=$(CDPATH= cd -- "$EXAMPLE_DIR/.." && pwd)
if [ "$#" -gt 1 ]; then
  printf 'usage: %s [output-directory]\n' "$0" >&2
  exit 2
fi
if [ "$#" -eq 1 ]; then
  OUT=$1
  mkdir -p "$OUT"
else
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/rubric-mutation-lab.XXXXXX")
fi
export PYTHONDONTWRITEBYTECODE=1

run_positive() {
  DEST=$1
  mkdir -p "$DEST"
  python3 "$BUNDLE_DIR/scripts/score_engine.py" \
    --items "$EXAMPLE_DIR/item_bank.json" --item-id synth-reaction \
    --candidate-file "$EXAMPLE_DIR/engine_candidate.txt" \
    --output "$DEST/engine_score.json"
  python3 "$BUNDLE_DIR/scripts/mutation_check.py" \
    --items "$EXAMPLE_DIR/item_bank.json" \
    --output "$DEST/mutation_report.json"
  python3 "$BUNDLE_DIR/scripts/score_outputs.py" \
    --items "$EXAMPLE_DIR/item_bank.json" \
    --candidate-outputs "$EXAMPLE_DIR/candidate_outputs.json" \
    --output "$DEST/score_report.json"
  python3 "$BUNDLE_DIR/scripts/finalize.py" \
    --case "$EXAMPLE_DIR/case.json" --items "$EXAMPLE_DIR/item_bank.json" \
    --score-report "$DEST/score_report.json" \
    --mutation-report "$DEST/mutation_report.json" \
    --output "$DEST/result.json" --strict
}

run_positive "$OUT/pass-1"
run_positive "$OUT/pass-2"
for name in engine_score.json mutation_report.json score_report.json result.json; do
  cmp "$OUT/pass-1/$name" "$OUT/pass-2/$name"
done

# Verify observed positive results rather than merely trusting zero exit codes.
python3 - "$EXAMPLE_DIR/case.json" "$OUT/pass-1/mutation_report.json" "$OUT/pass-1/score_report.json" "$OUT/pass-1/result.json" <<'PY'
import json, sys
case, mutation, scores, result = [
    json.load(open(path, encoding="utf-8")) for path in sys.argv[1:]]
assert mutation["status"] == "passed"
assert mutation["summary"]["probe_count"] == 45
assert mutation["summary"]["disagreement_count"] == 0
assert scores["rollup"] == {
    "score_total": 7, "max_score": 8, "scored_required_count": 4,
    "required_denominator": 4, "normalization_denominator": 8,
    "normalized_score": 0.875,
    "formula": "sum(score of scored required four) / (2 * scored required count)"
}
assert [r["score"] for r in scores["records"]] == [1, 2, 2, 2]
assert result["case_id"] == "SYNTHETIC-RUBRIC-LAB-004"
assert result["contract_field_to_preserve"]["nested_original_value"] == 17
contract = {entry["name"]: entry for entry in case["output_contract"]["fields"]}
assert contract, "example must exercise its declared contract"
for name, spec in contract.items():
    assert name in result, "contract field is not top-level: " + name
    expected_type = {"object": dict, "array": list, "string": str,
                     "boolean": bool}[spec["type"]]
    assert isinstance(result[name], expected_type), (name, type(result[name]))
assert result["item_bank"]["items"] and len(result["item_bank"]["items"]) == 4
assert result["score_report"] == scores
assert result["mutation_report"] == mutation
assert result["sources"] == case["sources"]
assert result["uncertainty"] == case["uncertainty"]
assert result["change_records"] == case["change_records"]
assert result["status"] == "complete"
assert result["summary"]["success"] is True
assert result["rubric_mutation_lab"]["status"] == "complete"
assert all(g["passed"] for g in result["rubric_mutation_lab"]["strict_gates"])
PY

# Contract-shape regression: dynamic binding must not depend on synthetic example
# metadata, repeated case_id/status declarations, or the nested exporter alone.
python3 - "$BUNDLE_DIR/scripts" "$EXAMPLE_DIR/case.json" \
  "$EXAMPLE_DIR/item_bank.json" "$OUT/pass-1/score_report.json" \
  "$OUT/pass-1/mutation_report.json" <<'PY'
import copy, json, sys
sys.path.insert(0, sys.argv[1])
import finalize as finalizer
case, bank, scores, mutation = [
    json.load(open(path, encoding="utf-8")) for path in sys.argv[2:]]
shapes = [
    ("list", ["item_bank", "score_report", "mutation_report", "sources",
              "uncertainty", "change_records", "status"]),
    ("fields-list", {"fields": ["benchmark_draft", "questions",
                                "actual_score_records", "rollup", "success", "summary"]}),
    ("fields-objects", {"fields": [
        {"name": "draft_item_bank", "type": "object"},
        {"name": "items", "type": "array"},
        {"name": "scores", "type": "array"},
        {"name": "diagnostics", "type": "object"},
        {"name": "success", "type": "boolean"},
        {"name": "human_agreement", "type": "object"},
    ]}),
    ("direct-map", {
        "item_bank": "object", "questions": "array",
        "score_report": {"type": "object"},
        "mutation_report": {"type": "object"},
        "sources": {"type": "array"}, "uncertainty": {"type": "array"},
        "change_records": {"type": "array"}, "success": "boolean",
    }),
    ("properties", {
        "properties": {
            "benchmark_draft": {"type": "object"},
            "score_report": {"type": "object"},
            "scores": {"type": "array"}, "rollup": {"type": "object"},
        },
        "required": ["benchmark_draft", "score_report", "scores", "rollup"],
    }),
    ("required-fields", {"required_fields": [
        "item_bank", "score_report", "mutation_report", "sources",
        "uncertainty", "change_records",
    ]}),
    ("required-top-level-fields", {
        "properties": {
            "item_bank": {"type": "object"}, "questions": {"type": "array"},
            "mutation_report": {"type": "object"}, "diagnostics": {"type": "object"},
        },
        "required_top_level_fields": [
            "item_bank", "questions", "mutation_report", "diagnostics"],
    }),
]

def names(contract):
    if isinstance(contract, list):
        return contract
    if "fields" in contract:
        return [entry if isinstance(entry, str) else entry["name"]
                for entry in contract["fields"]]
    if "properties" in contract:
        return list(contract["properties"])
    if "required_fields" in contract and len(contract) == 1:
        return contract["required_fields"]
    controls = {"required", "required_fields", "required_top_level_fields",
                "optional_fields", "description", "title", "schema_version",
                "$schema", "additionalProperties"}
    return [name for name in contract if name not in controls]

for label, contract in shapes:
    assert "case_id" not in names(contract), label
    if label != "list":
        assert "status" not in names(contract), label
    shaped = copy.deepcopy(case)
    shaped["output_contract"] = contract
    result, complete = finalizer.finalize(shaped, bank, scores, mutation, [])
    assert complete, (label, result["rubric_mutation_lab"]["strict_gates"])
    assert result["case_id"] == case["case_id"]
    assert result["status"] == "complete"
    assert result["success"] is True
    for name in names(contract):
        assert name in result and result[name] is not None, (label, name)
    if "questions" in names(contract):
        assert len(result["questions"]) == 4
    if "scores" in names(contract):
        assert [record["score"] for record in result["scores"]] == [1, 2, 2, 2]

unknown = copy.deepcopy(case)
unknown["output_contract"] = {"item_bank": "object", "not_a_lab_output": "string"}
result, complete = finalizer.finalize(unknown, bank, scores, mutation, [])
assert not complete and result["status"] == "partial"
assert result["not_a_lab_output"] is None
failed = {g["gate"] for g in result["rubric_mutation_lab"]["strict_gates"] if not g["passed"]}
assert "contract_field:not_a_lab_output" in failed

wrong_type = copy.deepcopy(case)
wrong_type["output_contract"] = {"fields": [{"name": "item_bank", "type": "string"}]}
result, complete = finalizer.finalize(wrong_type, bank, scores, mutation, [])
assert not complete and result["item_bank"] == ""
assert result["status"] == "partial"

early = copy.deepcopy(case)
result, complete = finalizer.finalize(
    early, bank, None, None, ["score report was not supplied", "mutation report was not supplied"])
assert not complete and result["status"] == "partial" and result["success"] is False
for entry in early["output_contract"]["fields"]:
    assert entry["name"] in result
assert isinstance(result["item_bank"], dict)
assert result["score_report"] == {} and result["mutation_report"] == {}
assert isinstance(result["summary"], dict) and result["summary"]["success"] is False

unmeasured = copy.deepcopy(case)
unmeasured["output_contract"] = {
    "properties": {
        "item_bank": {"type": "object"},
        "human_agreement_score": {"type": "number"},
    },
    "required": ["item_bank"],
}
result, complete = finalizer.finalize(unmeasured, bank, scores, mutation, [])
assert result["human_agreement_score"] is None
assert not complete and result["status"] == "partial"
print("PASS: all output_contract shapes, unknown fields, types, and early partial")
PY

# Exercise the actual no-report CLI early-partial write path as well.
set +e
python3 "$BUNDLE_DIR/scripts/finalize.py" \
  --case "$EXAMPLE_DIR/case.json" --items "$EXAMPLE_DIR/item_bank.json" \
  --output "$OUT/early_partial_result.json" --strict
EARLY_STATUS=$?
set -e
if [ "$EARLY_STATUS" -eq 0 ]; then
  printf 'early partial unexpectedly passed strict finalization\n' >&2
  exit 1
fi
python3 - "$EXAMPLE_DIR/case.json" "$OUT/early_partial_result.json" "$EARLY_STATUS" <<'PY'
import json, sys
case = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.load(open(sys.argv[2], encoding="utf-8"))
assert int(sys.argv[3]) != 0
assert result["case_id"] == case["case_id"]
assert result["status"] == "partial" and result["success"] is False
for entry in case["output_contract"]["fields"]:
    assert entry["name"] in result, entry["name"]
assert result["score_report"] == {} and result["mutation_report"] == {}
assert any(g["gate"] == "input_error" and not g["passed"]
           for g in result["rubric_mutation_lab"]["strict_gates"])
PY

# Meaningful negative mutation: allow mg in a percentage predicate without changing
# the independent probe label. The wrong-unit probe must become a score-2 acceptance,
# and mutation_check must reject that disagreement.
python3 - "$EXAMPLE_DIR/item_bank.json" "$OUT/mutated_wrong_unit_item_bank.json" <<'PY'
import json, sys
bank = json.load(open(sys.argv[1], encoding="utf-8"))
item = next(x for x in bank["items"] if x["item_id"] == "synth-reaction")
check = next(x for x in item["rubric"]["predicates"] if x["id"] == "yield")
check["predicate"]["numeric"]["units"].append("mg")
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(bank, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
PY
set +e
python3 "$BUNDLE_DIR/scripts/mutation_check.py" \
  --items "$OUT/mutated_wrong_unit_item_bank.json" \
  --output "$OUT/negative_mutation_report.json"
NEGATIVE_STATUS=$?
set -e
if [ "$NEGATIVE_STATUS" -eq 0 ]; then
  printf 'negative mutation unexpectedly passed\n' >&2
  exit 1
fi
python3 - "$OUT/negative_mutation_report.json" "$NEGATIVE_STATUS" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert int(sys.argv[2]) != 0
assert report["status"] == "failed"
item = next(x for x in report["items"] if x["item_id"] == "synth-reaction")
probe = next(x for x in item["probe_results"] if x["probe_id"] == "synth-reaction-wrong-unit")
assert probe["expected_score"] == 1
assert probe["actual_score"] == 2
assert probe["actual_predicates"]["yield"] is True
assert probe["predicate_disagreements"]["yield"] == {"expected": False, "actual": True}
PY
printf 'expected failure: exit=%s; wrong mg unit was accepted at score 2 and rejected by independent probe\n' \
  "$NEGATIVE_STATUS" > "$OUT/negative_mutation.log"
printf 'PASS: deterministic positive suite and expected-failure negative mutation\n'
printf 'Output directory: %s\n' "$OUT"
