#!/usr/bin/env bash
# COMPLETE SYNTHETIC local example: no official case, answer key, or score.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(CDPATH= cd -- "$EXAMPLE_DIR/.." && pwd)
if [[ $# -gt 1 ]]; then
  printf 'usage: %s [caller-output-directory]\n' "$0" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  OUT=$1
else
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/source-atom-synthetic.XXXXXX")
fi
mkdir -p "$OUT/work" "$OUT/output"

PYTHON=${PYTHON:-python3}
SOURCE_MAP="$OUT/work/source_map.json"
VERDICT="$OUT/work/evidence_verdicts.json"
RESULT="$OUT/output/result.json"

"$PYTHON" "$SKILL_DIR/scripts/source_map.py" "$EXAMPLE_DIR/materials.json" --output "$SOURCE_MAP"
"$PYTHON" "$SKILL_DIR/scripts/evidence_gate.py" \
  --draft "$EXAMPLE_DIR/draft.json" \
  --source-map "$SOURCE_MAP" \
  --output "$VERDICT"
"$PYTHON" "$SKILL_DIR/scripts/finalize.py" \
  --case "$EXAMPLE_DIR/case.json" \
  --draft "$EXAMPLE_DIR/draft.json" \
  --source-map "$SOURCE_MAP" \
  --evidence-verdict "$VERDICT" \
  --result "$RESULT"

"$PYTHON" - "$EXAMPLE_DIR/draft.json" "$OUT/work" <<'PY'
import copy
import json
from pathlib import Path
import sys

source = Path(sys.argv[1])
work = Path(sys.argv[2])
draft = json.loads(source.read_text(encoding="utf-8"))
altered = copy.deepcopy(draft)
altered["Bank"][0]["evidence"]["atoms"][0]["evidence"]["quote"] += " during a second trial"
altered["notice"] = "SYNTHETIC NEGATIVE altered quote; rejection is mandatory."
(work / "negative_altered_quote_draft.json").write_text(
    json.dumps(altered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
missing = copy.deepcopy(draft)
del missing["Bank"][0]["evidence"]["atoms"][0]
missing["notice"] = "SYNTHETIC NEGATIVE missing atom; rejection is mandatory."
(work / "negative_missing_atom_draft.json").write_text(
    json.dumps(missing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY

expect_rejection() {
  local label=$1
  local draft_path=$2
  local expected_code=$3
  local negative_verdict="$OUT/work/negative_${label}_verdict.json"
  local log="$OUT/work/negative_${label}.log"
  set +e
  "$PYTHON" "$SKILL_DIR/scripts/evidence_gate.py" \
    --draft "$draft_path" --source-map "$SOURCE_MAP" --output "$negative_verdict" >"$log" 2>&1
  local rc=$?
  set -e
  if [[ $rc -ne 1 ]]; then
    printf 'NEGATIVE_CHECK_FAILED label=%s expected_exit=1 actual_exit=%s log=%s\n' "$label" "$rc" "$log" >&2
    return 1
  fi
  "$PYTHON" - "$negative_verdict" "$expected_code" <<'PY'
import json
import sys

verdict = json.load(open(sys.argv[1], encoding="utf-8"))
expected = sys.argv[2]
codes = []
codes.extend(error["code"] for error in verdict.get("errors", []))
for item in verdict.get("items", []):
    codes.extend(error["code"] for error in item.get("errors", []))
    for atom in item.get("atoms", []):
        codes.extend(error["code"] for error in atom.get("errors", []))
if verdict.get("ok") is not False or expected not in codes:
    raise SystemExit("negative verdict lacks expected rejection %s; codes=%r" % (expected, codes))
print("NEGATIVE_REJECTION_CONFIRMED code=%s" % expected)
PY
  printf 'NEGATIVE_OK label=%s exit=%s verdict=%s log=%s\n' "$label" "$rc" "$negative_verdict" "$log"
}

expect_rejection "altered_quote" "$OUT/work/negative_altered_quote_draft.json" "quote_not_in_declared_node"
expect_rejection "missing_atom" "$OUT/work/negative_missing_atom_draft.json" "uncovered_answer_element"

# A failed gate must not create a fresh complete result, even though partial export is separately available.
set +e
"$PYTHON" "$SKILL_DIR/scripts/finalize.py" \
  --case "$EXAMPLE_DIR/case.json" \
  --draft "$OUT/work/negative_altered_quote_draft.json" \
  --source-map "$SOURCE_MAP" \
  --evidence-verdict "$OUT/work/negative_altered_quote_verdict.json" \
  --result "$OUT/output/should_not_exist_result.json" >"$OUT/work/negative_finalize.log" 2>&1
NEGATIVE_FINALIZE_RC=$?
set -e
if [[ $NEGATIVE_FINALIZE_RC -ne 1 || -e "$OUT/output/should_not_exist_result.json" ]]; then
  printf 'NEGATIVE_FINALIZE_FAILED rc=%s unexpected output or exit\n' "$NEGATIVE_FINALIZE_RC" >&2
  exit 1
fi
printf 'NEGATIVE_FINALIZE_OK exit=%s no_result_created=true\n' "$NEGATIVE_FINALIZE_RC"

"$PYTHON" - "$RESULT" "$EXAMPLE_DIR/case.json" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
case = json.load(open(sys.argv[2], encoding="utf-8"))
assert result["case_id"] == case["case_id"]
assert result["status"] == "complete" and result["success"] is True
assert result.get("synthetic") is True and len(result["Bank"]) == 4
assert result["evidence_gate"]["ok"] is True
assert result["sources"] and all(len(item["sha256"]) == 64 for item in result["sources"])
assert "uncertainty" in result and "change_records" in result
print("SYNTHETIC_RESULT_CHECK_OK four_items=true source_hashes=true status=complete")
PY

printf '\nSYNTHETIC_EXAMPLE_COMPLETE output_dir=%s\n' "$OUT"
printf 'SOURCE_MAP=%s\nEVIDENCE_VERDICTS=%s\nRESULT_JSON=%s\n' "$SOURCE_MAP" "$VERDICT" "$RESULT"
printf 'All outcomes are synthetic technical checks, not DSH scores or independent semantic validation.\n'
