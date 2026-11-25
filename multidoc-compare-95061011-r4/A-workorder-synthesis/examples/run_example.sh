#!/usr/bin/env bash
# SYNTHETIC minimal example only; contains no official case answers.
set -euo pipefail

EXAMPLES="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$(cd -- "${EXAMPLES}/.." && pwd)"
LABEL="SYNTHETIC MINIMAL EXAMPLE — NOT AN OFFICIAL CASE ANSWER"

python3 "${BUNDLE}/scripts/plan_workorder.py" \
  --case "${EXAMPLES}/input/case.json" \
  --task "${EXAMPLES}/input/task.md" \
  --workorder "${EXAMPLES}/input/comparison-workorder.json" \
  --output "${EXAMPLES}/synthetic-output/response-plan.json"

python3 "${BUNDLE}/scripts/assemble_response.py" \
  --case "${EXAMPLES}/input/case.json" \
  --workorder "${EXAMPLES}/input/comparison-workorder.json" \
  --response "${EXAMPLES}/agent-response.json" \
  --cells "${EXAMPLES}/common-cells.json" \
  --source-root "${EXAMPLES}" \
  --output-dir "${EXAMPLES}/synthetic-output" \
  --output-label "${LABEL}"

printf 'Synthetic outputs written to %s\n' "${EXAMPLES}/synthetic-output"
