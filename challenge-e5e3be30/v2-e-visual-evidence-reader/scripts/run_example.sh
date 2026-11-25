#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 1 ]]; then
  printf 'Usage: %s [OUTPUT_DIR]\n' "$0" >&2
  exit 64
fi
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [[ $# -eq 1 ]]; then
  OUTPUT_DIR="$1"
  mkdir -p -- "$OUTPUT_DIR"
else
  OUTPUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/visual-evidence-example.XXXXXX")"
fi
exec python3 "$SCRIPT_DIR/run_example.py" "$OUTPUT_DIR"
