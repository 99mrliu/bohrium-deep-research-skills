#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  printf 'usage: %s OUTPUT_DIR WORK_DIR\n' "$0" >&2
  printf 'Both directories must be writable; all intermediate work stays in WORK_DIR.\n' >&2
  exit 64
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/../scripts/oracle_lab.py" run \
  --spec "$SCRIPT_DIR/spec.json" \
  --output-dir "$1" \
  --work-dir "$2"
