#!/bin/sh
# Minimal example for text-fidelity-gate (SYNTHETIC EXAMPLE — not a real case).
# Runs the full pipeline on a synthetic paper text and shows the gate and the
# verbatim quotecheck catching one fabricated quote. Safe to re-run.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK="$HERE/outputs/work"
mkdir -p "$WORK"

echo "== 1. extract (txt input; PDF works the same via pdftotext -layout) =="
python3 "$SKILL/scripts/fidelity.py" extract --input "$HERE/inputs/synthetic_paper.txt" --work "$WORK" || exit 1

echo "== 2. certificate (expect gate=degraded: abrupt_end truncation warning) =="
python3 "$SKILL/scripts/fidelity.py" certificate --work "$WORK"
GATE_RC=$?
echo "certificate exit code: $GATE_RC (2 = degraded, as designed for this input)"

echo "== 3. anchor (sentence ids S0001...) =="
python3 "$SKILL/scripts/fidelity.py" anchor --work "$WORK" || exit 1

echo "== 4. quotecheck (expect exit 4: DEMO-BAD is a fabricated quote) =="
python3 "$SKILL/scripts/fidelity.py" quotecheck --work "$WORK" --findings "$HERE/inputs/demo_findings.json"
QC_RC=$?
echo "quotecheck exit code: $QC_RC (4 = violations found, as designed)"

echo
echo "Artifacts written under $HERE/outputs/work/ :"
ls -1 "$WORK"
echo
echo "Expected: fidelity_certificate.json shows gate=degraded with abrupt_end"
echo "warning; quotecheck_problems.json lists DEMO-BAD only."
