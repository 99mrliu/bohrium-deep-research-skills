#!/usr/bin/env python3
"""Run the handoff-renderer synthetic example end to end."""
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

steps = [
    ["handoff_scan.py", CASE, WORK],
    ["handoff_build.py", CASE, WORK, OUT],
    ["handoff_preview.py", OUT],
    ["handoff_result.py", CASE, WORK, os.path.join(OUT, "result.json")],
]
for step in steps:
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, step[0])] + step[1:],
                       capture_output=True, text=True)
    print("$ python3 %s" % step[0], "->",
          (p.stdout or p.stderr).strip().splitlines()[-1])
    if p.returncode:
        print("FAILED(rc=%d):" % p.returncode, p.stderr)
        sys.exit(1)

manifest = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
previews = json.load(open(os.path.join(OUT, "preview_report.json"),
                          encoding="utf-8"))
result = json.load(open(os.path.join(OUT, "result.json"), encoding="utf-8"))
check = json.load(open(os.path.join(OUT, "checklist_report.json"),
                       encoding="utf-8"))
assert manifest["completeness"]["ok"], manifest["completeness"]
assert len(manifest["entries"]) == 4
assert previews["preview_structure.png"]["valid"]
assert previews["preview_index.png"]["valid"]
assert check["ok"], check
contract = json.load(open(CASE, encoding="utf-8"))["output_contract"]
assert all(f in result for f in contract)
assert result["status"] == "complete"
assert any(a["status"] == "no_match" for a in result["answers"])
print("OK: completeness ok, 2 valid PNG previews, checklist ok,",
      "contract covered ->", sorted(os.listdir(OUT)))
