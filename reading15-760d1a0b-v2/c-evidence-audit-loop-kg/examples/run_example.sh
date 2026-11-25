#!/bin/sh
# Run the SYNTHETIC end-to-end example (not real papers, not formal case answers).
set -e
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$SCRIPT_DIR/../scripts/run_minimal_example.py" --bundle "$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
