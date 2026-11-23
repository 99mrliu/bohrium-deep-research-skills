#!/usr/bin/env python3
"""Finalize a result.json (run-controller skill): contract check, honest
overall status recomputed from field-level outcomes, uncertainties mirror,
change records appended from run.log.

Exit 0 = contract ok (file updated); 1 = violations found (printed).
"""
import argparse
import json
import os
import sys

STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True)
    ap.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    d = json.load(open(a.result, encoding="utf-8"))
    errors = []
    for k in ("case_id", "status", "result", "claims", "uncertainties"):
        if k not in d:
            errors.append("missing contract key %s" % k)
    if not d.get("case_id"):
        errors.append("case_id empty")
    frs = (d.get("result") or {}).get("field_results") or []
    if not frs:
        errors.append("result.field_results empty")
    seen = set()
    for r in frs:
        fid = r.get("field_id")
        if fid in seen:
            errors.append("duplicate field_id %s" % fid)
        seen.add(fid)
        st = r.get("status")
        if st not in STATUSES:
            errors.append("%s: bad status %r" % (fid, st))
        if st == "reported":
            if not r.get("scalar") or r.get("scalar") not in (r.get("quote") or ""):
                errors.append("%s: scalar not verbatim in quote" % fid)
            if r.get("page") is None:
                errors.append("%s: reported without page" % fid)
        if st == "not_reported" and not r.get("notes"):
            errors.append("%s: not_reported without notes" % fid)
        if st == "extraction_failed" and r.get("page") is None \
                and not r.get("paragraph_id"):
            errors.append("%s: extraction_failed without takeover location" % fid)
    for c in d.get("claims", []):
        ev = c.get("evidence") or {}
        if c.get("kind") not in ("conclusion", "limitation", "speculation"):
            errors.append("claim kind invalid: %r" % c.get("kind"))
        if not ev.get("quote") or ev.get("page") is None:
            errors.append("claim without located verbatim evidence")
    if errors:
        for e in errors:
            print("ERROR: %s" % e)
        print("finalize: FAIL (%d errors)" % len(errors))
        return 1

    sts = [r["status"] for r in frs]
    if all(s == "reported" for s in sts):
        d["status"] = "answered"
    elif all(s in ("not_reported", "extraction_failed") for s in sts):
        undecided = any("skeleton" in str(r.get("notes", "")) for r in frs)
        d["status"] = "partial" if undecided else "insufficient_evidence"
    else:
        d["status"] = "partial"
    d["uncertainties"] = [
        {"field_id": r["field_id"], "status": r["status"],
         "notes": r.get("notes")}
        for r in frs if r["status"] != "reported"
    ]
    # change records from run.log
    log_p = os.path.join(a.work_dir, "run.log")
    changes = []
    if os.path.isfile(log_p):
        for ln in open(log_p, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                changes.append(ln)
    d["change_records"] = changes[-40:]
    with open(a.result, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("finalize: OK status=%s fields=%d uncertainties=%d" % (
        d["status"], len(frs), len(d["uncertainties"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
