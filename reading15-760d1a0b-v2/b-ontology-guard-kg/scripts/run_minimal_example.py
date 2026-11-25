#!/usr/bin/env python3
"""run_minimal_example.py — end-to-end SYNTHETIC example for b-ontology-guard-kg.

Runs the whole pipeline with ONLY this bundle's scripts, simulating the
runtime contract (/input -> /app/work -> /app/output) inside examples/:

    examples/synthetic/input/           (synthetic /input)
    examples/synthetic/work/            (authored SYNTHETIC model drafts,
                                         incl. a deliberate ontology violation)
    examples/synthetic/output/work/     (simulated /app/work, regenerated)
    examples/synthetic/output/          (simulated /app/output, regenerated)

Steps: discover -> validate (draft) -> validate (repair) -> build -> query
-> assemble. Exits non-zero if any step fails.

Usage:
    python3 scripts/run_minimal_example.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.dirname(HERE)
EX = os.path.join(BUNDLE, "examples", "synthetic")
IN_DIR = os.path.join(EX, "input")
DRAFTS = os.path.join(EX, "work")
OUT_DIR = os.path.join(EX, "output")
WORK_DIR = os.path.join(OUT_DIR, "work")


def step(cmd):
    print("+ python3 " + " ".join(cmd))
    proc = subprocess.run([sys.executable] + cmd)
    if proc.returncode != 0:
        print("STEP FAILED with exit code %d: %s" % (proc.returncode, cmd),
              file=sys.stderr)
        sys.exit(proc.returncode)


def main():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(WORK_DIR, exist_ok=True)
    scripts = os.path.join(BUNDLE, "scripts")
    step([os.path.join(scripts, "discover.py"),
          "--input", IN_DIR, "--work", WORK_DIR])
    step([os.path.join(scripts, "validate_ontology.py"),
          "--work", WORK_DIR,
          "--extraction", os.path.join(DRAFTS, "extractions_draft.jsonl")])
    step([os.path.join(scripts, "validate_ontology.py"), "--repair",
          "--work", WORK_DIR,
          "--extraction", os.path.join(DRAFTS, "extractions_repair.jsonl")])
    step([os.path.join(scripts, "build_graph.py"), "--work", WORK_DIR])
    step([os.path.join(scripts, "query.py"), "--work", WORK_DIR])
    step([os.path.join(scripts, "assemble.py"),
          "--work", WORK_DIR, "--output", OUT_DIR])
    # demo hygiene: drop simulated-work files that are byte-identical copies
    # of committed output files or authored drafts, so the example tree stays
    # free of exact duplicates (a real /app/work keeps everything at runtime).
    for fn in os.listdir(WORK_DIR):
        wp = os.path.join(WORK_DIR, fn)
        if not os.path.isfile(wp):
            continue
        for op in (os.path.join(OUT_DIR, fn), os.path.join(DRAFTS, fn)):
            if os.path.isfile(op) and _same_bytes(wp, op):
                os.remove(wp)
                break
    print("SYNTHETIC example pipeline finished OK -> %s" % OUT_DIR)
    return 0


def _same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


if __name__ == "__main__":
    sys.exit(main())
