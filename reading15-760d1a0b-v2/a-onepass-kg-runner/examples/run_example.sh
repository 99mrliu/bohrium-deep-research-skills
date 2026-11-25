#!/bin/sh
# Run the SYNTHETIC end-to-end example (input -> work -> output) with one command.
# SYNTHETIC example, not real papers.
set -e
cd "$(dirname "$0")/.."
exec python3 scripts/run_example.py "$@"
