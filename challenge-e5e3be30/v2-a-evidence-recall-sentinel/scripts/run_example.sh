#!/usr/bin/env bash
# SYNTHETIC end-to-end executable demo, including a real expected-failure path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXAMPLE="$BUNDLE_DIR/examples/synthetic"
INPUT="$EXAMPLE/input"
GENERATED="$EXAMPLE/generated"
ENGINE="$BUNDLE_DIR/scripts/recall_sentinel.py"
REVIEWER="$EXAMPLE/synthetic_reviewer.py"

# The resolved target is fixed and checked before any removal.
case "$GENERATED" in
  "$EXAMPLE/generated") ;;
  *) printf 'Refusing unsafe output path\n' >&2; exit 2 ;;
esac
rm -rf -- "$GENERATED"
mkdir -p "$GENERATED/work" "$GENERATED/output"

printf '=== SYNTHETIC good case: prepare, review, finalize ===\n'
python3 "$ENGINE" prepare \
  --input "$INPUT" \
  --work "$GENERATED/work" \
  --output "$GENERATED/output/result.json" \
  --label "SYNTHETIC"
python3 "$REVIEWER" \
  --work "$GENERATED/work" \
  --output "$GENERATED/work/review.json"
python3 "$ENGINE" finalize \
  --case "$INPUT/case.json" \
  --work "$GENERATED/work" \
  --output "$GENERATED/output/result.json" \
  --review "$GENERATED/work/review.json"
python3 "$ENGINE" validate \
  --case "$INPUT/case.json" \
  --result "$GENERATED/output/result.json" \
  --work "$GENERATED/work"
python3 "$ENGINE" coverage-svg \
  --work "$GENERATED/work" \
  --output "$GENERATED/recall_coverage.svg" \
  --label "SYNTHETIC"
PYTHONDONTWRITEBYTECODE=1 python3 - "$GENERATED/output/result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
s1 = next(row for row in result["recall_coverage"]["claims"] if row["claim_id"] == "S1")
by_family = {row["family_id"]: row["candidate_count"] for row in s1["families"]}
assert by_family["S1-initial-narrow"] == 0, by_family
assert by_family["S1-synonym-table-recovery"] > 0, by_family
evidence = next(row for row in result["claim_results"] if row["claim_id"] == "S1")["evidence_candidate_ids"]
assert evidence, "Second-family candidate was not available for Agent review"
print("RECALL PROOF: initial family=0; second family>0; reviewed evidence exists")
PY

printf '\n=== SYNTHETIC bad case: one query family must fail with exit 1 ===\n'
BAD="$GENERATED/bad-tmp"
mkdir -p "$BAD/work" "$BAD/output"
python3 "$ENGINE" prepare \
  --input "$INPUT" \
  --claims "$EXAMPLE/bad-claims-missing-query-family.json" \
  --work "$BAD/work" \
  --output "$BAD/output/result.json" \
  --label "SYNTHETIC-BAD"
python3 "$REVIEWER" --work "$BAD/work" --output "$BAD/work/review.json"
set +e
python3 "$ENGINE" finalize \
  --case "$INPUT/case.json" \
  --work "$BAD/work" \
  --output "$BAD/output/result.json" \
  --review "$BAD/work/review.json" \
  >"$GENERATED/bad-validation.log" 2>&1
BAD_EXIT=$?
set -e
cp "$BAD/output/result.json" "$GENERATED/bad-result.json"
printf 'Observed bad-case finalize exit code: %s (required: 1)\n' "$BAD_EXIT" | tee -a "$GENERATED/bad-validation.log"
if [[ "$BAD_EXIT" -ne 1 ]]; then
  printf 'Bad case did not produce the expected validation exit 1\n' >&2
  exit 1
fi
rm -rf -- "$BAD"

printf '\nSYNTHETIC GOOD CASE PASSED; expected failure was captured as exit 1.\n'
printf 'Result: %s\n' "$GENERATED/output/result.json"
printf 'Recall SVG: %s\n' "$GENERATED/recall_coverage.svg"
printf 'Bad-case audit: %s\n' "$GENERATED/bad-validation.log"
