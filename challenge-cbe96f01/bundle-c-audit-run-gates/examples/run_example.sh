#!/usr/bin/env bash
# SYNTHETIC EXAMPLE runner for audit-run-gates.
# Inputs under examples/synthetic_case/ are fabricated; outputs are
# illustrative, NOT formal case results.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
CK="$HERE/work/checkpoints"
OUT="$HERE/example_output"
rm -rf "$HERE/work" "$OUT"
mkdir -p "$CK/stage0" "$CK/stage0_replay" "$CK/stage3" "$CK/stage4" "$OUT"

echo "== stage 0: ingest + anchors (gate G0) =="
python3 "$SKILL_DIR/scripts/ingest.py" \
  "$HERE/synthetic_case/paper.txt" "$CK/stage0/pages.jsonl" || exit 1
python3 "$SKILL_DIR/scripts/anchor_index.py" \
  --pages "$CK/stage0/pages.jsonl" --out "$CK/stage0/anchors.json" || exit 1

echo "== stage 4: deterministic replay (gate G9) =="
python3 "$SKILL_DIR/scripts/ingest.py" \
  "$HERE/synthetic_case/paper.txt" "$CK/stage0_replay/pages.jsonl" || exit 1
python3 "$SKILL_DIR/scripts/anchor_index.py" \
  --pages "$CK/stage0_replay/pages.jsonl" \
  --out "$CK/stage0_replay/anchors.json" || exit 1
python3 "$SKILL_DIR/scripts/replay_diff.py" \
  --run "$CK/stage0" --rerun "$CK/stage0_replay" \
  --out "$CK/stage4/replay_report.json"
echo "replay exit=$? (0 expected)"

echo "== stage 3a: delivery gate on honest partial result (expect PASS) =="
python3 "$SKILL_DIR/scripts/gate_check.py" \
  --result "$HERE/synthetic_case/result_good.json" \
  --case "$HERE/synthetic_case/case.json" \
  --pages "$CK/stage0/pages.jsonl" \
  --log "$HERE/synthetic_case/run_log.jsonl" \
  --out "$CK/stage3/gate_report_good.json"
echo "gate exit=$? (0 expected)"

echo "== stage 3b: delivery gate on booby-trapped result (expect FAIL) =="
python3 "$SKILL_DIR/scripts/gate_check.py" \
  --result "$HERE/synthetic_case/result_bad.json" \
  --case "$HERE/synthetic_case/case.json" \
  --pages "$CK/stage0/pages.jsonl" \
  --log "$HERE/synthetic_case/run_log.jsonl" \
  --out "$CK/stage3/gate_report_bad.json"
echo "gate exit=$? (1 expected: G2/G5/G6/G7 violations planted)"

cp "$CK/stage0/anchors.json" "$CK/stage3/gate_report_good.json" \
   "$CK/stage3/gate_report_bad.json" "$CK/stage4/replay_report.json" "$OUT/"
echo "== done; inspect $OUT =="
exit 0
