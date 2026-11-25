#!/bin/sh
# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE: integration and determinism self-check.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
EXAMPLES="$ROOT/examples"
INPUT="$EXAMPLES/synthetic-input"
OUTPUT="$EXAMPLES/synthetic-output"
CONFLICT_OUTPUT="$EXAMPLES/synthetic-conflict-output"
WORK="$EXAMPLES/.runtime-work"

cleanup_work() {
  case "$WORK" in
    "$ROOT/examples/.runtime-work") rm -rf -- "$WORK" ;;
    *) printf '%s\n' 'Refusing unexpected work path' >&2; exit 90 ;;
  esac
}
trap cleanup_work EXIT HUP INT TERM
cleanup_work
mkdir -p -- "$WORK/main" "$WORK/no-data"

printf '%s\n' 'SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE'
printf '%s\n' '== standard-library unit self-tests =='
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/test_rule_spec_compiler.py"

printf '%s\n' '== first full success run =='
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/rule_spec_compiler.py" \
  --input "$INPUT" --work "$WORK/main" --output "$OUTPUT"
cp -R -- "$OUTPUT" "$WORK/first-output"

printf '%s\n' '== independent deterministic rerun =='
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/rule_spec_compiler.py" \
  --input "$INPUT" --work "$WORK/main" --output "$OUTPUT"
PYTHONDONTWRITEBYTECODE=1 python3 - "$WORK/first-output" "$OUTPUT" <<'PY'
import hashlib
from pathlib import Path
import sys
left, right = Path(sys.argv[1]), Path(sys.argv[2])
left_files = sorted(p.name for p in left.iterdir() if p.is_file())
right_files = sorted(p.name for p in right.iterdir() if p.is_file())
assert left_files == right_files, (left_files, right_files)
for name in left_files:
    a, b = (left / name).read_bytes(), (right / name).read_bytes()
    assert a == b, f"determinism mismatch: {name}"
    print("DETERMINISTIC", name, hashlib.sha256(a).hexdigest())
print("DETERMINISM_OK", len(left_files), "artifacts")
PY

printf '%s\n' '== incompatible-rule partial run (expected exit 0) =='
set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/rule_spec_compiler.py" \
  --input "$INPUT" --work "$WORK/conflict" --output "$CONFLICT_OUTPUT" \
  --config "$INPUT/conflict-override.json"
CONFLICT_CODE=$?
set -e
printf 'CONFLICT_EXIT=%s\n' "$CONFLICT_CODE"
test "$CONFLICT_CODE" -eq 0

printf '%s\n' '== unresolved required contract field (expected exit 0 and null) =='
set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/rule_spec_compiler.py" \
  --input "$INPUT" --work "$WORK/unresolved" --output "$WORK/unresolved-output" \
  --config "$INPUT/unresolved-override.json"
UNRESOLVED_CODE=$?
set -e
printf 'UNRESOLVED_EXIT=%s\n' "$UNRESOLVED_CODE"
test "$UNRESOLVED_CODE" -eq 0

printf '%s\n' '== no-data conflict input-error run (expected exit 2) =='
set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/rule_spec_compiler.py" \
  --input "$WORK/no-data" --case "$INPUT/case.json" --task "$INPUT/task.md" \
  --rules "$INPUT/rules.json" --config "$INPUT/conflict-override.json" \
  --work "$WORK/failure" --output "$WORK/failure-output"
FAILURE_CODE=$?
set -e
printf 'FAILURE_EXIT=%s\n' "$FAILURE_CODE"
test "$FAILURE_CODE" -eq 2

PYTHONDONTWRITEBYTECODE=1 python3 - "$OUTPUT" "$CONFLICT_OUTPUT" "$WORK/failure-output" "$WORK/unresolved-output" <<'PY'
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
success, conflict, failure, unresolved = map(Path, sys.argv[1:])
required = {"cleaned.csv", "cleaned.json", "execution_plan.json", "changes.jsonl",
            "review_queue.csv", "audit.md", "result.json", "statistics.csv"}
for directory, expected in ((success, "success"), (conflict, "partial"), (failure, "input_error")):
    names = {p.name for p in directory.iterdir() if p.is_file()}
    assert required <= names, (directory, required - names)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == expected, result["status"]
    for key in ("case_id", "status", "sources", "uncertainty", "change_records",
                "change_log", "review_queue", "artifacts", "official_note"):
        assert key in result, (directory, key)
    assert result["official_note"] is None
    for name in required:
        if name == "changes.jsonl" and not (directory / name).read_text(encoding="utf-8"):
            continue
        if expected == "input_error" and name in {"cleaned.csv", "cleaned.json", "changes.jsonl"}:
            continue
        text = (directory / name).read_text(encoding="utf-8")
        assert "SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE" in text, (directory, name)
    plan = json.loads((directory / "execution_plan.json").read_text(encoding="utf-8"))
    claimed = plan.pop("plan_sha256")
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert hashlib.sha256(raw.encode()).hexdigest() == claimed
    for obj in (result, plan):
        stack = [obj]
        while stack:
            value = stack.pop()
            if isinstance(value, dict): stack.extend(value.values())
            elif isinstance(value, list): stack.extend(value)
            elif isinstance(value, float): assert math.isfinite(value)

with (success / "cleaned.csv").open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
assert len(rows) == 4
assert [r["dose_g"] for r in rows] == ["1250", "500", "", "2000000"]
assert [r["yield"] for r in rows] == ["1250", "92.5", "88", "75.25"]
assert rows[1]["note"] == "" and rows[2]["note"] == ""
assert rows[0]["observed_range"] == "10..20"
conflict_result = json.loads((conflict / "result.json").read_text(encoding="utf-8"))
assert any(q["code"] == "RULE_CONFLICT" for q in conflict_result["review_queue"])
conflict_plan = json.loads((conflict / "execution_plan.json").read_text(encoding="utf-8"))
held = [r for r in conflict_plan["rules"] if r.get("field") == "yield"]
assert len(held) == 2 and all(not r["enabled"] for r in held)
with (conflict / "cleaned.csv").open(newline="", encoding="utf-8") as handle:
    conflict_rows = list(csv.DictReader(handle))
assert conflict_rows[0]["yield"] == "1,250" and conflict_rows[2]["yield"] == "88.0"
failure_result = json.loads((failure / "result.json").read_text(encoding="utf-8"))
assert any(q["code"] == "RULE_CONFLICT" for q in failure_result["review_queue"])
assert failure_result["statistics"]["output_rows"] == 0
unresolved_result = json.loads((unresolved / "result.json").read_text(encoding="utf-8"))
assert unresolved_result["status"] == "partial"
assert "unavailable_evidence" in unresolved_result and unresolved_result["unavailable_evidence"] is None
assert unresolved_result["unresolved_fields"] == ["unavailable_evidence"]
print("INTEGRATION_ASSERTIONS_OK success/conflict-hold/failure/contract-null/plan-digest/markers/finite-values")
PY
printf '%s\n' 'ALL_SYNTHETIC_CHECKS_PASSED'
