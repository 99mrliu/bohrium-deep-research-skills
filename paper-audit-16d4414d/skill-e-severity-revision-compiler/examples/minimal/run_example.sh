#!/bin/sh
# Minimal example for severity-revision-compiler (SYNTHETIC EXAMPLE — not a real case).
# findings_bad.json plants exactly one vague revision ("建议补充论证") in F04.
# Step 1 must fail lint; step 2 repairs F04 on a copy; steps 3-5 pass.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK="$HERE/outputs/work"
OUT="$HERE/outputs/app_output"
mkdir -p "$WORK" "$OUT"
CR="python3 $SKILL/scripts/compile_report.py"

echo "== 1. lint on findings_bad.json (expect exit 7: F04 vague lexicon) =="
$CR lint --findings "$HERE/inputs/findings_bad.json" --work "$WORK"
echo "lint exit: $? (7 = violations, as designed)"

echo "== 2. repair F04 on a working copy (the only change) =="
python3 - "$HERE" "$WORK" <<'PY'
import json, sys
here, work = sys.argv[1], sys.argv[2]
fs = json.load(open(here + "/inputs/findings_bad.json"))
for f in fs:
    if f["id"] == "F04":
        f["revision"] = ("在 S0005 的 [1] 之外补引一篇 2019 年后的沙土-生物炭综述支撑该背景命题，"
                         "或将该句改写为不加引用的常识性表述。")
json.dump(fs, open(work + "/findings_fixed.json", "w"),
          ensure_ascii=False, indent=2)
print("repaired -> work/findings_fixed.json")
PY

echo "== 3. lint on repaired copy (expect pass) =="
$CR lint --findings "$WORK/findings_fixed.json" --work "$WORK" || exit 1

echo "== 4. priority queue =="
$CR priority --findings "$WORK/findings_fixed.json" || exit 1

echo "== 5. compile report.md + result_fields.json =="
$CR compile --findings "$WORK/findings_fixed.json" --work "$WORK" --out "$OUT" \
  --case "$HERE/inputs/synthetic_case.json" || exit 1

echo
echo "Artifacts: $OUT/report.md, $OUT/result_fields.json, $WORK/lint_report.json"
