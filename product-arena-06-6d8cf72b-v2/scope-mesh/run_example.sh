#!/bin/sh
# SYNTHETIC / 合成示例: regenerate only the fictional example outputs.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT=${1:-"$ROOT/examples/synthetic/output"}
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$OUT"
python3 "$ROOT/scripts/scope_mesh.py" validate-scope \
  --records "$ROOT/examples/synthetic/scope_records.json" \
  --source-root "$ROOT/examples/synthetic" \
  --output "$OUT/scope_validation.json"
python3 "$ROOT/scripts/build_example.py" \
  --example-dir "$ROOT/examples/synthetic" \
  --output-dir "$OUT"
printf '%s\n' "SYNTHETIC / 合成示例 outputs written to $OUT"
