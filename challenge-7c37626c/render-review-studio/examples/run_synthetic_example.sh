#!/usr/bin/env bash
# Run the render-review-studio pipeline end-to-end on the SYNTHETIC fixture.
# All inputs and outputs are synthetic demonstrations of the interface.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
ROOT="${RR_RUN_ROOT:-/tmp/render-review-example}"
IN="$ROOT/input"
WORK="$ROOT/app/work"
OUT="$ROOT/app/output"
rm -rf "$ROOT"
mkdir -p "$IN/artifacts" "$WORK" "$OUT"
cp "$HERE/fixture/input/case.json" "$IN/case.json"

echo "== build a tiny synthetic source PDF at runtime (fixture ships no binary) =="
python3 - "$IN/artifacts/paper.pdf" <<'PY'
import sys
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
lines = ["Synthetic mobility note (fabricated)", "",
         "D = mu k_B T / q", "mu(E) = mu_0 exp(beta sqrt(E))"]
fig = plt.figure(figsize=(8.5, 4))
fig.text(0.08, 0.9, "\n".join(lines), va="top", fontsize=11, family="monospace")
with PdfPages(sys.argv[1]) as pdf:
    pdf.savefig(fig)
plt.close(fig)
print("synthetic PDF written")
PY

echo "== bootstrap =="
python3 "$BUNDLE/scripts/case_bootstrap.py" --input "$IN" --work "$WORK" --out "$OUT"

echo "== agent step: transcriptions + variable table (synthetic fixtures) =="
cp "$HERE/fixture/formulas.json" "$WORK/formulas.json"
cp "$HERE/fixture/variables.json" "$WORK/variables.json"

echo "== strict mathtext rendering =="
python3 "$BUNDLE/scripts/render_formula.py" --work "$WORK" --out "$OUT/render"

echo "== side-by-side comparison sheets =="
python3 "$BUNDLE/scripts/compare_sheet.py" --case "$IN/case.json" --input "$IN" --work "$WORK" --out "$OUT/render"

echo "== variable table rendering =="
python3 "$BUNDLE/scripts/table_render.py" --work "$WORK" --out "$OUT/render"

echo "== review pack with fail-closed completeness =="
python3 "$BUNDLE/scripts/review_pack.py" --work "$WORK" --out "$OUT"

echo "== verify result.json contract =="
python3 - "$OUT/result.json" "$IN/case.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
case = json.load(open(sys.argv[2]))
need = case["output_contract"]["required_fields"]
missing = [f for f in need if f not in r]
assert not missing, "missing fields: %s" % missing
assert r["status"] in case["output_contract"]["status_enum"]
rp = r["answers"]["review_pack"]
print("status=%s previews=%d unrenderable=%s" % (
    r["status"], len(rp["previews"]), [u["id"] for u in rp["unrenderable"]]))
PY
echo "outputs under $OUT"
