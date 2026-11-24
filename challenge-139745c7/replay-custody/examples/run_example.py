#!/usr/bin/env python3
"""Run the replay-custody synthetic example end to end.

Injects one deliberately paraphrased evidence card after the retrieval step
to demonstrate that the gate rejects non-verbatim quotes.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "output")
CASE = os.path.join(HERE, "case.json")
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def run(args, expect=0):
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    print("$ python3 %s" % os.path.basename(args[0]), "->",
          (p.stdout or p.stderr).strip().splitlines()[-1])
    if p.returncode != expect:
        print("FAILED(rc=%d):" % p.returncode, p.stderr)
        sys.exit(1)
    return p


run([os.path.join(SCRIPTS, "custody_run.py"), CASE, WORK])

# inject a forged card: paraphrased quote that is NOT verbatim
cards_p = os.path.join(WORK, "evidence_cards.json")
data = json.load(open(cards_p, encoding="utf-8"))
lib_file = os.path.join(HERE, "library", "实验记录_B2023-014.md")
digest = hashlib.sha256(open(lib_file, "rb").read()).hexdigest()
data["cards"].append({
    "question_id": "q1", "question": "（注入的伪卡）",
    "claim": "缓冲液为 0.05 M Tris", "file": "实验记录_B2023-014.md",
    "sha256": digest, "quote": "缓冲液为 0.05 M Tris 缓冲液（改写，非原文）",
    "char_start": 0, "char_end": 20})
json.dump(data, open(cards_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

run([os.path.join(SCRIPTS, "custody_gate.py"), WORK,
     os.path.join(WORK, "verified_answers.json")])
run([os.path.join(SCRIPTS, "custody_contract.py"), CASE, WORK,
     os.path.join(OUT, "result.json")])
run([os.path.join(SCRIPTS, "custody_journal.py"), "seal", WORK,
     os.path.join(OUT, "REPLAY.md")])

gate = json.load(open(os.path.join(WORK, "verified_answers.json"),
                      encoding="utf-8"))
result = json.load(open(os.path.join(OUT, "result.json"), encoding="utf-8"))
assert gate["n_rejected"] == 1, gate
assert "quote_not_verbatim" in gate["rejected"][0]["reasons"][0] or \
    "quote_not_verbatim" in ";".join(gate["rejected"][0]["reasons"])
assert not any("改写" in str(a.get("claim", "")) for a in result["answers"])
assert result["rejected_claims"], "rejection not surfaced"
contract = json.load(open(CASE, encoding="utf-8"))["output_contract"]
assert all(f in result for f in contract)
rep = json.load(open(os.path.join(WORK, "contract_report.json"), encoding="utf-8"))
assert rep["ok"], rep
print("OK: forged card rejected by gate, honest not_found kept,",
      "contract ok, chain sealed")
