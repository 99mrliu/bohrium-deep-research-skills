#!/usr/bin/env bash
# SYNTHETIC end-to-end positive, selective-impact, and negative execution.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
if [[ $# -eq 0 ]]; then
  OUT="$(mktemp -d "${TMPDIR:-/tmp}/rerun-impact-ledger.XXXXXX")"
elif [[ $# -eq 2 && "$1" == "--output-dir" ]]; then
  OUT="$2"
else
  echo "usage: ./run_example.sh [--output-dir DIRECTORY]" >&2
  exit 2
fi
OUT="$("$PYTHON" -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$OUT")"
case "$OUT" in
  "$ROOT"|"$ROOT"/*)
    echo "generated output inside the bundle is forbidden" >&2
    exit 2
    ;;
esac
mkdir -p "$OUT"
exec > >(tee "$OUT/run_example.log") 2>&1
EX="$ROOT/examples/synthetic"

stage_input() {
  local version="$1"
  local destination="$2"
  mkdir -p "$destination/materials"
  cp "$EX/case_${version}.json" "$destination/case.json"
  cp "$EX/task_${version}.md" "$destination/task.md"
  cp "$EX/materials_${version}/"* "$destination/materials/"
}
stage_input v1 "$OUT/input_v1"
stage_input v2 "$OUT/input_v2"
"$PYTHON" "$ROOT/scripts/early_partial.py" \
  --case "$OUT/input_v1/case.json" --output "$OUT/pre_authoring_result.json"
"$PYTHON" - "$OUT/pre_authoring_result.json" "$OUT/input_v1/case.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
case = json.load(open(sys.argv[2], encoding="utf-8"))
assert result["case_id"] == case["case_id"] and result["status"] == "PARTIAL"
assert result["summary"]["expected_item_count"] == 4
assert result["uncertainty"] and result["change_records"]
PY

init_run() {
  local input="$1"
  local bank="$2"
  local result="$3"
  "$PYTHON" "$ROOT/scripts/init_run.py" \
    --input-dir "$input" \
    --work-root "$OUT/work" \
    --output-result "$result" \
    --item-bank "$bank" \
    --time-budget-seconds 30 \
    --output-budget-bytes 5000000 \
    --model not-used-deterministic-synthetic-scorer \
    --harness run_example.sh-v1
}

make_command() {
  local run="$1"
  local input="$2"
  local bank="$3"
  local negative="$4"
  "$PYTHON" - "$PYTHON" "$EX/scorer.py" "$bank" "$input/materials" "$run/run_config.json" "$run" "$negative" <<'PY'
import json, sys
command = [sys.argv[1], sys.argv[2], "--item-bank", sys.argv[3], "--materials", sys.argv[4], "--run-config", sys.argv[5], "--output-dir", sys.argv[6]]
if sys.argv[7] == "yes":
    command.append("--synthetic-fail")
print(json.dumps(command))
PY
}

RUN1="$(init_run "$OUT/input_v1" "$EX/item_bank_v1.json" "$OUT/run1_early_result.json")"
CMD1="$(make_command "$RUN1" "$OUT/input_v1" "$EX/item_bank_v1.json" no)"
"$PYTHON" "$ROOT/scripts/run_command.py" --run-dir "$RUN1" --cwd "$ROOT" \
  --command-json "$CMD1" --timeout-seconds 20 \
  --expected-output selection.json --expected-output scores.json --expected-output errors.json

RUN2="$(init_run "$OUT/input_v1" "$EX/item_bank_v1.json" "$OUT/run2_early_result.json")"
CMD2="$(make_command "$RUN2" "$OUT/input_v1" "$EX/item_bank_v1.json" no)"
"$PYTHON" "$ROOT/scripts/run_command.py" --run-dir "$RUN2" --cwd "$ROOT" \
  --command-json "$CMD2" --timeout-seconds 20 \
  --expected-output selection.json --expected-output scores.json --expected-output errors.json

"$PYTHON" "$ROOT/scripts/compare_runs.py" \
  --run-a "$RUN1" --run-b "$RUN2" --item-bank "$EX/item_bank_v1.json" \
  --output "$OUT/comparison.json"

"$PYTHON" "$ROOT/scripts/impact.py" \
  --old-bank "$EX/item_bank_v1.json" --new-bank "$EX/item_bank_v2.json" \
  --old-materials "$OUT/input_v1/materials" --new-materials "$OUT/input_v2/materials" \
  --old-run "$RUN1" --output "$OUT/impact.json"

RUN3="$(init_run "$OUT/input_v2" "$EX/item_bank_v2.json" "$OUT/run3_early_result.json")"
CMD3="$("$PYTHON" - "$PYTHON" "$EX/scorer.py" "$EX/item_bank_v2.json" "$OUT/input_v2/materials" "$RUN3/run_config.json" "$RUN3" "$OUT/impact.json" <<'PY'
import json, sys
command = [sys.argv[1], sys.argv[2], "--item-bank", sys.argv[3], "--materials", sys.argv[4], "--run-config", sys.argv[5], "--output-dir", sys.argv[6]]
impact = json.load(open(sys.argv[7], encoding="utf-8"))
for item_id in impact["recompute_item_ids"]:
    command.extend(["--only", item_id])
print(json.dumps(command))
PY
)"
"$PYTHON" "$ROOT/scripts/run_command.py" --run-dir "$RUN3" --cwd "$ROOT" \
  --command-json "$CMD3" --timeout-seconds 20 \
  --expected-output selection.json --expected-output scores.json --expected-output errors.json

"$PYTHON" "$ROOT/scripts/finalize.py" \
  --case "$OUT/input_v1/case.json" --item-bank "$EX/item_bank_v1.json" \
  --run-dir "$RUN1" --comparison "$OUT/comparison.json" --impact "$OUT/impact.json" \
  --selective-run "$RUN3" --output "$OUT/result.json"

# Negative: the real scorer deliberately returns 3. run_command must fail and can never write STABLE.
NEG_RUN="$(init_run "$OUT/input_v1" "$EX/item_bank_v1.json" "$OUT/negative_early_result.json")"
NEG_CMD="$(make_command "$NEG_RUN" "$OUT/input_v1" "$EX/item_bank_v1.json" yes)"
if "$PYTHON" "$ROOT/scripts/run_command.py" --run-dir "$NEG_RUN" --cwd "$ROOT" \
  --command-json "$NEG_CMD" --timeout-seconds 20 \
  --expected-output selection.json --expected-output scores.json --expected-output errors.json; then
  echo "NEGATIVE CASE ERROR: nonzero scorer unexpectedly passed" >&2
  exit 1
else
  negative_code=$?
  echo "Expected negative run_command exit_code=$negative_code"
fi
if "$PYTHON" "$ROOT/scripts/finalize.py" \
  --case "$OUT/input_v1/case.json" --item-bank "$EX/item_bank_v1.json" \
  --run-dir "$NEG_RUN" --output "$OUT/negative_result.json"; then
  echo "NEGATIVE CASE ERROR: failed run finalized as success" >&2
  exit 1
else
  echo "Expected negative finalize rejected SUCCESS"
fi

"$PYTHON" "$ROOT/examples/contract_regression.py" \
  --work-dir "$OUT/contract-regression" --run-dir "$RUN1" \
  --item-bank "$EX/item_bank_v1.json" --comparison "$OUT/comparison.json" \
  --impact "$OUT/impact.json" --selective-run "$RUN3"

"$PYTHON" - "$OUT" "$RUN1" "$RUN2" "$RUN3" "$NEG_RUN" "$ROOT" <<'PY'
import json, pathlib, sys
sys.dont_write_bytecode = True
out = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[6])
sys.path.insert(0, str(root / "scripts"))
from common import canonical_bytes, output_fields, read_json, sha256_bytes
from compare_runs import canonicalize, validate_run
result = json.loads((out / "result.json").read_text())
case = json.loads((out / "input_v1/case.json").read_text())
required = set(output_fields(case))
assert required == set(result), (required, set(result))
assert result["case_id"] == case["case_id"]
assert result["status"] == "SUCCESS" and result["success"] is True
assert len(result["items"]) == 4
assert all(item["score"] == 2 and item["max_score"] == 2 for item in result["items"])
assert all(set(item["component_scores"]) == {"calculation", "final_answer"} for item in result["items"])
assert all(item["task"] and item["reference_answer"] and item["rubric"] and item["evidence"] for item in result["items"])
assert all(item["raw_answer"] == item["raw_output"]["answer"] for item in result["items"])
assert sum(item["score"] for item in result["items"]) == 8
assert result["summary"]["score_total"] == 8 and result["summary"]["score_max"] == 8
comparison = json.loads((out / "comparison.json").read_text())
assert comparison["semantic_equal"] is True and comparison["errors_equal"] is True
assert comparison["scientific_correctness"] == "NOT_ESTABLISHED_BY_HASH_EQUALITY"
bank = read_json(root / "examples/synthetic/item_bank_v1.json")
for run_argument, hash_field in [(sys.argv[2], "semantic_hash_a"), (sys.argv[3], "semantic_hash_b")]:
    data = validate_run(pathlib.Path(run_argument), bank)
    semantic = canonicalize({
        "raw_outputs": data["raw_outputs"],
        "scores": data["scores"],
        "selection": data["selection"],
        "item_bank_sha256": data["item_bank_sha256"],
    })
    fresh_hash = sha256_bytes(canonical_bytes(semantic))
    assert comparison[hash_field] == fresh_hash
assert comparison["semantic_hash_a"] == comparison["semantic_hash_b"]
impact = json.loads((out / "impact.json").read_text())
assert impact["recompute_item_ids"] == ["SYNTH-DRAFT-002", "SYNTH-DRAFT-003", "SYNTH-DRAFT-004"]
assert [row["item_id"] for row in impact["unaffected_scores"]] == ["SYNTH-DRAFT-001"]
selection = json.loads((pathlib.Path(sys.argv[4]) / "selection.json").read_text())
assert selection["mode"] == "selective_recomputation" and selection["selected_count"] == 3
assert selection["unaffected_item_ids_not_recomputed"] == ["SYNTH-DRAFT-001"]
negative = json.loads((pathlib.Path(sys.argv[5]) / "execution.json").read_text())
assert negative["status"] == "FAILED" and negative["success"] is False
assert negative["exit_code"] != 0
negative_result = json.loads((out / "negative_result.json").read_text())
assert negative_result["status"] == "PARTIAL" and negative_result["success"] is False
for run in sys.argv[2:6]:
    run_path = pathlib.Path(run)
    for name in ["manifest.json", "run_config.json", "command_record.json", "execution.json"]:
        path = run_path / name
        assert path.stat().st_mode & 0o222 == 0, f"mutable audit record: {path}"
print("SYNTHETIC END-TO-END ASSERTIONS PASSED")
PY

printf 'OUTPUT_DIR=%s\nRESULT=%s\nCOMPARISON=%s\nIMPACT=%s\nNEGATIVE_RESULT=%s\n' \
  "$OUT" "$OUT/result.json" "$OUT/comparison.json" "$OUT/impact.json" "$OUT/negative_result.json"
