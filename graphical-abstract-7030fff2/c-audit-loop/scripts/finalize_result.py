#!/usr/bin/env python3
"""finalize_result.py -- Bundle C (ga-audit-loop): early + final result.json.

Writes /app/output/result.json at the START of the run (partial, honest) and
updates it after each phase. All original output_contract fields are carried
from case.json; every entry records which gate produced it.

Usage:
  python3 finalize_result.py --case /input/case.json --output /app/output \
      [--phase mined|ledgered|inspected|exported|complete|failed] \
      [--ledger-gate pass|fail|not-run] [--inspect-verdict clean|defects|not-run] \
      [--exception "text"] [--uncertainty "text"]
"""
import argparse
import datetime
import json
import os
import sys

BASE_FIELDS = ["case_id", "status", "phase", "editable_source",
               "export_artifacts", "source_ledger", "gates",
               "change_record", "exceptions", "uncertainty"]


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--phase", default="mined")
    ap.add_argument("--ledger-gate", default=None)
    ap.add_argument("--inspect-verdict", default=None)
    ap.add_argument("--exception", default=None)
    ap.add_argument("--uncertainty", default=None)
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    os.makedirs(args.output, exist_ok=True)
    rpath = os.path.join(args.output, "result.json")

    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as fh:
            res = json.load(fh)
    else:
        res = {k: None for k in BASE_FIELDS}
        res.update({"case_id": case.get("case_id") or case.get("id"),
                    "status": "partial", "gates": {}, "change_record": [],
                    "exceptions": [], "uncertainty": [],
                    "editable_source": {}, "export_artifacts": {}})
        contract = case.get("output_contract") or {}
        for f in contract.get("fields", []):
            res.setdefault(f, None)

    res["phase"] = args.phase
    res["status"] = "complete" if args.phase == "complete" else (
        "failed" if args.phase == "failed" else "partial")
    res["gates"].update({k: v for k, v in
                         (("ledger", args.ledger_gate),
                          ("inspection", args.inspect_verdict)) if v})
    if args.exception:
        res["exceptions"].append({"ts": utcnow(), "text": args.exception})
    if args.uncertainty:
        res["uncertainty"].append({"ts": utcnow(), "text": args.uncertainty})
    res["change_record"].append({"ts": utcnow(), "phase": args.phase})

    for name, slot in (("graphical_abstract.svg", "svg"),
                       ("graphical_abstract.png", "png"),
                       ("graphical_abstract.pdf", "pdf")):
        p = os.path.join(args.output, name)
        if os.path.exists(p):
            res["export_artifacts"][slot] = {"path": p,
                                             "bytes": os.path.getsize(p)}
    if "svg" in res["export_artifacts"]:
        res["editable_source"]["svg"] = res["export_artifacts"]["svg"]["path"]
    for extra, slot in (("/app/work/source_ledger.json", "ledger"),
                        ("/app/work/patch.json", "patch")):
        if os.path.exists(extra):
            res["editable_source"][slot] = extra

    with open(rpath, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"wrote": rpath, "phase": args.phase,
                      "status": res["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
