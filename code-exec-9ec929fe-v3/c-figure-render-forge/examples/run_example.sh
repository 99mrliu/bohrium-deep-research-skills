#!/usr/bin/env bash
# figure-render-forge synthetic demo. Works from any cwd.
# Steps: draft a plan (for show) -> render the curated plan -> qc -> manifest.
#
# Negative test (run manually): edit one n_plotted value in
#   examples/output_demo/figures_manifest.json
# then re-run the qc command below; it must print FAIL lines and exit 1.
# Restore the manifest (re-run render) afterwards.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CASE="${SCRIPT_DIR}/synthetic_case"
OUT="${SCRIPT_DIR}/output_demo"
PY="${PYTHON:-python3}"

mkdir -p "${OUT}"

echo "=== [1/3] plan (heuristic draft, for demonstration only) ==="
"${PY}" "${ROOT}/scripts/figforge.py" plan \
    --csv "${CASE}/concrete_like_syn.csv" \
    --dictionary "${CASE}/data_dictionary.json" \
    --out "${OUT}/draft_plan.json"
echo "draft plan exit=$?"

echo "=== [2/3] render (curated plan) ==="
"${PY}" "${ROOT}/scripts/figforge.py" render \
    --csv "${CASE}/concrete_like_syn.csv" \
    --dictionary "${CASE}/data_dictionary.json" \
    --plan "${CASE}/figure_plan.json" \
    --outdir "${OUT}"
render_rc=$?
echo "render exit=${render_rc}"

echo "=== [3/3] qc ==="
"${PY}" "${ROOT}/scripts/figforge.py" qc \
    --manifest "${OUT}/figures_manifest.json" \
    --csv "${CASE}/concrete_like_syn.csv" \
    --outdir "${OUT}"
qc_rc=$?
echo "qc exit=${qc_rc}"

echo "=== figures_manifest.json ==="
cat "${OUT}/figures_manifest.json"

echo "=== artifacts ==="
ls -la "${OUT}"

if [ "${render_rc}" -eq 0 ] && [ "${qc_rc}" -eq 0 ]; then
    echo "DEMO OK"
else
    echo "DEMO FAILED (render=${render_rc}, qc=${qc_rc})"
    exit 1
fi
