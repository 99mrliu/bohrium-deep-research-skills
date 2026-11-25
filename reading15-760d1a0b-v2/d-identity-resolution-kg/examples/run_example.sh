#!/bin/sh
# Run the SYNTHETIC end-to-end example (not real papers).
# Equivalent to: python3 scripts/run_minimal_example.py
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$HERE/../scripts/run_minimal_example.py"
