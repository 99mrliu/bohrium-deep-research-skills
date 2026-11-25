#!/bin/sh
# SYNTHETIC runnable demonstration; never reads formal case data.
set -eu
EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(CDPATH= cd -- "$EXAMPLE_DIR/../.." && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_DIR/scripts/field_contract.py" init \
  --input-dir "$EXAMPLE_DIR/input" --work "$EXAMPLE_DIR/work" --output "$EXAMPLE_DIR/output"
PYTHONDONTWRITEBYTECODE=1 python3 "$SKILL_DIR/scripts/field_contract.py" finalize \
  --work "$EXAMPLE_DIR/work" --output "$EXAMPLE_DIR/output" \
  --source-register "$EXAMPLE_DIR/agent/source-register.json" \
  --decisions "$EXAMPLE_DIR/agent/decisions.json"
printf '%s\n' 'SYNTHETIC example complete: examples/minimal/output/result.json and contract-audit.md'
