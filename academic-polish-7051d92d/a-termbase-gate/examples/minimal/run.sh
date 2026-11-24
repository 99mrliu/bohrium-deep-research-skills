#!/bin/sh
# End-to-end run of the termbase-gated-polish pipeline on the SYNTHETIC
# minimal example. Uses only relative paths and Python 3 standard library.
# Expected to finish with exit code 0 and fresh artifacts in out/.
set -eu
cd "$(dirname "$0")"

BUNDLE=../..
WORK=.tmp-work
OUT=out
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "== [1/9] extract candidate terms from the draft =="
python3 "$BUNDLE/scripts/termbase.py" extract \
  --source source.md --out "$WORK/termbase-candidates.json"

echo "== [2/9] agent review: confirm/clean candidates (deterministic stand-in) =="
python3 - <<'PY'
import json
doc = json.load(open(".tmp-work/termbase-candidates.json", encoding="utf-8"))
# The agent reviews the mined candidates and confirms the real terms with
# cleaned canonical forms; noise (multiword phrases, GITT with unknown
# expansion) is deliberately not confirmed.
APPROVE = {
    "LIBs": ("Li-ion battery", "LIB"),
    "EIS": ("electrochemical impedance spectroscopy", "EIS"),
    "SEI": ("solid electrolyte interphase", "SEI"),
    "ALD": ("atomic layer deposition", "ALD"),
    "NCM811": ("LiNi0.8Co0.1Mn0.1O2", "NCM811"),
}
confirmed = []
for c in doc["candidates"]:
    if c["kind"] == "abbrev_pair" and c["abbrev"] in APPROVE:
        canonical, abbrev = APPROVE[c["abbrev"]]
        confirmed.append({
            "canonical": canonical,
            "abbrev": abbrev,
            "variants": [],
            "banned": [],
            "note": "confirmed from draft definition pair",
        })
