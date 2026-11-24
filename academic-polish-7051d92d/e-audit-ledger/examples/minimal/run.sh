#!/bin/sh
# run.sh -- end-to-end demo of the audit-trail-polish pipeline (SYNTHETIC EXAMPLE / 合成示例).
# Steps: prepare -> intake -> review -> export -> idempotence -> determinism (two full
# runs, diff must be empty) -> result-skeleton -> fill-result -> validate-result.
# Uses only relative paths and Python 3 standard library. No network.
set -eu
cd "$(dirname "$0")"
HERE=$PWD
SCRIPTS=../../scripts
JOB=$HERE/job
OUT=$HERE/out
JOB2=$HERE/job2
OUT2=$HERE/out2
rm -rf "$JOB" "$OUT" "$JOB2" "$OUT2"
mkdir -p "$JOB" "$OUT"

echo "== [0] extract frozen source text from case.json =="
python3 -c 'import json,sys; sys.stdout.write(json.load(open("case.json", encoding="utf-8"))["source_text"])' > "$JOB/source.txt"
cp "$JOB/source.txt" "$HERE/.source-copy"

run_pipeline () {  # $1=job dir  $2=out dir
  echo "== [1] prepare: freeze source into sentence units =="
  python3 "$SCRIPTS/ledger.py" prepare --source "$HERE/.source-copy" --job "$1"
  echo "== [2] intake: merge edit batches (one entry is deliberately vacuous and must be rejected) =="
  python3 "$SCRIPTS/ledger.py" intake --job "$1" --edits "$HERE/edits" --out "$1/intake-report.json"
  cp "$1/intake-report.json" "$2/intake-report.json"
  echo "== [3] build review records: every accepted edit EXCEPT the s0009 one =="
  echo "    (s0009 is deliberately left unreviewed to demonstrate mandatory rollback)"
  python3 - "$1/intake-report.json" "$1/review.json" <<'PY'
import json, sys
rep = json.load(open(sys.argv[1], encoding="utf-8"))
reviews = []
for e in rep["accepted"]:
    if e["sid"] == "s0009":
        continue  # deliberately unreviewed -> the review gate must roll it back
    reviews.append({
        "edit_id": e["edit_id"],
        "decision": "accept",
        "reason": "Re-read against the frozen sentence: the fix is correct, minimal, "
                  "and every protected token is preserved.",
    })
json.dump({"reviews": reviews}, open(sys.argv[2], "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, sort_keys=True)
open(sys.argv[2], "a", encoding="utf-8").write("\n")
PY
  echo "== [4] review: apply mandatory review gate =="
  python3 "$SCRIPTS/ledger.py" review --job "$1" --edits "$HERE/edits" --review "$1/review.json"
  echo "== [5] export: polished.md / changes.json / change-log.md / review.html =="
  python3 "$SCRIPTS/render.py" export --job "$1" --out "$2" --case-id MINIMAL-AUDIT-001
}

run_pipeline "$JOB" "$OUT"

echo "== [6] idempotence: polished text as new source must yield 0 mandatory changes =="
python3 "$SCRIPTS/render.py" idempotence --job "$JOB" --polished "$OUT/polished.md"

echo "== [7] determinism: full second run, then diff =="
mkdir -p "$JOB2" "$OUT2"
run_pipeline "$JOB2" "$OUT2"
if diff -r "$OUT" "$OUT2"; then
  echo "DETERMINISM: PASS (byte-identical outputs, diff empty)"
else
  echo "DETERMINISM: FAIL"; exit 1
fi

echo "== [8] result.json: skeleton -> fill -> validate =="
python3 "$SCRIPTS/result.py" result-skeleton --case case.json --out "$JOB/result-skeleton.json"
python3 "$SCRIPTS/result.py" fill-result --case case.json --artifacts "$OUT" --out "$OUT/result.json"
python3 "$SCRIPTS/result.py" validate-result --case case.json --result "$OUT/result.json"

rm -rf "$JOB" "$JOB2" "$OUT2" "$HERE/.source-copy"
echo "ALL STEPS PASSED -- deliverables in out/"
