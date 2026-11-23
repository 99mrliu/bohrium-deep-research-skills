#!/usr/bin/env python3
"""make_result.py -- Bundle A (ga-spec-compiler), step 0 and final step.

Write (step 0, EARLY) or update (final) /app/output/result.json so a valid,
honest partial result exists from the first minutes of the run.

Usage:
  python3 make_result.py --case /input/case.json --outdir /app/output \
      [--status partial|complete|failed] [--gate pass|fail|not-run] \
      [--note "free text"] [--uncertainty "free text"]
"""
import argparse
import json
import os
import sys
import time

ROOT_FIELDS = ["case_id", "status", "editable_source", "export_artifacts",
               "content_map", "compliance_checks", "exceptions",
               "sources", "uncertainty", "change_record"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--gate", default="not-run")
    ap.add_argument("--note", default="")
    ap.add_argument("--uncertainty", default="")
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    case_id = case.get("case_id") or case.get("id") or "unknown"
    os.makedirs(args.outdir, exist_ok=True)
    rpath = os.path.join(args.outdir, "result.json")

    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as fh:
            res = json.load(fh)
    else:
        res = {k: None for k in ROOT_FIELDS}
        res.update({"case_id": case_id, "status": "partial",
                    "editable_source": {}, "export_artifacts": {},
                    "content_map": [], "compliance_checks": {},
                    "exceptions": [], "sources": [], "uncertainty": [],
                    "change_record": []})

    res["case_id"] = case_id
    res["status"] = args.status
    res["compliance_checks"]["spec_gate"] = args.gate
    if args.uncertainty:
        res["uncertainty"].append(args.uncertainty)
    res["change_record"].append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": args.status, "note": args.note})

    for name, key in (("graphical_abstract.svg", "svg"),
                      ("graphical_abstract.png", "png"),
                      ("graphical_abstract.pdf", "pdf")):
        p = os.path.join(args.outdir, name)
        if os.path.exists(p):
            res["export_artifacts"][key] = {"path": p,
                                            "bytes": os.path.getsize(p)}
    for name, key in (("figure_spec.json", "spec"),
                      ("graphical_abstract.svg", "svg")):
        p = os.path.join(args.outdir, name)
        if os.path.exists(p):
            res["editable_source"][key] = p
    with open(rpath, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"wrote": rpath, "status": args.status,
                      "gate": args.gate}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
