#!/usr/bin/env bash
# SYNTHETIC example, not real papers.
# End-to-end demo of b-ontology-guard-kg using ONLY the bundle's own scripts.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 "$HERE/../scripts/run_minimal_example.py"
