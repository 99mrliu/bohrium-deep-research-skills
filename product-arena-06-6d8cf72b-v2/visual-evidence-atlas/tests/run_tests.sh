#!/usr/bin/env bash
# Offline, standard-library release regression suite.
set -euo pipefail
TEST_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s "$TEST_DIR" -p 'test_*.py' -v
