#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
INPUT="$ROOT/examples/input"
WORK="$ROOT/examples/work"
OUTPUT="$ROOT/examples/output"
python3 "$ROOT/scripts/run_pipeline.py" --input-dir "$INPUT" --work-dir "$WORK" --output-dir "$OUTPUT"
test -s "$OUTPUT/comparison-matrix.md"
test -s "$OUTPUT/conflict-atlas.md"
test -s "$OUTPUT/result.json"
python3 - "$OUTPUT" <<'PY'
import json
import pathlib
import sys
out = pathlib.Path(sys.argv[1])
result = json.loads((out / "result.json").read_text(encoding="utf-8"))
assert result["case_id"] == "synthetic-conflict-mechanisms-001"
assert result["status"] == "success", result
atlas = (out / "conflict-atlas.md").read_text(encoding="utf-8")
assert "genuine_conflict" in atlas
assert "supported_by_direct_comparison" in atlas
assert "speculation" in atlas
print("Example assertions passed; no pooling and all three required outputs exist.")
PY
