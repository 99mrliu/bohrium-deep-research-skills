#!/bin/sh
# Minimal example for audit-process-qc (SYNTHETIC EXAMPLE — not a real case).
# Simulates one checkpointed audit session on a synthetic case.json, then a
# rerun-consistency check (DRIFT expected: F01 severity changed, F03 dropped,
# F04 added), then the finalize honesty gate.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK="$HERE/outputs/work"
OUT="$HERE/outputs/app_output"
mkdir -p "$WORK" "$OUT"
QC="python3 $SKILL/scripts/runqc.py"

echo "== 1. init: skeleton result.json from synthetic case.json =="
$QC init --work "$WORK" --output "$OUT" --case "$HERE/inputs/synthetic_case.json" || exit 1

echo "== 2. coverage ledger: six check items, one skipped with reason =="
$QC coverage --work "$WORK" --item fact_check --status examined || exit 1
$QC coverage --work "$WORK" --item citation_support --status examined || exit 1
$QC coverage --work "$WORK" --item method_design --status examined || exit 1
$QC coverage --work "$WORK" --item stats_report --status examined || exit 1
$QC coverage --work "$WORK" --item reasoning_chain --status examined || exit 1
$QC coverage --work "$WORK" --item academic_norm --status skipped --reason "扫描件末页参考文献区缺文本，规范项无法核对" || exit 1

echo "== 3. checkpoints: incremental honest saves =="
$QC checkpoint --work "$WORK" --output "$OUT" --stage findings-draft --note "2 confirmed, 1 needs_review" || exit 1
$QC checkpoint --work "$WORK" --output "$OUT" --stage fill-contract --field unchecked_items --value '[{"item":"academic_norm","reason":"扫描件末页参考文献区缺文本"}]' || exit 1
$QC checkpoint --work "$WORK" --output "$OUT" --stage set-status --field status --value '"partial"' || exit 1

echo "== 4. budget safety net at 41/64 (expect warn) =="
$QC budget --work "$WORK" --requests 41 || echo "budget exit: $? (non-zero warn/critical is by design)"

echo "== 5. rerun-consistency (expect DRIFT with 3 diffs) =="
$QC reruncheck --work "$WORK" --previous "$HERE/inputs/findings_run1.json" --current "$HERE/inputs/findings_run2.json" || exit 1

echo "== 6. finalize gate (expect PASS: partial is honest with open items) =="
$QC finalize --work "$WORK" --output "$OUT" || exit 1

echo "== 7. negative control: dishonest status must fail the gate =="
$QC checkpoint --work "$WORK" --output "$OUT" --stage sabotage --field status --value '"success"' || exit 1
$QC finalize --work "$WORK" --output "$OUT"
echo "finalize exit with dishonest status: $? (5 = gate refused, as designed)"
$QC checkpoint --work "$WORK" --output "$OUT" --stage restore --field status --value '"partial"' || exit 1

echo
echo "Artifacts: $OUT/result.json, $WORK/{journal.jsonl,coverage_ledger.json,budget.json,reruncheck.json,finalize_report.json}"
