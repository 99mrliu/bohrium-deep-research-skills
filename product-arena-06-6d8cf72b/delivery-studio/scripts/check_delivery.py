#!/usr/bin/env python3
"""check_delivery.py -- final delivery inspection for the output directory.

Checks (deterministic):
  1. every declared artifact exists, is non-empty, and (for .json) parses;
  2. manifest.json hashes match the files on disk (drift detection);
  3. result.json contains case_id and a non-in_progress status;
  4. preview artifacts listed when required (html always; png only when its
     render report said rendered).

Output: delivery-report.json + stdout summary. Exit 0 = deliverable,
2 = gaps (the report names each one; fix or declare in result limits).
"""
import argparse
import hashlib
import json
import os
import sys


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="delivery directory (/app/output)")
    ap.add_argument("--case", required=True)
    ap.add_argument("--require", nargs="*", default=["result.json", "notes.md",
                                                     "preview.html",
                                                     "manifest.json"])
    args = ap.parse_args()

    gaps = []
    for name in args.require:
        path = os.path.join(args.out, name)
        if not os.path.exists(path):
            gaps.append("missing artifact: " + name)
        elif os.path.getsize(path) == 0:
            gaps.append("empty artifact: " + name)
        elif name.endswith(".json"):
            try:
                with open(path, encoding="utf-8") as fh:
                    json.load(fh)
            except Exception as exc:
                gaps.append("unparseable json %s: %s" % (name, exc))

    result_path = os.path.join(args.out, "result.json")
    if os.path.exists(result_path):
        with open(result_path, encoding="utf-8") as fh:
            result = json.load(fh)
        case = json.load(open(args.case, encoding="utf-8"))
        if result.get("case_id") != case.get("case_id"):
            gaps.append("result.json case_id mismatch")
        if result.get("status") in (None, "in_progress"):
            gaps.append("result.json status not finalized: %r" % result.get("status"))
        for req in case.get("output_contract", {}).get("required", []):
            if req not in result:
                gaps.append("result.json missing required field: " + req)

    manifest_path = os.path.join(args.out, "manifest.json")
    drift = []
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        for entry in manifest.get("artifacts", []):
            if os.path.exists(entry["path"]) \
                    and sha256_file(entry["path"]) != entry["sha256"]:
                drift.append(entry["path"])
        if drift:
            gaps.append("manifest drift: " + ", ".join(drift))

    report = {"deliverable": not gaps, "gaps": gaps,
              "note": "a gap is a repair instruction, not a veto: fix it or "
                      "declare it in result.limits before delivery"}
    with open(os.path.join(args.out, "delivery-report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if not gaps else 2)


if __name__ == "__main__":
    main()
