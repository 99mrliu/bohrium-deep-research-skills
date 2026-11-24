#!/bin/sh
# run.sh -- end-to-end demo of genre-register-polish on a SYNTHETIC example.
# Flow: detect -> lint(before) -> prepare -> apply-edits -> export ->
#       lint(after) -> scorecard gate -> result-skeleton -> validate-result
# Relative paths only; no network; python3 standard library only.
set -eu
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
SCRIPTS=../../scripts

rm -rf out .work
mkdir -p out .work

echo "== 1. genre detection (task declaration + text signals) =="
$PY $SCRIPTS/register.py detect --task task.md --text source-zh-grant.txt --out .work/genre-zh.json
$PY $SCRIPTS/register.py detect --task task.md --text source-en-abstract.txt --out .work/genre-en.json
$PY - <<'EOF'
import json
for f, exp in [(".work/genre-zh.json", "grant-proposal"),
               (".work/genre-en.json", "en-abstract")]:
    g = json.load(open(f, encoding="utf-8"))
    assert g["genre"] == exp and not g["needs_confirmation"], (f, g["genre"])
print("genres confirmed: grant-proposal, en-abstract")
EOF

echo "== 2. register lint BEFORE =="
$PY $SCRIPTS/register.py lint --text source-zh-grant.txt --genre grant-proposal --out .work/report-zh-before.json
$PY $SCRIPTS/register.py lint --text source-en-abstract.txt --genre en-abstract --out .work/report-en-before.json

echo "== 3. freeze sentence units =="
$PY $SCRIPTS/pipeline.py prepare --text source-zh-grant.txt --doc source-zh-grant --out .work/prepared-zh.json
$PY $SCRIPTS/pipeline.py prepare --text source-en-abstract.txt --doc source-en-abstract --out .work/prepared-en.json

echo "== 4. apply reviewed edit batches (edits.json = pre-recorded agent decisions) =="
$PY $SCRIPTS/pipeline.py apply-edits --prepared .work/prepared-zh.json --edits edits.json --doc source-zh-grant --out .work/applied-zh.json
$PY $SCRIPTS/pipeline.py apply-edits --prepared .work/prepared-en.json --edits edits.json --doc source-en-abstract --out .work/applied-en.json

echo "== 5. materialize polished texts for after-lint =="
$PY - <<'EOF'
import json
for doc in ("zh", "en"):
    a = json.load(open(".work/applied-%s.json" % doc, encoding="utf-8"))
    paras = {}
    for u in a["units"]:
        paras.setdefault(u["para"], []).append(u["final"] + u["sep_after"])
    text = "\n\n".join("".join(paras[p]).rstrip() for p in sorted(paras))
    open(".work/polished-%s.txt" % doc, "w", encoding="utf-8").write(text + "\n")
print("polished texts written")
EOF

echo "== 6. register lint AFTER + scorecard gate =="
$PY $SCRIPTS/register.py lint --text .work/polished-zh.txt --genre grant-proposal --out .work/report-zh-after.json
$PY $SCRIPTS/register.py lint --text .work/polished-en.txt --genre en-abstract --out .work/report-en-after.json
$PY $SCRIPTS/register.py scorecard --before .work/report-zh-before.json --after .work/report-zh-after.json --out .work/scorecard-zh.json --md .work/sc-zh.md
$PY $SCRIPTS/register.py scorecard --before .work/report-en-before.json --after .work/report-en-after.json --out .work/scorecard-en.json --md .work/sc-en.md

echo "== 7. export deliverables =="
$PY $SCRIPTS/pipeline.py export \
  --applied .work/applied-zh.json --applied .work/applied-en.json \
  --scorecard-md .work/sc-zh.md --scorecard-md .work/sc-en.md \
  --outdir out

echo "== 8. result skeleton -> fill -> validate =="
$PY $SCRIPTS/result.py result-skeleton --case case.json --out .work/skeleton.json
$PY - <<'EOF'
import json
case = json.load(open("case.json", encoding="utf-8"))
changes = json.load(open("out/changes.json", encoding="utf-8"))
applied = {d: json.load(open(".work/applied-%s.json" % d, encoding="utf-8"))
           for d in ("zh", "en")}

def polished(a):
    paras = {}
    for u in a["units"]:
        paras.setdefault(u["para"], []).append(u["final"] + u["sep_after"])
    return "\n\n".join("".join(paras[p]).rstrip() for p in sorted(paras))

flat_changes = []
for doc in changes["docs"]:
    for c in doc["applied"]:
        flat_changes.append(dict({"doc": doc["doc_id"]}, **c))
    for r in doc["reverted"]:
        flat_changes.append(dict({"doc": doc["doc_id"]}, **r))

register_report = {}
for key, tag in (("source-zh-grant", "zh"), ("source-en-abstract", "en")):
    genre = json.load(open(".work/genre-%s.json" % tag, encoding="utf-8"))
    before = json.load(open(".work/report-%s-before.json" % tag, encoding="utf-8"))
    after = json.load(open(".work/report-%s-after.json" % tag, encoding="utf-8"))
    sc = json.load(open(".work/scorecard-%s.json" % tag, encoding="utf-8"))
    register_report[key] = {
        "genre_detected": genre["genre"],
        "genre_evidence": "task declaration" if genre["declared_in_task"] else "text signals",
        "before": {"counts": before["counts"], "warnings": before["warning_count"],
                   "total_violations": before["total_violations"],
                   "violations": before["violations"]},
        "after": {"counts": after["counts"], "warnings": after["warning_count"],
                  "total_violations": after["total_violations"],
                  "violations": after["violations"]},
        "scorecard": {"delta_total": sc["delta_total"], "gate": sc["gate"]},
    }

result = {
    "case_id": case["case_id"],
    "status": "success",
    "sources": ["task.md", "source-zh-grant.txt", "source-en-abstract.txt"],
    "uncertainty": ("Synthetic example. Register lint is heuristic: hits were "
                    "adjudicated per references/register-taxonomy.md; the "
                    "scorecard proves violations did not increase, not that "
                    "the prose is optimal."),
    "notes": ("合成示例 / synthetic. Two deliberate reverts demonstrate the "
              "gates: one unreviewed edit (zh s0001), one edit losing "
              "protected tokens (en s0004)."),
    "polished_text": {k: polished(applied[t]) for k, t in
                      (("source-zh-grant", "zh"), ("source-en-abstract", "en"))},
    "changes": flat_changes,
    "register_report": register_report,
}
json.dump(result, open("out/result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
open("out/result.json", "a", encoding="utf-8").write("\n")
print("result.json filled")
EOF
$PY $SCRIPTS/result.py validate-result --case case.json --result out/result.json

echo "== 9. cleanup intermediates =="
rm -rf .work
echo "DONE -- see out/: polished.md changes.json audit.json register-scorecard.md result.json"
