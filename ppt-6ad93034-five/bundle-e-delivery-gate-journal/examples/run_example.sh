#!/usr/bin/env bash
# run_example.sh — end-to-end SYNTHETIC demo of the gated, journaled pipeline,
# including a deliberate tamper-detection negative demo (expected non-zero exits).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(dirname "$HERE")/scripts"
BASE="$HERE/work"
export CASE_INPUT_DIR="$BASE/input"
export CASE_WORK_DIR="$BASE/work"
export CASE_OUTPUT_DIR="$BASE/app-output"

echo "=== [0] fresh fixture ==="
rm -rf "$BASE"
mkdir -p "$CASE_INPUT_DIR" "$CASE_WORK_DIR" "$CASE_OUTPUT_DIR"
python3 "$HERE/make_fixture.py" "$BASE"

echo "=== [1] watchdog init (BEFORE any real work) ==="
python3 "$SCRIPTS/watchdog.py" init --case "$CASE_INPUT_DIR/case.json"
test -f "$CASE_OUTPUT_DIR/result.json"
python3 - <<'PY'
import json, os
r = json.load(open(os.path.join(os.environ["CASE_OUTPUT_DIR"], "result.json")))
assert r["status"] == "partial" and r["case_id"] == "synthetic-demo-005", r
assert r.get("synthetic_example") is True
print("ASSERT ok: result.json exists IMMEDIATELY with honest status=partial")
PY

echo "=== [2] journal init (hash inputs + record tool versions) ==="
cd "$BASE"   # journal log paths are recorded relative to $BASE so copies re-verify in place
python3 "$SCRIPTS/journal.py" init

echo "=== [3] extract paper text + journal the plan ==="
python3 "$SCRIPTS/pdf_text.py"
python3 "$SCRIPTS/journal.py" log --kind command \
  --cmd "agent wrote plan.json grounded in paper.txt (fixture-supplied plan)" \
  --inputs work/paper.txt --outputs work/plan.json \
  --note "plan written: 3 slides, evidence quotes from paper"
python3 "$SCRIPTS/gate.py" plan
python3 "$SCRIPTS/watchdog.py" advance --stage plan-gated

echo "=== [4] build the deck ==="
python3 "$SCRIPTS/mini_build.py"
python3 "$SCRIPTS/journal.py" log --kind command \
  --cmd "python3 mini_build.py" \
  --inputs work/plan.json --outputs app-output/presentation.pptx \
  --note "deck built from gated plan"
python3 "$SCRIPTS/gate.py" build
python3 "$SCRIPTS/watchdog.py" advance --stage build-gated \
  --set-json "editable_source=\"$CASE_OUTPUT_DIR/presentation.pptx\""

echo "=== [5] render/export (only if soffice exists) + render gate ==="
if command -v soffice >/dev/null 2>&1; then
  soffice --headless --convert-to pdf --outdir "$CASE_OUTPUT_DIR" "$CASE_OUTPUT_DIR/presentation.pptx"
  mkdir -p "$CASE_OUTPUT_DIR/previews"
  if command -v pdftoppm >/dev/null 2>&1; then
    pdftoppm -png -r 60 "$CASE_OUTPUT_DIR/presentation.pdf" "$CASE_OUTPUT_DIR/previews/slide"
  fi
  python3 "$SCRIPTS/journal.py" log --kind command --cmd "soffice --convert-to pdf" \
    --inputs app-output/presentation.pptx --outputs app-output/presentation.pdf \
    --note "PDF export + previews"
else
  echo "soffice absent: skipping PDF export (render gate will record renderer-absent honestly)"
fi
python3 "$SCRIPTS/gate.py" render
if [ -f "$CASE_OUTPUT_DIR/presentation.pdf" ]; then
  python3 "$SCRIPTS/watchdog.py" advance --stage render-gated \
    --set-json "export_artifact=\"$CASE_OUTPUT_DIR/presentation.pdf\""
else
  python3 "$SCRIPTS/watchdog.py" advance --stage render-gated \
    --exception "soffice unavailable: PDF export and previews not produced; deck delivered as .pptx only"
fi
echo "=== [6] delivery package: advance watchdog, ship journal copy, manifest + RUN_REPORT ==="
python3 "$SCRIPTS/watchdog.py" advance --stage delivery-packed \
  --set-json "content_map={\"deck\":\"$CASE_OUTPUT_DIR/presentation.pptx\"}" \
  --set-json 'compliance_checks=["gates-passed","journal-verified"]'
cp "$CASE_WORK_DIR/journal.jsonl" "$CASE_OUTPUT_DIR/journal.jsonl"
cp "$CASE_WORK_DIR"/gate-plan.json "$CASE_WORK_DIR"/gate-build.json "$CASE_WORK_DIR"/gate-render.json "$CASE_OUTPUT_DIR/"
python3 "$SCRIPTS/replay.py"
python3 "$SCRIPTS/replay.py" --check
python3 "$SCRIPTS/journal.py" verify

echo "=== [7] finalize, then refresh manifest so final result.json hash is captured ==="
python3 "$SCRIPTS/watchdog.py" finalize --status success
python3 "$SCRIPTS/replay.py"
python3 "$SCRIPTS/replay.py" --check

echo "=== [8] NEGATIVE DEMO (by design): flip one byte in a COPY, expect detection ==="
TAMPER="$BASE/tamper-demo"
mkdir -p "$TAMPER"
cp -R "$CASE_INPUT_DIR" "$TAMPER/input"
cp -R "$CASE_WORK_DIR" "$TAMPER/work"
cp -R "$CASE_OUTPUT_DIR" "$TAMPER/app-output"
python3 - "$TAMPER/app-output/presentation.pptx" <<'PY'
import sys
p = sys.argv[1]
b = bytearray(open(p, "rb").read())
b[100] ^= 0xFF  # flip a single byte
open(p, "wb").write(bytes(b))
print(f"flipped one byte in {p}")
PY
set +e
( cd "$TAMPER" && CASE_INPUT_DIR="$TAMPER/input" CASE_WORK_DIR="$TAMPER/work" CASE_OUTPUT_DIR="$TAMPER/app-output" \
    python3 "$SCRIPTS/journal.py" verify ) >"$TAMPER/journal-verify.out" 2>&1
rc_journal=$?
( cd "$TAMPER" && CASE_INPUT_DIR="$TAMPER/input" CASE_WORK_DIR="$TAMPER/work" CASE_OUTPUT_DIR="$TAMPER/app-output" \
    python3 "$SCRIPTS/replay.py" --check ) >"$TAMPER/replay-check.out" 2>&1
rc_replay=$?
set -e
grep -h -i "tamper" "$TAMPER/journal-verify.out" "$TAMPER/replay-check.out" | head -4
if [ "$rc_journal" -eq 0 ] || [ "$rc_replay" -eq 0 ]; then
  echo "NEGATIVE DEMO FAILED: tampering was NOT detected (journal=$rc_journal replay=$rc_replay)" >&2
  exit 1
fi
echo "NEGATIVE DEMO ok: journal verify exit=$rc_journal, replay --check exit=$rc_replay (both non-zero as designed)"
echo "originals untouched — re-checking original delivery:"
python3 "$SCRIPTS/replay.py" --check >/dev/null && echo "original delivery still verifies OK"

echo "=== [9] final artifacts ==="
ls -la "$CASE_OUTPUT_DIR"
echo "RUN EXAMPLE COMPLETE — exit 0"