json.dump({"confirmed": confirmed},
          open(".tmp-work/candidates.confirmed.json", "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("agent review: confirmed %d of %d candidates"
      % (len(confirmed), len(doc["candidates"])))
PY

echo "== [3/9] lock termbase (case glossary + confirmed candidates) =="
python3 - <<'PY'
import json
case = json.load(open("case.json", encoding="utf-8"))
json.dump(case["materials"]["glossary"],
          open(".tmp-work/glossary.json", "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
PY
python3 "$BUNDLE/scripts/termbase.py" lock \
  --candidates "$WORK/candidates.confirmed.json" \
  --glossary "$WORK/glossary.json" \
  --out "$OUT/termbase.json"

echo "== [3b] baseline lint of the untouched draft (expected to FAIL the gate) =="
if python3 "$BUNDLE/scripts/termbase.py" lint \
     --source source.md --termbase "$OUT/termbase.json" \
     --out "$WORK/term-lint-before.json"; then
  echo "UNEXPECTED: draft passed the terminology gate"
else
  echo "as expected: the raw draft fails the terminology gate (see findings below)"
  python3 - <<'PY'
import json
doc = json.load(open(".tmp-work/term-lint-before.json", encoding="utf-8"))
for f in doc["findings"]:
    loc = f["locations"][0]
    print("  %s [%s] %s @%s L%d: %s"
          % (f["id"], f["type"], f.get("surface") or "-",
             loc["section"], loc["line"], f["message"]))
PY
fi

echo "== [4/9] freeze the source into anchored units =="
python3 "$BUNDLE/scripts/pipeline.py" prepare \
  --source source.md --out "$WORK/units.json"

echo "== [5/9] agent writes one edit batch (pre-set real edits for this demo) =="
cat > "$WORK/edits.json" <<'JSON'
{
  "edits": [
    {
      "edit_id": "e0001",
      "unit": "u0001",
      "new_text": "# Interface Engineering of Li-ion Battery Cathodes via Al2O3 Coatings",
      "type": "terminology_unification",
      "reason": "Title uses 'Li-Ion' with wrong capitalization; glossary canonical form is 'Li-ion'.",
      "review": {"decision": "approve", "reason": "Matches glossary canonical casing; no meaning change."}
    },
    {
      "edit_id": "e0002",
      "unit": "u0003",
      "new_text": "Li-ion batteries (LIBs) are widely used in portable electronics and electric vehicles.",
      "type": "terminology_unification",
      "reason": "'Lithium-ion' is a banned variant; canonical short form 'Li-ion' must be used, keeping the (LIBs) definition.",
      "review": {"decision": "approve", "reason": "Fixes banned variant and preserves the first-use abbreviation definition."}
    },
    {
      "edit_id": "e0003",
      "unit": "u0005",
      "new_text": "Electrochemical impedance spectroscopy (EIS) has become a standard tool for probing interfacial resistance in Li-ion cells.",
      "type": "abbreviation_first_use",
      "reason": "EIS was used here before being defined in Methods; move the definition to first use and fix 'li-ion' casing in the same sentence.",
      "review": {"decision": "approve", "reason": "Satisfies define_at_first_use for EIS and unifies Li-ion casing; no data touched."}
    },
    {
      "edit_id": "e0004",
      "unit": "u0008",
      "new_text": "Li-ion coin cells were assembled with LiNi0.8Co0.1Mn0.1O2 (NCM811) cathodes.",
      "type": "terminology_unification",
      "reason": "'Li ion' misses the hyphen required by the glossary canonical form 'Li-ion'.",
      "review": {"decision": "approve", "reason": "Hyphenation fix only; formula and abbreviation untouched."}
    },
    {
      "edit_id": "e0005",
      "unit": "u0009",
      "new_text": "Al2O3 coatings were deposited by atomic layer deposition (ALD).",
      "type": "concision",
      "reason": "Streamline the sentence.",
      "review": {"decision": "approve", "reason": "Looks stylistically fine."}
    },
    {
      "edit_id": "e0006",
      "unit": "u0011",
      "new_text": "EIS data were collected from 100 kHz to 10 mHz with a perturbation amplitude of 5 mV.",
      "type": "abbreviation_first_use",
      "reason": "The full name is now defined at first use in the Introduction, so the abbreviation is used here; 'data were collected' also fixes the original collocation 'spectroscopy was collected'.",
      "review": {"decision": "approve", "reason": "Keeps every number and unit (100 kHz, 10 mHz, 5 mV) unchanged."}
    },
    {
      "edit_id": "e0007",
      "unit": "u0014",
      "new_text": "The solid electrolyte interphase on coated anodes was thinner and more uniform.",
      "type": "terminology_unification",
      "reason": "'solid-electrolyte interphase' is a banned hyphenation of the SEI full name.",
      "review": {"decision": "approve", "reason": "Removes banned variant; canonical form restored."}
    },
    {
      "edit_id": "e0008",
      "unit": "u0015",
      "new_text": "Li-ion diffusion coefficients extracted from GITT reached 4.5e-10 cm2 s-1.",
      "type": "terminology_unification",
      "reason": "'Lithium-ion' is a banned variant; use 'Li-ion'.",
      "review": {"decision": "approve", "reason": "Value 4.5e-10 cm2 s-1 preserved exactly."}
    },
    {
      "edit_id": "e0009",
      "unit": "u0016",
      "new_text": "Fig. 2 summarizes the rate capability of Li-ion cells [3].",
      "type": "terminology_unification",
      "reason": "'Li-ion and Lithium-ion cells' mixes a canonical form with a banned variant in one sentence; the redundancy is removed.",
      "review": {"decision": "approve", "reason": "Figure pointer 'Fig. 2' and citation [3] are preserved."}
    },
    {
      "edit_id": "e0010",
      "unit": "u0018",
      "new_text": "Al2O3 coatings stabilize the Li-ion cathode interface and effectively suppress SEI growth.",
      "type": "style",
      "reason": "Add emphasis."
    },
    {
      "edit_id": "e0011",
      "unit": "u0019",
      "new_text": "These findings demonstrate a scalable route to durable high-voltage Li-ion batteries.",
      "type": "terminology_unification",
      "reason": "'lithium ion batteries' is the banned long form in lowercase without hyphen; use 'Li-ion batteries'.",
      "review": {"decision": "approve", "reason": "Unifies the closing sentence with the glossary; no meaning change."}
    }
  ]
}
JSON

echo "== [6/9] apply the reviewed edit batch (gate: review + protected tokens) =="
python3 "$BUNDLE/scripts/pipeline.py" apply-edits \
  --units "$WORK/units.json" --edits "$WORK/edits.json" --out "$WORK/applied.json"

echo "== [7/9] export polished text, then run the full-text terminology gate =="
python3 "$BUNDLE/scripts/pipeline.py" export \
  --units "$WORK/units.json" --applied "$WORK/applied.json" \
  --label "Synthetic example output / 合成示例产物, not a formal case result" \
  --outdir "$OUT"
python3 "$BUNDLE/scripts/termbase.py" lint \
  --source "$OUT/polished.md" --termbase "$OUT/termbase.json" \
  --out "$OUT/term-lint.json"

echo "== [8/9] re-export with the terminology governance report =="
python3 "$BUNDLE/scripts/pipeline.py" export \
  --units "$WORK/units.json" --applied "$WORK/applied.json" \
  --lint "$OUT/term-lint.json" --termbase "$OUT/termbase.json" \
  --label "Synthetic example output / 合成示例产物, not a formal case result" \
  --outdir "$OUT"

echo "== [9/9] build result.json from the case output_contract and validate it =="
python3 "$BUNDLE/scripts/result.py" result-skeleton \
  --case case.json --artifacts "$OUT" --result "$WORK/result.skeleton.json"
python3 - <<'PY'
import json
sk = json.load(open(".tmp-work/result.skeleton.json", encoding="utf-8"))
sk["uncertainty"] = (
    "GITT was left unchanged: its expansion is not given in the draft and the "
    "term is not in the locked termbase. Chemical formulas (Al2O3, NCM811 "
    "formula) are outside termbase matching scope. All edits were verified by "
    "the mechanical gates; stylistic quality still needs a human read."
)
sk["notes"] = list(sk.get("notes", [])) + [
    "synthetic example / 合成示例, not a formal case result",
    "uncertainty: written by the agent during this run",
]
json.dump(sk, open("out/result.json", "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("result.json filled")
PY
python3 "$BUNDLE/scripts/result.py" validate-result \
  --case case.json --result "$OUT/result.json"

rm -rf "$WORK"
echo "OK - synthetic example finished; deliverables in $OUT/"
ls -la "$OUT"
