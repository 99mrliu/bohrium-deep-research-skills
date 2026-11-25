#!/usr/bin/env python3
"""run_minimal_example.py — end-to-end demo of the bundle on the SYNTHETIC
example corpus, using ONLY the bundle's own scripts.

Simulates the runtime contract:
  examples/synthetic/input            -> /input
  examples/synthetic/work             -> /app/work   (regenerated)
  examples/synthetic/output           -> /app/output (committed for review)

The two model artifacts (adjudication.json, extractions.json) are taken from
examples/synthetic/model_artifacts/ and marked SYNTHETIC.

Usage: python3 scripts/run_minimal_example.py
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SYN = os.path.join(ROOT, "examples", "synthetic")
INPUT = os.path.join(SYN, "input")
WORK = os.path.join(SYN, "work")
OUTPUT = os.path.join(SYN, "output")
ARTIFACTS = os.path.join(SYN, "model_artifacts")

STAGES = [
    ("discover", ["discover.py", "--input", INPUT, "--work", WORK]),
    ("candidates", ["candidates.py", "--work", WORK]),
    ("adjudicate", ["adjudicate.py", "--work", WORK]),
    ("build_graph", ["build_graph.py", "--work", WORK]),
    ("verify", ["verify.py", "--work", WORK]),
    ("query", ["query.py", "--work", WORK]),
    ("assemble", ["assemble.py", "--work", WORK, "--output", OUTPUT]),
]


def _same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def main():
    timings = {}
    t0 = time.perf_counter()
    for d in (WORK, OUTPUT):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    # stage 0: the "model" delivers its two tiny artifacts into the work dir
    for name in ("adjudication.json", "extractions.json"):
        shutil.copyfile(os.path.join(ARTIFACTS, name), os.path.join(WORK, name))

    rc_all = 0
    for stage, cmd in STAGES:
        t1 = time.perf_counter()
        proc = subprocess.run([sys.executable] + [os.path.join(HERE, cmd[0])] + cmd[1:],
                              capture_output=True, text=True)
        timings[stage] = round(time.perf_counter() - t1, 4)
        print(proc.stdout.strip())
        if proc.returncode != 0:
            rc_all = proc.returncode
            print("stage %s FAILED (exit %d):\n%s" % (stage, proc.returncode,
                                                       proc.stderr),
                  file=sys.stderr)
            break

    # demo hygiene: drop work-dir files that are byte-identical copies of
    # committed output/ or model_artifacts/ files, so the example tree stays
    # free of exact duplicates (real /app/work keeps everything at runtime).
    for dirpath, _dirnames, filenames in os.walk(WORK):
        for fn in filenames:
            wp = os.path.join(dirpath, fn)
            for other_dir in (OUTPUT, ARTIFACTS):
                op = os.path.join(other_dir, fn)
                if os.path.isfile(op) and _same_bytes(wp, op):
                    os.remove(wp)
                    break

    import kgcommon as K  # local import; scripts dir is on sys.path
    K.dump_json({
        "notice": "run_meta is the ONLY artifact allowed to contain wall-clock "
                  "data; excluded from deterministic comparisons.",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "stage_seconds": timings,
        "total_seconds": round(time.perf_counter() - t0, 4),
        "exit_code": rc_all,
    }, os.path.join(WORK, "run_meta.json"))
    print("run_minimal_example: exit=%d (work=%s output=%s)"
          % (rc_all, WORK, OUTPUT))
    return rc_all


if __name__ == "__main__":
    sys.exit(main())
