#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
WORK="$ROOT/tests/negative-work"
mkdir -p "$WORK"
python3 - "$ROOT/examples/input/comparison-workorder.json" "$WORK/invalid-workorder.json" <<'PY'
import copy
import json
import pathlib
import sys
source = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
invalid = copy.deepcopy(source)
mechanism = next(item for item in invalid["mechanism_attributions"] if item["mechanism_id"] == "M-PORE-SPECULATION")
assert mechanism["status"] == "unresolved"
mechanism["status"] = "supported_by_direct_comparison"
pathlib.Path(sys.argv[2]).write_text(json.dumps(invalid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
if python3 "$ROOT/scripts/detect_attribution.py" --workorder "$WORK/invalid-workorder.json" >"$WORK/stdout.txt" 2>"$WORK/stderr.txt"; then
    echo "NEGATIVE TEST FAILED: speculation was accepted as supported" >&2
    exit 1
fi
grep -q "supported status has no direct comparison" "$WORK/stderr.txt"
grep -q "speculation A-E2 cannot establish supported mechanism" "$WORK/stderr.txt"
echo "Negative test passed: turning speculation into supported status fails attribution detection."
