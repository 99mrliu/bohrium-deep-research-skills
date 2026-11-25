#!/usr/bin/env bash
# SYNTHETIC EXAMPLE ONLY: run the independent tools without writing outputs into the bundle.
set -euo pipefail

if [ "$#" -gt 1 ]; then
  printf 'Usage: bash examples/synthetic/run_example.sh [caller_output_dir]\n' >&2
  exit 64
fi
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
BUNDLE_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)"
if [ "$#" -eq 1 ]; then
  mkdir -p -- "$1"
  OUT="$(CDPATH= cd -- "$1" && pwd -P)"
  case "$OUT" in
    "$BUNDLE_DIR"|"$BUNDLE_DIR"/*)
      printf 'Refusing to generate outputs inside the skill bundle: %s\n' "$OUT" >&2
      exit 64
      ;;
  esac
else
  OUT="$(mktemp -d "${TMPDIR:-/tmp}/construct-blueprint-forge.XXXXXX")"
fi

cd "$BUNDLE_DIR"
python3 scripts/blueprint.py examples/synthetic/blueprint.json \
  --case examples/synthetic/case.json --output "$OUT/blueprint_audit.json"
python3 scripts/item_audit.py examples/synthetic/item_bank.json \
  --blueprint examples/synthetic/blueprint.json --case examples/synthetic/case.json \
  --output "$OUT/item_audit.json"
python3 scripts/snapshot.py examples/synthetic/item_bank.json \
  --previous examples/synthetic/item_bank.previous.json \
  --output "$OUT/snapshot.json" --diff-output "$OUT/diff.json"
python3 scripts/finalize.py --case examples/synthetic/case.json \
  --blueprint examples/synthetic/blueprint.json --items examples/synthetic/item_bank.json \
  --output "$OUT/result.json"
python3 scripts/finalize.py --case examples/synthetic/case.json \
  --output "$OUT/early_partial.json" --partial-only --allow-partial

python3 - examples/synthetic/item_bank.json examples/synthetic/negative_leak.json \
  "$OUT/negative_item_bank.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    bank = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    fixture = json.load(handle)
matches = [item for item in bank["items"] if item["item_id"] == fixture["item_id"]]
assert len(matches) == 1
matches[0]["task"] += fixture["task_suffix"]
bank["label"] = "SYNTHETIC NEGATIVE OUTPUT ONLY — deliberately leaked answer"
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(bank, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
PY

set +e
python3 scripts/item_audit.py "$OUT/negative_item_bank.json" \
  --blueprint examples/synthetic/blueprint.json --case examples/synthetic/case.json \
  --output "$OUT/negative_item_audit.json"
NEGATIVE_RC=$?
set -e
if [ "$NEGATIVE_RC" -ne 2 ]; then
  printf 'Negative leak fixture returned %s; expected audit rejection 2.\n' "$NEGATIVE_RC" >&2
  exit 1
fi

python3 scripts/blueprint.py --skeleton "$OUT/blueprint_skeleton.json"
set +e
python3 scripts/blueprint.py "$OUT/blueprint_skeleton.json" \
  --output "$OUT/skeleton_audit.json"
SKELETON_RC=$?
set -e
if [ "$SKELETON_RC" -ne 2 ]; then
  printf 'Placeholder skeleton returned %s; expected audit rejection 2.\n' "$SKELETON_RC" >&2
  exit 1
fi

python3 - "$OUT" <<'PY'
import json
import pathlib
import re
import sys

out = pathlib.Path(sys.argv[1])
def load(name):
    with (out / name).open(encoding="utf-8") as handle:
        return json.load(handle)

blueprint_audit = load("blueprint_audit.json")
item_audit = load("item_audit.json")
snapshot = load("snapshot.json")
diff = load("diff.json")
result = load("result.json")
partial = load("early_partial.json")
negative = load("negative_item_audit.json")
skeleton_audit = load("skeleton_audit.json")
assert blueprint_audit["status"] == "pass", blueprint_audit["errors"]
assert item_audit["status"] == "pass", item_audit["errors"]
assert len(result["items"]) == 4
assert result["case_id"] == "synthetic-aster-construct-v1"
assert result["status"] == "success" and result["defects"] == []
for field in ("case_id", "items", "status", "sources", "uncertainty", "change_records", "defects"):
    assert field in result and field in partial
assert partial["status"] == "partial" and partial["items"] == []
assert re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot["content_address"])
assert snapshot["bank_sha256"] == snapshot["content_address"].split(":", 1)[1]
assert diff["answer_changed_item_ids"] == ["item-2"], diff
assert diff["rubric_changed_item_ids"] == ["item-2"], diff
assert diff["construct_comparable"] is True
assert diff["scoring_comparable"] is False
assert diff["comparability"] == "rescore_required"
assert any(error["code"] == "ANSWER_LEAKAGE" and error.get("item_id") == "item-4" for error in negative["errors"]), negative
assert any(error["code"] == "UNRESOLVED_PLACEHOLDER" for error in skeleton_audit["errors"]), skeleton_audit
print("Verified success, early partial, content-addressed answer/rubric diff, leaked-answer rejection and skeleton rejection.")
PY

printf 'OUTPUT_DIR=%s\n' "$OUT"
printf 'Generated JSON files:\n'
for name in blueprint_audit.json item_audit.json snapshot.json diff.json result.json early_partial.json negative_item_audit.json skeleton_audit.json; do
  printf '  %s\n' "$OUT/$name"
done
