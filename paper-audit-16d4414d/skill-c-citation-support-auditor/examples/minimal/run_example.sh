#!/bin/sh
# Minimal example for citation-support-auditor (SYNTHETIC EXAMPLE — not a real case).
# Planted defects: [3] cited but not listed; [4] listed but not cited;
# Wang et al. (2021) cited but missing; one over-strong claim behind [3].
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK="$HERE/outputs/work"
mkdir -p "$WORK"

echo "== 1. parse =="
python3 "$SKILL/scripts/citescan.py" parse --input "$HERE/inputs/synthetic_paper.txt" --work "$WORK" || exit 1

echo "== 2. reconcile (expect [3] + Wang 2021 cited-not-listed; [4] listed-not-cited) =="
python3 "$SKILL/scripts/citescan.py" reconcile --work "$WORK" || exit 1
python3 - "$WORK" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + "/reconcile.json"))
print(json.dumps(d, ensure_ascii=False, indent=1))
PY

echo "== 3. worksheet (expect strong-claim flag on the 'cures' sentence) =="
python3 "$SKILL/scripts/citescan.py" worksheet --work "$WORK" || exit 1
python3 - "$WORK" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + "/worksheet.json"))
print("citations:", d["citation_count"], "strong_claim:", d["strong_claim_citations"])
for r in d["worksheet"]:
    print(" -", r["sentence_id"], r["citation_raw"], r["function_guess"],
          "ref_found=%s" % r["reference_found"],
          "STRONG" if r["strong_claim_with_citation"] else "")
PY

echo "== 4. verify (expect exit 4: DEMO-BAD is not verbatim) =="
python3 "$SKILL/scripts/citescan.py" verify --work "$WORK" --findings "$HERE/inputs/demo_findings.json"
echo "verify exit code: $? (4 = violations found, as designed)"
