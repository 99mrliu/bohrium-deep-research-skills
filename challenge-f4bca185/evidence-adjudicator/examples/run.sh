#!/usr/bin/env bash
# SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$HERE/.." && pwd)"
WORK="$HERE/synthetic-output/.work"
trap 'rmdir "$WORK" 2>/dev/null || true' EXIT
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/evidence_adjudicator.py" \
  --input "$HERE/synthetic-input" \
  --work "$WORK" \
  --output "$HERE/synthetic-output"
