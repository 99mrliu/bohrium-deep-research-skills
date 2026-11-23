#!/usr/bin/env python3
"""write_result.py -- Bundle B (ga-archetype-forge): early-partial result writer.

Creates /app/output/result.json IMMEDIATELY after reading case.json (run it
before any drawing), then re-run at each milestone to update status. Keeps the
original output_contract fields plus case_id; honest status at every step.

Usage:
  python3 write_result.py --case /input/case.json --outdir /app/output \
      [--status early-partial|draft-forged|audited|complete|failed] \
      [--milestone "what just happened"] [--caveat "known limitation"]
"""
import argparse
import datetime
import json
import os
import sys

FIELDS = ["case_id", "task_echo", "status", "artifacts", "editable_source",
          "archetype_choice", "anchor_report", "layout_audit",
          "export_report", "exceptions", "limitations", "milestones"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--status", default="early-partial")
    ap.add_argument("--milestone", default="")
    ap.add_argument("--caveat", default="")
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    os.makedirs(args.outdir, exist_ok=True)
    rpath = os.path.join(args.outdir, "result.json")

    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as fh:
            res = json.load(fh)
    else:
        res = {k: None for k in FIELDS}
        res.update({"case_id": case.get("case_id") or case.get("id"),
                    "task_echo": case.get("task") or case.get("workorder"),
                    "artifacts": {}, "editable_source": {},
                    "anchor_report": {}, "layout_audit": {},
                    "export_report": {}, "exceptions": [],
                    "limitations": [], "milestones": []})

    res["status"] = args.status
    if args.milestone:
        res["milestones"].append({"ts": now(), "status": args.status,
                                  "note": args.milestone})
    if args.caveat:
        res["limitations"].append(args.caveat)

    for name in ("graphical_abstract.svg", "graphical_abstract.pdf",
                 "graphical_abstract.png"):
        p = os.path.join(args.outdir, name)
        if os.path.exists(p):
            res["artifacts"][name.rsplit(".", 1)[1]] = {
                "path": p, "bytes": os.path.getsize(p)}
    if "svg" in res["artifacts"]:
        res["editable_source"]["svg"] = res["artifacts"]["svg"]["path"]
    for candidate in (os.path.join(args.outdir, "..", "work", "params.json"),
                      "/app/work/params.json"):
        if os.path.exists(candidate):
            res["editable_source"]["params"] = os.path.abspath(candidate)
            break

    with open(rpath, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"wrote": rpath, "status": args.status}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
