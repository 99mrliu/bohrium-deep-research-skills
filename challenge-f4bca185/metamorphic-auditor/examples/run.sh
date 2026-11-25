#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=${TMPDIR:-/tmp}/metamorphic-auditor-example-$$
mkdir -p "$TMP"
trap 'rm -rf "${TMP:?}"' EXIT HUP INT TERM
IN="$ROOT/examples/synthetic-input"
OUT="$TMP/generated"
WORK="$TMP/work"
SCRIPT="$ROOT/scripts/metamorphic_auditor.py"

printf '%s\n' 'SYNTHETIC_EXAMPLE_NOT_OFFICIAL_CASE: generate and independently verify'
python3 "$SCRIPT" --input "$IN" --work "$WORK" --output "$OUT"

python3 "$SCRIPT" --input "$IN" --work "$WORK" --output "$OUT" --verify-existing
mkdir "$TMP/first-snapshot"
cp "$OUT"/*.csv "$OUT"/*.json "$OUT"/*.jsonl "$OUT"/*.md "$TMP/first-snapshot/"
python3 "$SCRIPT" --input "$IN" --work "$WORK" --output "$OUT" --verify-existing
python3 - "$TMP/first-snapshot" "$OUT" <<'PY'
import hashlib, pathlib, sys
left, right = map(pathlib.Path, sys.argv[1:])
names = sorted(path.name for path in left.iterdir() if path.is_file())
for name in names:
    a = hashlib.sha256((left / name).read_bytes()).hexdigest()
    b = hashlib.sha256((right / name).read_bytes()).hexdigest()
    assert a == b, (name, a, b)
print("deterministic verify-existing rerun: byte-identical for", len(names), "artifacts")
PY

cp -R "$OUT" "$TMP/tampered"
python3 - "$TMP/tampered" <<'PY'
import csv, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
path = root / "cleaned.csv"
with path.open(encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fields, rows = reader.fieldnames, list(reader)
for row in rows:
    if row.get("_source_id", "").endswith("::row=4"):
        row["temp_K"] = "999"
with path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
path = root / "cleaned.json"
data = json.loads(path.read_text(encoding="utf-8"))
for row in data["cleaned"]:
    if row.get("_source_id", "").endswith("::row=4"):
        row["temp_K"] = "999"
path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
if python3 "$SCRIPT" --input "$IN" --work "$WORK" --output "$TMP/tampered" --verify-existing; then
    printf '%s\n' 'ERROR: tampered candidate unexpectedly passed' >&2
    exit 1
else
    code=$?
    test "$code" -eq 1
fi
python3 - "$TMP/tampered" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
result = json.loads((root / "result.json").read_text())
report = json.loads((root / "verification.json").read_text())
examples = [json.loads(x) for x in (root / "counterexamples.jsonl").read_text().splitlines() if x]
assert result["status"] == "partial" and result["verification_status"] == "fail"
assert report["counterexample_count"] > 0
assert {"raw_value_immutability", "unit_conversion_recomputation"} <= {x["check"] for x in examples}
print("tamper counterexamples:", report["counterexample_count"], "; nonzero verify confirmed")
PY

mkdir -p "$TMP/malformed-input/materials" "$TMP/missing-input/materials"
cp "$IN/materials/literature.csv" "$TMP/malformed-input/materials/literature.csv"
cp "$IN/materials/literature.csv" "$TMP/missing-input/materials/literature.csv"
printf '{bad json\n' > "$TMP/malformed-input/case.json"
if python3 "$SCRIPT" --input "$TMP/malformed-input" --work "$WORK" --output "$TMP/malformed-output"; then
    exit 1
else
    code=$?
    test "$code" -eq 2
fi
if python3 "$SCRIPT" --input "$TMP/missing-input" --work "$WORK" --output "$TMP/missing-output"; then
    exit 1
else
    code=$?
    test "$code" -eq 2
fi
python3 - "$TMP/malformed-output" "$TMP/missing-output" <<'PY'
import json, pathlib, sys
for arg in sys.argv[1:]:
    root = pathlib.Path(arg)
    result = json.loads((root / "result.json").read_text())
    assert result["status"] == "input_error" and result["verification_status"] == "fail"
    assert all((root / name).is_file() for name in (
        "cleaned.csv", "cleaned.json", "verification.json", "counterexamples.jsonl",
        "changes.jsonl", "review_queue.csv", "audit.md", "result.json"))
print("malformed and missing cases: input_error, complete reports, exit 2 confirmed")
PY
printf '%s\n' 'All synthetic positive, negative, determinism, and invalid-input tests passed.'
