#!/bin/sh
# Run the synthetic fixture, compare its deterministic summary, and test a bad result.
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /absolute/writable/verification-output" >&2
    exit 2
fi

OUT=$1
EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLE_DIR=$(CDPATH= cd -- "$EXAMPLE_DIR/.." && pwd)
mkdir -p "$OUT"

python3 "$BUNDLE_DIR/scripts/audit_dataset.py" \
    --manifest "$EXAMPLE_DIR/manifest.json" \
    --case "$EXAMPLE_DIR/case.json" \
    --task "$EXAMPLE_DIR/task.md" \
    --output-dir "$OUT"

python3 "$BUNDLE_DIR/scripts/check_result.py" \
    --case "$EXAMPLE_DIR/case.json" \
    --result "$OUT/result.json"

diff -u "$EXAMPLE_DIR/expected.txt" "$OUT/summary.txt"

python3 - "$EXAMPLE_DIR/case.json" "$OUT/result.json" "$OUT/negative_result.json" <<'PY'
import json
import sys
from pathlib import Path

case = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
result = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
fields = case["output_contract"]["required_fields"]
nested = {field: result.pop(field) for field in fields}
result["case_id"] = "structurally-wrong-case"
result["status"] = "success"
result["output_contract"] = {"required_fields": fields, "values": nested}
result.pop("sources", None)
Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

set +e
python3 "$BUNDLE_DIR/scripts/check_result.py" \
    --case "$EXAMPLE_DIR/case.json" \
    --result "$OUT/negative_result.json" \
    >"$OUT/negative_validation.log" 2>&1
NEGATIVE_STATUS=$?
set -e

if [ "$NEGATIVE_STATUS" -ne 2 ]; then
    echo "Negative result was not rejected with expected exit 2 (got $NEGATIVE_STATUS)" >&2
    exit 1
fi

python3 - "$OUT/negative_validation.log" <<'PY'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
for expected in ("case_id mismatch", "top-level output_contract", "missing top-level contract field"):
    if expected not in text:
        raise SystemExit(f"Negative validation log lacks {expected!r}")
PY

CONTRACT_TEST_LOG="$OUT/contract_shape_tests.log"
if ! python3 "$BUNDLE_DIR/examples/test_output_contracts.py" "$OUT/contract_shapes" \
    >"$CONTRACT_TEST_LOG" 2>&1; then
    cat "$CONTRACT_TEST_LOG" >&2
    exit 1
fi
cat "$CONTRACT_TEST_LOG"

echo "Expected summary matched; structural negative rejected with exit $NEGATIVE_STATUS."
echo "List/JSON Schema and other contract-shape tests passed; see $CONTRACT_TEST_LOG."
echo "Synthetic example only: no candidate methods were run; result status remains partial."
