#!/bin/sh
# run.sh -- end-to-end demo of c2e-detox-polish on the SYNTHETIC minimal case.
# Relative paths only; no network; Python 3 standard library only.
#
# Division of labor: scripts do lint/alignment/conservation/gating/statistics;
# the Agent (LLM) does the actual rewriting and back-translation. To keep this
# example runnable without a model, the Agent's rewrite and worksheet fillings
# are pre-scripted below (clearly marked). Everything else is real execution.
set -eu
cd "$(dirname "$0")"

OUT=out
SCRIPTS=../../scripts
# Relative workdir so paths recorded in JSON artifacts are deterministic.
TMP=.work
rm -rf "$TMP"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== 0. extract case materials (zh source, en draft) =="
python3 - "$TMP" <<'PY'
import json, sys
case = json.load(open("case.json", encoding="utf-8"))
m = case["materials"]
open(sys.argv[1] + "/zh.txt", "w", encoding="utf-8").write(m["zh_source"]["text"] + "\n")
open(sys.argv[1] + "/en-draft.txt", "w", encoding="utf-8").write(m["en_draft"]["text"] + "\n")
print("case_id:", case["case_id"])
PY

echo "== 1. detox lint of the ORIGINAL Chinglish draft =="
python3 "$SCRIPTS/detox.py" lint --text "$TMP/en-draft.txt" --out "$OUT/detox-report.json"
python3 "$SCRIPTS/detox.py" export-md --report "$OUT/detox-report.json" --out "$OUT/detox-report.md"

echo "== 2. AGENT STEP (pre-scripted stand-in): rewrite into idiomatic grant English =="
# In real use the Agent (LLM) writes this translation using
# references/restructuring-guide.md + genre-notes.md + the lint hits above.
cat > "$TMP/en-polished.txt" <<'EOF'
Stricter industrial emission standards have made efficient and stable low-temperature denitration catalysts a priority for air pollution control. We will load manganese-cerium mixed oxide onto nanoscale titania to construct a core-shell catalyst for low-temperature selective catalytic reduction (SCR). We will combine in situ infrared spectroscopy with density functional theory calculations to clarify how manganese-cerium interfacial synergy regulates NH3 adsorption and activation. In preliminary work, our MnOx-CeO2/TiO2 catalyst converted more than 92% of NOx across the 150-250 °C window [1]. The analogous system reported in reference [2] (2020) deactivates readily in sulfur-containing atmospheres; we will therefore introduce yttrium doping to improve sulfur resistance. The expected outcomes will inform diesel vehicle exhaust purification and offer both mechanistic insight and application value.
EOF

echo "== 3. idempotency check: lint the polished text (expect 0 hits) =="
python3 "$SCRIPTS/detox.py" lint --text "$TMP/en-polished.txt" --out "$TMP/detox-polished.json"
python3 - "$TMP/detox-polished.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["hit_count"] == 0, "polished text still has %d lint hits" % r["hit_count"]
print("polished text lint hits: 0 (idempotent)")
PY

echo "== 4. align zh <-> polished en =="
python3 "$SCRIPTS/align.py" align --zh "$TMP/zh.txt" --en "$TMP/en-polished.txt" --out "$OUT/alignment.json"

echo "== 5. conservation coverage gate + alignment table =="
python3 "$SCRIPTS/align.py" coverage --alignment "$OUT/alignment.json" \
    --out "$OUT/coverage.json" --table "$OUT/alignment-table.md"

echo "== 6. back-translation QA =="
python3 "$SCRIPTS/align.py" backtrans-template --alignment "$OUT/alignment.json" --out "$TMP/backtrans-template.json"
# AGENT STEP (pre-scripted stand-in): the LLM back-translates each en_text into
# Chinese and labels equivalence. Unfilled or 'mismatch' pairs would be forced
# into uncertainty by backtrans-check and forbid status=success.
python3 - "$TMP/backtrans-template.json" "$OUT/backtrans.json" <<'PY'
import json, sys
ws = json.load(open(sys.argv[1], encoding="utf-8"))
fills = {
 "p0001": ("更严格的工业排放标准使高效、稳定的低温脱硝催化剂成为大气污染控制的优先方向。",
           "equivalent", ""),
 "p0002": ("我们将锰铈复合氧化物负载于纳米二氧化钛上，构建用于低温选择性催化还原（SCR）的核壳催化剂。",
           "equivalent", ""),
 "p0003": ("我们将结合原位红外光谱与密度泛函理论计算，阐明锰铈界面协同作用如何调控NH3的吸附与活化。",
           "equivalent", ""),
 "p0004": ("在前期工作中，我们的MnOx-CeO2/TiO2催化剂在150-250 °C窗口内实现了超过92%的NOx转化[1]。",
           "equivalent", ""),
 "p0005": ("文献[2]（2020）报道的类似体系在含硫气氛中容易失活；因此我们将引入钇掺杂以提高抗硫性能。",
           "equivalent", ""),
 "p0006": ("预期成果将为柴油车尾气净化提供参考，兼具机理认识与应用价值。",
           "minor-difference",
           "原文套话'理论依据与技术支撑/重要的科学意义和应用前景'被有意弱化为'机理认识与应用价值'，限定强度略降；需作者确认可接受。"),
}
for p in ws["pairs"]:
    bt, eq, note = fills[p["pair_id"]]
    p["back_translation"], p["equivalence"], p["note"] = bt, eq, note
