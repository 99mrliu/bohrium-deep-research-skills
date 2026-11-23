#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_run.py — one-command orchestrator for the whole audit battery.

Runs, in order:
  1. audit_svg_parse     SVG -> figure_graph.json
  2. audit_semantic_diff claims vs figure graph
  3. audit_pixels        PNG pixel probes (if --png)
  4. audit_exports       artifact/DPI/PDF/font/SVG-health (always; each
                         artifact optional)
  5. audit_edit_diff     before/after element diff (if --before-svg)

Merges everything into <out>/audit_report.json:
  {"summary": {"errors": N, "warnings": N, "skipped": N,
               "auditors_run": [...], "auditors_failed": [...]},
   "violations": [...], "skipped": [...]}
and prints a compact table. Exit code 1 if any error-severity violation
exists, else 0. An auditor that crashes is recorded in auditors_failed
and counts as a WARNING (never a pass), so a broken auditor cannot
masquerade as a clean figure.

Usage:
  audit_run.py --claims claims.json --svg figure.svg [--png figure.png]
               [--pdf figure.pdf] [--before-svg before.svg] --out DIR
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run_step(name, argv, out_file, failed):
    cmd = [sys.executable, os.path.join(HERE, name)] + argv
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0 or not os.path.exists(out_file):
        failed.append({"auditor": name,
                       "note": "exited %d: %s" % (
                           proc.returncode,
                           (proc.stderr or "").strip()[:400])})
        return None
    with open(out_file, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--before-svg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", type=int, default=24)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    violations, skipped, failed, ran = [], [], [], []

    graph_file = os.path.join(args.out, "figure_graph.json")
    r = run_step("audit_svg_parse.py",
                 ["--svg", args.svg, "--out", graph_file],
                 graph_file, failed)
    if r is not None:
        ran.append("audit_svg_parse")

        f = os.path.join(args.out, "viol_semantic.json")
        res = run_step("audit_semantic_diff.py",
                       ["--claims", args.claims, "--graph", graph_file,
                        "--out", f], f, failed)
        if res:
            ran.append("audit_semantic_diff")
            violations += res.get("violations", [])
            skipped += res.get("skipped", [])

        if args.png:
            f = os.path.join(args.out, "viol_pixels.json")
            res = run_step("audit_pixels.py",
                           ["--png", args.png, "--svg", args.svg,
                            "--claims", args.claims,
                            "--tolerance", str(args.tolerance),
                            "--out", f], f, failed)
            if res:
                ran.append("audit_pixels")
                violations += res.get("violations", [])
                skipped += res.get("skipped", [])

    argv = ["--out", os.path.join(args.out, "viol_exports.json")]
    if args.svg:
        argv += ["--svg", args.svg]
    if args.png:
        argv += ["--png", args.png]
    if args.pdf:
        argv += ["--pdf", args.pdf]
    f = os.path.join(args.out, "viol_exports.json")
    res = run_step("audit_exports.py", argv, f, failed)
    if res:
        ran.append("audit_exports")
        violations += res.get("violations", [])
        skipped += res.get("skipped", [])

    if args.before_svg:
        f = os.path.join(args.out, "viol_edit_diff.json")
        res = run_step("audit_edit_diff.py",
                       ["--before", args.before_svg, "--after", args.svg,
                        "--claims", args.claims, "--out", f], f, failed)
        if res:
            ran.append("audit_edit_diff")
            violations += res.get("violations", [])
            skipped += res.get("skipped", [])

    # crashed auditors become warnings — never silent passes
    for fl in failed:
        violations.append({"auditor": fl["auditor"], "check": "auditor.crashed",
                           "severity": "warning",
                           "detail": "auditor failed to run: %s" % fl["note"],
                           "element": None, "source": None})

    errors = sum(1 for v in violations if v["severity"] == "error")
    warnings = sum(1 for v in violations if v["severity"] == "warning")
    report = {
        "summary": {"errors": errors, "warnings": warnings,
                    "skipped": len(skipped),
                    "auditors_run": ran,
                    "auditors_failed": [f["auditor"] for f in failed]},
        "violations": violations,
        "skipped": skipped,
    }
    report_path = os.path.join(args.out, "audit_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n=== AUDIT REPORT (%s) ===" % report_path)
    print("%-8s %-16s %-28s %s" % ("SEV", "AUDITOR", "CHECK", "DETAIL"))
    for v in violations:
        print("%-8s %-16s %-28s %s" % (
            v["severity"], v["auditor"], v["check"],
            (v["detail"] or "")[:110]))
    for s in skipped:
        print("%-8s %-16s %-28s %s" % (
            "SKIPPED", "", s["check"], (s["note"] or "")[:110]))
    print("summary: %d errors, %d warnings, %d skipped" % (
        errors, warnings, len(skipped)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
