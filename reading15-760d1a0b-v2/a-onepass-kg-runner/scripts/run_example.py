#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the full a-onepass-kg-runner pipeline on the SYNTHETIC example corpus.

Simulates the official runtime (/input -> /app/work -> /app/output) using only
the bundle's own scripts:

    examples/synthetic/input   ->  examples/synthetic/_work  ->  examples/synthetic/output

The single model-written artifact is simulated by seeding
examples/synthetic/extractions.seed.jsonl into the work dir (the --seed option
of kg_run.py all), exactly where the harness agent would write
/app/work/extractions.jsonl.

Usage:  python3 scripts/run_example.py [--force]
Stdlib only. Exits 0 on success.
"""

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.dirname(HERE)
SYN = os.path.join(BUNDLE, "examples", "synthetic")
sys.path.insert(0, HERE)

import kg_run  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="ignore checkpoints and re-run all stages")
    args = ap.parse_args(argv)
    input_dir = os.path.join(SYN, "input")
    work = os.path.join(SYN, "_work")
    output = os.path.join(SYN, "output")
    seed = os.path.join(SYN, "extractions.seed.jsonl")
    for d in (work, output):
        if args.force and os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    kg_run.log("=== a-onepass-kg-runner SYNTHETIC example ===")
    kg_run.log("input : %s" % input_dir)
    kg_run.log("work  : %s" % work)
    kg_run.log("output: %s" % output)
    kg_run.log("(SYNTHETIC example, not real papers; outputs are demo data, "
               "not formal case answers)")
    ns = argparse.Namespace(input=input_dir, work=work, output=output,
                            force=args.force, seed=seed)
    rc = kg_run.run_all(ns)
    # demo hygiene: drop work-dir files that are byte-identical copies of
    # committed output files or of the seed JSONL, so the example tree stays
    # free of exact duplicates (checkpoints and run artifacts unique to the
    # work dir are kept; a real /app/work keeps everything at runtime).
    for fn in os.listdir(work):
        wp = os.path.join(work, fn)
        if not os.path.isfile(wp):
            continue
        for op in (os.path.join(output, fn),
                   os.path.join(SYN, "extractions.seed.jsonl")):
            if os.path.isfile(op) and _same_bytes(wp, op):
                os.remove(wp)
                break
    return rc


def _same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


if __name__ == "__main__":
    sys.exit(main())
