#!/usr/bin/env bash
# run_example.sh — end-to-end proof on the SYNTHETIC (合成) toy corpus.
#
# GOOD path: build_corpus -> term_cohorts (with synonyms.json)
#            -> phase_segment -> representative_select (multi-criteria)
#            must exit 0, recover the planted 3-phase segmentation
#            (2010-2015 / 2016-2020 / 2021-2024, tolerance +-1 year),
#            surface the foundation-model -> pretrained-language-model
#            drift, and select 2 auditable representatives per phase.
# BAD  path: representative_select --baseline top-citations mimics the
#            raw global citation top-N anti-pattern and MUST exit 1 with a
#            coverage violation (planted citations put the global top-N
#            entirely inside phase 2).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
SCRIPTS="$BUNDLE/scripts"
CASE="$HERE/synthetic_case"
OUT="$HERE/example_output"
GOOD="$OUT/good"
BAD="$OUT/bad"
WORK="$OUT/work"

rm -rf "$OUT"
mkdir -p "$GOOD" "$BAD" "$WORK"

echo "=== GOOD pipeline (multi-criteria) ==="
python3 "$SCRIPTS/build_corpus.py" --work "$WORK" --inputs "$CASE/corpus.jsonl"
python3 "$SCRIPTS/term_cohorts.py" --work "$WORK" --synonyms "$CASE/synonyms.json"
python3 "$SCRIPTS/phase_segment.py" --work "$WORK" --synonyms "$CASE/synonyms.json"
python3 "$SCRIPTS/representative_select.py" --work "$WORK" --per-phase 2
echo "GOOD: multi-criteria selection exited 0"

echo "=== verify GOOD artifacts ==="
python3 - "$WORK" <<'PY'
import json, sys
work = sys.argv[1]
ph = json.load(open(work + "/phases.json", encoding="utf-8"))
spans = [(p["start"], p["end"]) for p in ph["phases"]]
planted = [(2010, 2015), (2016, 2020), (2021, 2024)]
assert len(spans) == 3, "expected 3 phases, got %s" % (spans,)
for (s, e), (ps, pe) in zip(spans, planted):
    assert abs(s - ps) <= 1 and abs(e - pe) <= 1, \
        "phase %s-%s outside +-1y tolerance of planted %s-%s" % (s, e, ps, pe)
print("PROOF phases: detected %s vs planted %s (within +-1 year)"
      % (spans, planted))
print("  boundaries detected after years: %s"
      % ph["meta"]["boundaries_after_year"])

dr = json.load(open(work + "/drift_report.json", encoding="utf-8"))
v = dr["canonical_terms"]["pretrained language model"]["variants"]
plm = v.get("pretrained language model", {})
fm = v.get("foundation model", {})
assert sum(plm.values()) > 0 and sum(fm.values()) > 0, "drift variants missing"
assert max(map(int, plm)) < min(map(int, fm)), \
    "expected plm years before fm years, got %s vs %s" % (plm, fm)
print("PROOF drift: 'pretrained language model' %s -> renamed 'foundation model' %s; merged cohort %s (renaming, NOT a new topic)"
      % (plm, fm, dr["canonical_terms"]["pretrained language model"]["merged_cohort_year_counts"]))

rep = json.load(open(work + "/representatives.json", encoding="utf-8"))
from collections import Counter
sel = [c for c in rep["candidates"] if c["selected"]]
cnt = Counter(c["phase_id"] for c in sel)
for p in ph["phases"]:
    assert cnt.get(p["phase_id"], 0) == 2, \
        "phase %s has %s representatives" % (p["phase_id"], cnt.get(p["phase_id"], 0))
assert rep["coverage"]["coverage"] == 1.0, rep["coverage"]
print("PROOF representatives: %s; coverage %.3f; every row carries the full score table (citation_percentile/term_centrality/method_first_bonus/total)"
      % (dict(cnt), rep["coverage"]["coverage"]))
PY

cp "$WORK/canon.jsonl" "$WORK/term_year_matrix.json" "$WORK/year_vectors.json" \
   "$WORK/record_terms.json" "$WORK/top_terms.csv" "$WORK/phases.json" \
   "$WORK/drift_report.json" "$WORK/representatives.json" "$GOOD/"
echo "GOOD artifacts copied to $GOOD"

echo "=== BAD pipeline (anti-pattern baseline: raw citation top-N) ==="
set +e
python3 "$SCRIPTS/representative_select.py" --work "$WORK" --per-phase 2 \
    --baseline top-citations --out representatives_baseline.json \
    > "$BAD/baseline.log" 2>&1
rc=$?
set -e
cp "$WORK/representatives_baseline.json" "$BAD/"
if [ "$rc" -ne 1 ]; then
    echo "FAIL: baseline mode should exit 1 (coverage violation), got $rc"
    exit 1
fi
echo "PROOF baseline: exit code $rc (expected 1)"
grep -q "COVERAGE VIOLATION" "$BAD/baseline.log"
echo "PROOF baseline: $(grep 'COVERAGE VIOLATION' "$BAD/baseline.log")"
echo "PROOF baseline: $(grep 'coverage' "$BAD/baseline.log" | head -1)"
echo "BAD artifacts copied to $BAD"

echo "ALL CHECKS PASSED"
