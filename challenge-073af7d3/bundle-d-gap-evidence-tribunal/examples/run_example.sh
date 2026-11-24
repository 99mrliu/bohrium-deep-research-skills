#!/usr/bin/env bash
# run_example.sh -- end-to-end proof for the synthetic case (all data synthetic).
# GOOD pipeline must exit 0 at every step; BAD pipeline steps must exit 1 with
# the expected violation codes. Artifacts are copied to example_output/.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SCRIPTS="$ROOT/scripts"
CASE="$HERE/synthetic_case"
OUT="$HERE/example_output"

rm -rf "$OUT"
mkdir -p "$OUT/good" "$OUT/bad"
WG="$(mktemp -d)"   # work dir for GOOD
WB="$(mktemp -d)"   # work dir for BAD
trap 'rm -rf "$WG" "$WB"' EXIT

assert_grep() {  # file, pattern, proof-label
  if grep -q "$2" "$1"; then
    echo "PROOF $3"
  else
    echo "MISSING PROOF: pattern '$2' not found in $1" >&2
    exit 3
  fi
}

run_bad() {  # name, cmd... : expect exit 1, capture stdout/stderr
  local name="$1"; shift
  set +e
  "$@" >"$OUT/bad/$name.stdout.txt" 2>&1
  local rc=$?
  set -e
  if [ "$rc" -ne 1 ]; then
    echo "FAIL: bad case '$name' expected exit 1, got $rc" >&2
    exit 2
  fi
  echo "PROOF bad $name exit=1 (as expected)"
}

echo "== GOOD pipeline =="
python3 "$SCRIPTS/build_corpus.py" --work "$WG" --inputs "$CASE/corpus.jsonl"
echo "PROOF good build_corpus exit=0"

python3 "$SCRIPTS/retrieval_log.py" --work "$WG" --log "$CASE/retrieval_log_good.jsonl"
echo "PROOF good retrieval_log exit=0"

python3 "$SCRIPTS/gap_tribunal.py" --work "$WG" --gaps "$CASE/gaps_good.json"
echo "PROOF good gap_tribunal exit=0"

python3 "$SCRIPTS/conflict_pairs.py" --work "$WG" --conflicts "$CASE/conflicts_good.json"
echo "PROOF good conflict_pairs exit=0"

cp "$WG/canon.jsonl" "$WG/retrieval_report.json" "$WG/gap_verdicts.json" \
   "$WG/conflict_report.json" "$OUT/good/"

assert_grep "$OUT/good/gap_verdicts.json" '"admissible"' "good gaps admissible"
assert_grep "$OUT/good/conflict_report.json" '"admissible"' "good conflicts admissible"
assert_grep "$OUT/good/retrieval_report.json" '"not_in_canon_external"' \
  "external ref flagged (non-fatal)"

echo "== BAD pipeline (every validator is expected to exit 1) =="
# Build canon + a VALID retrieval report in WB first, so that the bad gap run
# resolves q1/q2 and fires the planted gap violations (not unknown_query noise).
python3 "$SCRIPTS/build_corpus.py" --work "$WB" --inputs "$CASE/corpus.jsonl" >/dev/null
python3 "$SCRIPTS/retrieval_log.py" --work "$WB" --log "$CASE/retrieval_log_good.jsonl" >/dev/null

run_bad gap_bad python3 "$SCRIPTS/gap_tribunal.py" --work "$WB" --gaps "$CASE/gaps_bad.json"
cp "$WB/gap_verdicts.json" "$OUT/bad/gap_verdicts_bad.json"

run_bad conflict_bad python3 "$SCRIPTS/conflict_pairs.py" --work "$WB" --conflicts "$CASE/conflicts_bad.json"
cp "$WB/conflict_report.json" "$OUT/bad/conflict_report_bad.json"

run_bad retrieval_bad python3 "$SCRIPTS/retrieval_log.py" --work "$WB" --log "$CASE/retrieval_log_bad.jsonl"
cp "$WB/retrieval_report.json" "$OUT/bad/retrieval_report_bad.json"

assert_grep "$OUT/bad/retrieval_report_bad.json" '"closure_violation"' \
  "closure_violation fired"
assert_grep "$OUT/bad/gap_verdicts_bad.json" '"bare_gap_claim"' \
  "bare_gap_claim fired"
assert_grep "$OUT/bad/gap_verdicts_bad.json" '"irrelevant_near_miss"' \
  "irrelevant_near_miss fired"
assert_grep "$OUT/bad/gap_verdicts_bad.json" '"unknown_gap_type"' \
  "unknown_gap_type fired"
assert_grep "$OUT/bad/gap_verdicts_bad.json" '"unknown_query"' \
  "unknown_query fired"
assert_grep "$OUT/bad/conflict_report_bad.json" '"missing_side"' \
  "missing_side fired"
assert_grep "$OUT/bad/conflict_report_bad.json" '"not_a_conflict"' \
  "not_a_conflict fired"

echo "ALL PROOFS PASSED"
