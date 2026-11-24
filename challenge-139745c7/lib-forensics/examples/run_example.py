#!/usr/bin/env python3
"""Run the lib-forensics synthetic example end to end.

Creates ./work and ./output next to this file and executes the four pipeline
steps against the synthetic library/. Prints a compact verification summary.
"""
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
    ["forensics_case.py", CASE, os.path.join(WORK, "case_profile.json")],
    ["forensics_scan.py", LIB, WORK],
    ["forensics_answer.py", os.path.join(WORK, "case_profile.json"),
     os.path.join(WORK, "inventory.json"), os.path.join(WORK, "answers.json")],
    ["forensics_result.py", CASE, WORK, os.path.join(OUT, "result.json")],
]
for step in steps:
    script = os.path.join(SCRIPTS, step[0])
    p = subprocess.run([sys.executable, script] + step[1:],
                       capture_output=True, text=True)
    print("$ python3 %s %s" % (step[0], " ".join(step[1:])))
    print("  ->", (p.stdout or p.stderr).strip().splitlines()[-1])
    if p.returncode:
        print("FAILED:", p.stderr)
        sys.exit(1)

inv = json.load(open(os.path.join(WORK, "inventory.json"), encoding="utf-8"))
result = json.load(open(os.path.join(OUT, "result.json"), encoding="utf-8"))
dup = [f for f in inv["files"] if f["status"] == "duplicate"]
suspect = [f for f in inv["files"] if f["status"] == "suspect"]
assert dup and dup[0]["path"].endswith("_copy.md"), "duplicate not detected"
assert suspect and suspect[0]["path"].endswith(".pdf"), "type_mismatch not detected"
contract = json.load(open(CASE, encoding="utf-8"))["output_contract"]
missing = [f for f in contract if f not in result]
assert not missing, "contract fields missing: %s" % missing
assert result["case_id"] == "synthetic-demo-forensics"
print("OK: duplicate + type_mismatch detected; result.json covers contract",
      contract)
