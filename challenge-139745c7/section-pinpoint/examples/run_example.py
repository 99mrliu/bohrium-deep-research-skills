#!/usr/bin/env python3
"""Run the section-pinpoint synthetic example end to end."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "output")
CASE = os.path.join(HERE, "case.json")
LIB = os.path.join(HERE, "library")
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

steps = [
    ["pinpoint_ingest.py", LIB, os.path.join(WORK, "anchors.jsonl"),
     os.path.join(WORK, "ingest_report.json")],
    ["pinpoint_search.py", CASE, os.path.join(WORK, "anchors.jsonl"),
     os.path.join(WORK, "hits.json")],
    ["pinpoint_result.py", CASE, WORK, os.path.join(OUT, "result.json")],
]
for step in steps:
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, step[0])] + step[1:],
                       capture_output=True, text=True)
    print("$ python3 %s" % step[0], "->",
          (p.stdout or p.stderr).strip().splitlines()[-1])
    if p.returncode:
        print("FAILED:", p.stderr)
        sys.exit(1)

hits = json.load(open(os.path.join(WORK, "hits.json"), encoding="utf-8"))
result = json.load(open(os.path.join(OUT, "result.json"), encoding="utf-8"))
r1, r2 = hits["results"]
assert r1["status"] == "located", r1
top = r1["hits"][0]
assert "终稿" in top["locator"] and "2.1" in (top["heading"] or ""), top
assert "HEPES" in top["quote"], top
assert r2["status"] == "no_match", r2
contract = json.load(open(CASE, encoding="utf-8"))["output_contract"]
missing = [f for f in contract if f not in result]
assert not missing, missing
print("OK: q1 located at", top["locator"], "| q2 no_match | contract covered")
