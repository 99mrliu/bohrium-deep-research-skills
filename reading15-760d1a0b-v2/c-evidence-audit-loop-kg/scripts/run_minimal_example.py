#!/usr/bin/env python3
"""run_minimal_example.py — end-to-end SYNTHETIC example (non-interactive).

Runs the whole audit-loop pipeline from examples/synthetic/input to
examples/synthetic/output using ONLY this bundle's scripts, simulating the
model's two writing steps with the pre-authored files:
  * examples/stage1_extraction_draft.json  plays "stage 1: model drafts extraction"
    (deliberately contains a few flawed items so the audit loop has work to do)
  * examples/stage2_repairs.json           plays "stage 3: model repairs the queue"

Everything between those two steps (discovery, audit, repair application,
re-audit, graph build, query execution, assembly, certificate) is mechanical.

Usage:
    python3 scripts/run_minimal_example.py [--bundle <bundle-root>]

Python 3.9+, standard library only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def _same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def run(cmd):
    print("+ %s" % " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0:
        print("FATAL: command exited %d" % proc.returncode, file=sys.stderr)
        sys.exit(proc.returncode)


def main():
    ap = argparse.ArgumentParser(description="Run the synthetic end-to-end example")
    ap.add_argument("--bundle", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="bundle root (default: parent of this script)")
    args = ap.parse_args()
    bundle = os.path.abspath(args.bundle)
    scripts = os.path.join(bundle, "scripts")
    examples = os.path.join(bundle, "examples")
    indir = os.path.join(examples, "synthetic", "input")
    work = os.path.join(examples, "synthetic", "work")
    outdir = os.path.join(examples, "synthetic", "output")

    for d in (work, outdir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    print("== SYNTHETIC example run (not real papers, not formal case answers) ==")

    # stage 0: discover
    run([sys.executable, os.path.join(scripts, "discover.py"),
         "--input", indir, "--work", work, "--output", outdir])

    # stage 1 (simulated model): write extraction draft
    shutil.copyfile(os.path.join(examples, "stage1_extraction_draft.json"),
                    os.path.join(work, "extraction.draft.json"))
    print("+ [simulated model] wrote extraction.draft.json (stage 1 draft)")

    # stage 2: audit iteration 1
    run([sys.executable, os.path.join(scripts, "audit.py"),
         "--work", work, "--draft", os.path.join(work, "extraction.draft.json"),
         "--iteration", "1"])

    # stage 3 (simulated model): repair ONLY the queued items
    shutil.copyfile(os.path.join(examples, "stage2_repairs.json"),
                    os.path.join(work, "repairs.json"))
    print("+ [simulated model] wrote repairs.json (targeted repairs for repair_queue.json)")
    run([sys.executable, os.path.join(scripts, "apply_repairs.py"),
         "--work", work,
         "--base", os.path.join(work, "extraction.draft.json"),
         "--repairs", os.path.join(work, "repairs.json"),
         "--out", os.path.join(work, "extraction.repaired.json")])

    # stage 4: re-audit (bounded at 2 iterations)
    run([sys.executable, os.path.join(scripts, "audit.py"),
         "--work", work, "--draft", os.path.join(work, "extraction.repaired.json"),
         "--iteration", "2"])

    # stages 5-7: build, query, assemble
    run([sys.executable, os.path.join(scripts, "build_graph.py"), "--work", work])
    run([sys.executable, os.path.join(scripts, "query.py"), "--work", work])
    run([sys.executable, os.path.join(scripts, "assemble.py"),
         "--work", work, "--output", outdir])

    # copy the key loop artifacts into output for inspection
    for name in ("audit_report.iter1.json", "audit_report.iter2.json",
                 "repair_queue.iter1.json", "repair_queue.iter2.json",
                 "extraction.repaired.json"):
        shutil.copyfile(os.path.join(work, name), os.path.join(outdir, name))

    # demo hygiene: drop work-dir files that are byte-identical copies of
    # committed output files or of the pre-authored stage files, so the
    # example tree stays free of exact duplicates (a real /app/work keeps
    # everything at runtime).
    for fn in os.listdir(work):
        wp = os.path.join(work, fn)
        if not os.path.isfile(wp):
            continue
        for op in (os.path.join(outdir, fn),
                   os.path.join(examples, "stage1_extraction_draft.json"),
                   os.path.join(examples, "stage2_repairs.json")):
            if os.path.isfile(op) and _same_bytes(wp, op):
                os.remove(wp)
                break

    cert = json.load(open(os.path.join(outdir, "audit_certificate.json"), encoding="utf-8"))
    m0 = cert["iterations"][0]["metrics"]
    m1 = cert["iterations"][-1]["metrics"]
    graph = json.load(open(os.path.join(outdir, "graph.json"), encoding="utf-8"))
    queries = json.load(open(os.path.join(outdir, "queries.json"), encoding="utf-8"))
    print("")
    print("== example summary ==")
    print("audit iteration 1 (raw draft):    quote=%.1f%% addr=%.1f%% attr=%.1f%% coverage=%.1f%% accept=%d repair=%d" % (
        m0["quote_precision_pct"], m0["address_validity_pct"],
        m0["attribution_accuracy_pct"], m0["paragraph_coverage_pct"],
        m0["accepted"], m0["repair"]))
    print("audit iteration 2 (post-repair):  quote=%.1f%% addr=%.1f%% attr=%.1f%% coverage=%.1f%% accept=%d reject=%d" % (
        m1["quote_precision_pct"], m1["address_validity_pct"],
        m1["attribution_accuracy_pct"], m1["paragraph_coverage_pct"],
        m1["accepted"], m1["rejected"]))
    print("certificate verdict: %s | quarantined: %d" % (cert["verdict"], cert["quarantined_count"]))
    print("graph: nodes=%d edges=%d merges=%d nonmerges=%d unreported=%d" % (
        graph["stats"]["node_count"], graph["stats"]["edge_count"],
        graph["stats"]["merge_count"], graph["stats"]["nonmerge_count"],
        graph["stats"]["unreported_count"]))
    print("queries executed: %d/%d" % (queries["queries_executed"], queries["queries_total"]))
    print("outputs in: %s" % outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
