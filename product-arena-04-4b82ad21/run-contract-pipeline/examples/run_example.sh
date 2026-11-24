#!/usr/bin/env bash
# run_example.sh -- miniature end-to-end run of the run-contract-pipeline skill
# against the bundled SYNTHETIC case. All content is invented; this demonstrates
# the interface only and is NOT a platform answer.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
CASE="$HERE/synthetic-case/case.json"
TASK="$HERE/synthetic-case/task.md"
FILLED="$HERE/synthetic-case/filled"
OUT="$HERE/sample-output"
WORK="$OUT/work"
FINAL="$OUT/output"

# Regenerate sample outputs from scratch so this script is idempotent.
rm -rf "$OUT"
mkdir -p "$WORK" "$FINAL"

echo "== stage 1: init_run =="
python3 "$SKILL_DIR/scripts/init_run.py" \
  --case "$CASE" --task "$TASK" --work "$WORK" --output "$FINAL"

echo
echo "== checkpoint: read =="
python3 "$SKILL_DIR/scripts/checkpoint.py" --work "$WORK" --stage read \
  --note "case.json, task.md and all declared material read; constraints extracted" \
  --snapshot "$CASE" --snapshot "$TASK"

# Stages 2-3 (scaffold/evidence, draft) are done by the agent, not by scripts.
# For this synthetic demo the draft and claim table are pre-authored under
# synthetic-case/filled/ and grounded only in the synthetic material.
echo
echo "== checkpoint: draft =="
python3 "$SKILL_DIR/scripts/checkpoint.py" --work "$WORK" --stage draft \
  --note "synthetic draft introduction.md + claims.json written and snapshotted" \
  --snapshot "$FILLED/introduction.md" --snapshot "$FILLED/claims.json"

echo
echo "== stage 5a: assemble_result (pass 1, verification not yet run) =="
python3 "$SKILL_DIR/scripts/assemble_result.py" \
  --case "$CASE" --work "$WORK" --output "$FINAL" \
  --draft "$FILLED/introduction.md" --claims "$FILLED/claims.json"

echo
echo "== stage 5b: contract_check (pass 1) =="
python3 "$SKILL_DIR/scripts/contract_check.py" \
  --case "$CASE" --result "$FINAL/result.json" \
  --draft "$FILLED/introduction.md" --out "$WORK/verification_report.json"

echo
echo "== stage 5c: assemble_result (pass 2, embedding the verification report) =="
python3 "$SKILL_DIR/scripts/assemble_result.py" \
  --case "$CASE" --work "$WORK" --output "$FINAL" \
  --draft "$FILLED/introduction.md" --claims "$FILLED/claims.json" \
  --verification "$WORK/verification_report.json"

echo
echo "== stage 5d: contract_check (final, on the delivered result.json) =="
python3 "$SKILL_DIR/scripts/contract_check.py" \
  --case "$CASE" --result "$FINAL/result.json" \
  --draft "$FILLED/introduction.md" --out "$FINAL/contract_report.json"

echo
echo "== resulting status =="
python3 - "$FINAL/result.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
print("status:", d["status"])
print("limits:", d["limits"])
print("contract fields present:", sorted(k for k in d if k != "limits"))
PY
