#!/usr/bin/env python3
"""Provenance join-check (audit-renderer skill).

Proves, for every field and claim in result.json:
  J1 scalar is a verbatim substring of its quote
  J2 quote is verbatim in the text layer (whitespace-normalized)
  J3 quote appears on the stated page
  J4 bank_id exists and its stored quote equals the field quote
  J5 every requested field is decided; non-reported mirrored in
     uncertainties; claims carry verbatim located evidence

Writes <work-dir>/verify_report.json. Exit 0 = PASS, 1 = errors found.
"""
import argparse
import json
import os
import re
import sys


def squash(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True)
    ap.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    d = json.load(open(a.result, encoding="utf-8"))
    layer = [json.loads(l) for l in
             open(os.path.join(a.work_dir, "layer.jsonl"), encoding="utf-8")]
    bank = {}
    bpath = os.path.join(a.work_dir, "bank.jsonl")
    if os.path.isfile(bpath):
        for l in open(bpath, encoding="utf-8"):
            b = json.loads(l)
            bank[b["bank_id"]] = b
    by_page = {}
    for e in layer:
        by_page.setdefault(e["page"], []).append(squash(e["text"]))
    whole = " ".join(squash(e["text"]) for e in layer)

    errors, checks = [], []

    def ok(name, cond, detail):
        checks.append({"check": name, "pass": bool(cond), "detail": detail})
        if not cond:
            errors.append("%s: %s" % (name, detail))

    frs = (d.get("result") or {}).get("field_results") or []
    if not frs:
        ok("coverage", False, "result.field_results empty")
    for r in frs:
        fid = r.get("field_id")
        st = r.get("status")
        if st == "reported":
            sc, qu = r.get("scalar") or "", r.get("quote") or ""
            ok("J1 %s" % fid, sc and sc in qu,
               "scalar %r verbatim in quote" % sc[:30])
            sq = squash(qu)
            ok("J2 %s" % fid, sq and sq in whole, "quote verbatim in layer")
            pg = r.get("page")
            ok("J3 %s" % fid,
               pg is not None and any(sq in t for t in by_page.get(pg, [])),
               "quote on stated page %s" % pg)
            bid = r.get("bank_id")
            if bid:
                b = bank.get(bid)
                ok("J4 %s" % fid,
                   b is not None and squash(b["quote"]) == sq,
                   "bank_id %s resolves, quote equal" % bid)
        elif st == "not_reported":
            ok("J5 %s" % fid, bool(r.get("notes")),
               "not_reported carries searched-terms notes")
        elif st == "extraction_failed":
            ok("J5 %s" % fid,
               r.get("page") is not None or r.get("paragraph_id"),
               "extraction_failed carries a takeover location")
        elif st == "source_conflict":
            ok("J5 %s" % fid, bool(r.get("notes")) and bool(r.get("quote")),
               "conflict lists readings+locations in notes")
        else:
            ok("status %s" % fid, False, "bad status %r" % st)
    unc = {u.get("field_id") for u in d.get("uncertainties", [])}
    for r in frs:
        if r.get("status") != "reported":
            ok("mirror %s" % r.get("field_id"), r.get("field_id") in unc,
               "non-reported field mirrored in uncertainties")
    for i, c in enumerate(d.get("claims", [])):
        ev = c.get("evidence") or {}
        q = squash(ev.get("quote"))
        ok("claim %d J2" % i, q and q in whole, "claim quote verbatim in layer")
        pg = ev.get("page")
        ok("claim %d J3" % i,
           pg is not None and any(q in t for t in by_page.get(pg, [])),
           "claim quote on page %s" % pg)
    rep = {"case_id": d.get("case_id"), "fields": len(frs),
           "checks": checks, "errors": len(errors),
           "verdict": "PASS" if not errors else "FAIL"}
    with open(os.path.join(a.work_dir, "verify_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    for c in checks:
        if not c["pass"]:
            print("ERROR [%s] %s" % (c["check"], c["detail"]))
    print("verify: %s (%d checks, %d errors)" %
          (rep["verdict"], len(checks), len(errors)))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