json.dump(ws, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("backtrans worksheet filled (Agent stand-in): %d pairs" % len(ws["pairs"]))
PY
python3 "$SCRIPTS/align.py" backtrans-check --backtrans "$OUT/backtrans.json" --out "$TMP/backtrans-check.json"
python3 - "$TMP/backtrans-check.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["gate"] == "pass", "backtrans gate failed: %s" % r["uncertainty"]
print("backtrans gate: pass (%s)" % r["counts"])
PY

echo "== 7. export polished-en.md =="
python3 - "$TMP/en-polished.txt" "$OUT/polished-en.md" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8").read().strip()
with open(sys.argv[2], "w", encoding="utf-8") as f:
    f.write("# Polished English translation (SYNTHETIC minimal example)\n\n")
    f.write("> 合成示例输出：c2e-detox-polish, case C2E-MIN-001.\n")
    f.write("> Source: synthetic zh grant paragraph in case.json; draft detoxed "
            "from 23 lint hits to 0.\n\n")
    f.write(text + "\n")
PY

echo "== 8. result.json: skeleton -> fill -> validate =="
python3 "$SCRIPTS/result.py" result-skeleton --case case.json --out "$TMP/skeleton.json"
python3 - "$TMP" "$OUT" <<'PY'
import json, sys
tmp, out = sys.argv[1], sys.argv[2]
skel = json.load(open(tmp + "/skeleton.json", encoding="utf-8"))["skeleton"]
draft_rep = json.load(open(out + "/detox-report.json", encoding="utf-8"))
pol_rep = json.load(open(tmp + "/detox-polished.json", encoding="utf-8"))
align = json.load(open(out + "/alignment.json", encoding="utf-8"))
cov = json.load(open(out + "/coverage.json", encoding="utf-8"))
btc = json.load(open(tmp + "/backtrans-check.json", encoding="utf-8"))
polished = open(tmp + "/en-polished.txt", encoding="utf-8").read().strip()

ok = cov["summary"]["all_conserved"] and btc["gate"] == "pass"
result = skel
result["case_id"] = "C2E-MIN-001"
result["translated_text"] = polished
result["polished_text"] = polished
result["alignment"] = [
    {"pair_id": p["pair_id"], "zh_text": p["zh_text"], "en_text": p["en_text"]}
    for p in align["pairs"]
]
result["detox_report"] = {
    "draft_hits": draft_rep["hit_count"],
    "polished_hits": pol_rep["hit_count"],
    "by_category": draft_rep["by_category"],
    "report_json": "out/detox-report.json",
    "report_md": "out/detox-report.md",
}
result["coverage"] = {
    "all_conserved": cov["summary"]["all_conserved"],
    "pair_count": cov["summary"]["pair_count"],
    "passed": cov["summary"]["passed"],
    "failed": cov["summary"]["failed"],
    "file": "out/coverage.json",
}
result["backtranslation_check"] = {
    "gate": btc["gate"],
    "counts": btc["counts"],
    "file": "out/backtrans.json",
}
result["exports"] = ["out/polished-en.md", "out/alignment-table.md",
                     "out/detox-report.md"]
result["status"] = "success" if ok else "partial"
result["sources"] = ["materials.zh_source (inline in case.json)",
                     "materials.en_draft (inline in case.json)"]
result["uncertainty"] = []
result["notes"] = (
    "Synthetic minimal example. translated_text == polished_text: the Agent "
    "rewrite already resolved all 23 lint hits (polished lint = 0), so no "
    "separate polish pass changed the text. Pair p0006 is an honest "
    "minor-difference in back-translation (deliberate de-boilerplating of "
    "'科学意义和应用前景'); recorded in out/backtrans.json, author "
    "confirmation recommended. All Agent steps (rewrite, back-translation) "
    "are pre-scripted in run.sh for reproducibility; in real use the LLM "
    "produces them.")
json.dump(result, open(out + "/result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("result.json written, status=%s" % result["status"])
PY
python3 "$SCRIPTS/result.py" validate-result --case case.json --result "$OUT/result.json"

echo "DONE. Artifacts in $OUT/"
