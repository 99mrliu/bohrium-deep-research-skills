#!/usr/bin/env python3
"""Run the queryforge synthetic example end to end."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
REFS = os.path.join(HERE, "..", "references")
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "output")
CASE = os.path.join(HERE, "case.json")
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

steps = [
    ["forge_parse.py", CASE, os.path.join(REFS, "lexicon.json"),
     os.path.join(WORK, "queries.json")],
    ["forge_run.py", CASE, os.path.join(WORK, "queries.json"),
     os.path.join(WORK, "query_results.json")],
    ["forge_result.py", CASE, WORK, os.path.join(OUT, "result.json")],
]
for step in steps:
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, step[0])] + step[1:],
                       capture_output=True, text=True)
    print("$ python3 %s" % step[0], "->",
          (p.stdout or p.stderr).strip().splitlines()[-1])
    if p.returncode:
        print("FAILED:", p.stderr)
        sys.exit(1)

qr = json.load(open(os.path.join(WORK, "query_results.json"), encoding="utf-8"))
result = json.load(open(os.path.join(OUT, "result.json"), encoding="utf-8"))
r1, r2, r3 = qr["results"]
assert r1["status"] == "matched", r1
assert "final" in r1["hits"][0]["file"], r1["hits"]
assert r1["filter_trace"]["version"]["dropped"] >= 1, r1["filter_trace"]
assert r2["status"] == "matched" and "B2023-014" in r2["hits"][0]["file"], r2
assert r3["status"] == "no_match", r3
assert r3["filter_trace"], r3
contract = json.load(open(CASE, encoding="utf-8"))["output_contract"]
missing = [f for f in contract if f not in result]
assert not missing, missing
print("OK: q1 final-only, q2 batch hit, q3 honest no_match with trace;",
      "contract covered")
