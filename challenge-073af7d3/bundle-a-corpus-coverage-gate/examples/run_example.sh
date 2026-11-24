#!/usr/bin/env bash
# run_example.sh — 端到端自证脚本（合成数据，SYNTHETIC）。
# GOOD 运行：正常语料 → 去重 + 闭环成立 → 门禁 pass（exit 0）。
# BAD  运行：注入被篡改的台账（闭环数字不成立）→ 门禁 fail（exit 1）。
# 两个运行的真实工件分别复制到 example_output/good/ 与 example_output/bad/。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../scripts"
WORK_GOOD="$HERE/.work_good"
WORK_BAD="$HERE/.work_bad"
OUT="$HERE/example_output"

rm -rf "$WORK_GOOD" "$WORK_BAD" "$OUT"
mkdir -p "$WORK_GOOD" "$WORK_BAD" "$OUT/good" "$OUT/bad"

echo "================ GOOD RUN ================"
python3 "$SCRIPTS/ingest_corpus.py" --work "$WORK_GOOD" \
  --inputs "$HERE/synthetic_case/corpus.jsonl"

cov_good=0
python3 "$SCRIPTS/coverage_ledger.py" --work "$WORK_GOOD" || cov_good=$?
if [ "$cov_good" -ne 0 ]; then
  echo "ERROR good: coverage_ledger expected exit 0, got $cov_good" >&2
  exit 1
fi
echo "PROOF good: coverage_ledger exit 0 as expected (closure holds)"

if python3 "$SCRIPTS/gate_check.py" --work "$WORK_GOOD"; then
  echo "PROOF good: gate_check exit 0 as expected (gate=pass)"
else
  echo "ERROR good: gate_check expected exit 0" >&2
  exit 1
fi

cp "$WORK_GOOD/canon.jsonl" "$WORK_GOOD/duplicates.json" \
   "$WORK_GOOD/ingest_report.json" "$WORK_GOOD/coverage.json" \
   "$WORK_GOOD/gate_verdict.json" "$OUT/good/"
echo "PROOF good: artifacts copied to example_output/good/"

echo "================ BAD RUN ================"
python3 "$SCRIPTS/ingest_corpus.py" --work "$WORK_BAD" \
  --inputs "$HERE/synthetic_case/corpus.jsonl"

ledger_bad=0
python3 "$SCRIPTS/coverage_ledger.py" --work "$WORK_BAD" \
  --inject-ledger "$HERE/synthetic_case/tampered_ledger.json" || ledger_bad=$?
if [ "$ledger_bad" -ne 1 ]; then
  echo "ERROR bad: coverage_ledger expected exit 1, got $ledger_bad" >&2
  exit 1
fi
echo "PROOF bad: coverage_ledger exit 1 as expected (tampered closure broken)"

gate_bad=0
python3 "$SCRIPTS/gate_check.py" --work "$WORK_BAD" || gate_bad=$?
if [ "$gate_bad" -ne 1 ]; then
  echo "ERROR bad: gate_check expected exit 1, got $gate_bad" >&2
  exit 1
fi
echo "PROOF bad: gate_check exit 1 as expected (gate=fail, closure violation listed)"

cp "$WORK_BAD/coverage.json" "$WORK_BAD/gate_verdict.json" "$OUT/bad/"
echo "PROOF bad: artifacts copied to example_output/bad/"

rm -rf "$WORK_GOOD" "$WORK_BAD"
echo "================ ALL EXPECTATIONS MET ================"
