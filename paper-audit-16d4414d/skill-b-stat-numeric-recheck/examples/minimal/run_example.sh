#!/bin/sh
# Minimal example for stat-numeric-recheck (SYNTHETIC EXAMPLE — not a real case).
# The synthetic paper plants six numeric defects; the engine must surface all
# six as candidates, and the verify gate must reject one non-verbatim quote.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK="$HERE/outputs/work"
mkdir -p "$WORK"

echo "== 1. scan =="
python3 "$SKILL/scripts/statscan.py" scan --input "$HERE/inputs/synthetic_paper.txt" --work "$WORK" || exit 1

echo "== 2. check (expect >=6 candidates: C1 x2, C2, C3, C4, C5, C6) =="
python3 "$SKILL/scripts/statscan.py" check --work "$WORK" || exit 1
python3 - "$WORK" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + "/candidates.json"))
print("rules hit:", json.dumps(d["rules"], ensure_ascii=False))
for c in d["candidates"]:
    print(" -", c["rule"], "|", c["sentence_id"], "|", c["deterministic_detail"][:90])
PY

echo "== 3. verify (expect exit 4: DEMO-BAD is not verbatim) =="
python3 "$SKILL/scripts/statscan.py" verify --work "$WORK" --findings "$HERE/inputs/demo_findings.json"
echo "verify exit code: $? (4 = violations found, as designed)"
echo
echo "Artifacts in $WORK:"
ls -1 "$WORK"
