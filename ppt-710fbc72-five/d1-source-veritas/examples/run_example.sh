#!/usr/bin/env bash
# run_example.sh — end-to-end SYNTHETIC demo of source-veritas-deck.
# Everything runs inside a mktemp dir; NOTHING is written back into the bundle.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S="$(dirname "$HERE")"           # bundle root
EX="$(mktemp -d /tmp/source-veritas-demo.XXXXXX)"

echo "=== synthetic example workspace: $EX ==="
mkdir -p "$EX/input" "$EX/work" "$EX/output"

echo "--- 1/4 generate synthetic case ---"
python3 "$S/scripts/make_synthetic_case.py" --out "$EX/input"

echo "--- 2/4 prepare (build corpus ledger, partial-first result.json) ---"
python3 "$S/scripts/run_case.py" prepare \
    --input "$EX/input" --work "$EX/work" --output "$EX/output"

echo "--- 3/4 auto-fill slide plan from the corpus (non-interactive) ---"
python3 "$S/scripts/fill_example_plan.py" --work "$EX/work"

echo "--- 4/4 finish (fidelity gate -> build -> export -> QA -> result) ---"
python3 "$S/scripts/run_case.py" finish \
    --input "$EX/input" --work "$EX/work" --output "$EX/output"

echo
echo "=== artifacts (sha256) ==="
( cd "$EX/output" && find . -type f | sort | while read -r f; do
    printf "%s  %s\n" "$(shasum -a 256 "$f" | awk '{print $1}')" "$f"
  done )

echo
echo "=== result.json status ==="
python3 - "$EX/output/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print("status   :", r.get("status"))
print("case_id  :", r.get("case_id"))
print("summary  :", r.get("summary"))
print("artifacts:", len(r.get("artifacts", [])))
print("missing contract fields:",
      [f for f in ("case_id","status","summary","artifacts","evidence_map",
                   "sources","uncertainty","change_log") if f not in r])
PY

echo
echo "DONE. Inspect outputs under: $EX/output"
