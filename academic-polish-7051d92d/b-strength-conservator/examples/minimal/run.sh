#!/bin/sh
# run.sh - end-to-end demo of strength-conserving-polish (SYNTHETIC example).
# Uses only relative paths; no network, no third-party packages.
set -eu
cd "$(dirname "$0")"
PY=python3
SCRIPTS=../../scripts

rm -rf out
mkdir -p out/.work

echo "== 1. prepare: freeze source.md into units =="
$PY "$SCRIPTS/pipeline.py" prepare --source source.md --work out/.work

echo "== 2. apply legal edits (grammar fixes, hedges untouched) =="
$PY "$SCRIPTS/pipeline.py" apply-edits --work out/.work --edits edits-good.json

echo "== 3. apply adversarial edits (expect gate reverts) =="
$PY "$SCRIPTS/pipeline.py" apply-edits --work out/.work --edits edits-adversarial.json

echo "== 4. export artifacts =="
$PY "$SCRIPTS/pipeline.py" export --work out/.work --outdir out

echo "== 5. result.json: skeleton -> fill -> validate =="
$PY "$SCRIPTS/result.py" result-skeleton --case case.json --out out/result.json
$PY "$SCRIPTS/result.py" fill --case case.json --result out/result.json \
    --polished out/polished.md --changes out/changes.json \
    --audit out/strength-audit.json --report out/conservation-report.md \
    --status success --sources source.md \
    --notes "SYNTHETIC example; strength cues are heuristic."
$PY "$SCRIPTS/result.py" validate-result --case case.json --result out/result.json

rm -rf out/.work
echo "OK: artifacts in out/ (polished.md changes.json strength-audit.json conservation-report.md result.json)"
