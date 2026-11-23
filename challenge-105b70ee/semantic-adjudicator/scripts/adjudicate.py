#!/usr/bin/env python3
"""Per-field adjudication state machine (semantic-adjudicator skill).

Subcommands:
  draft  --input-dir /input --output /app/output/result.json
      Build a valid honest-partial skeleton: every requested field
      not_reported, status partial.
  set    --output R --field F --status S [value/evidence options]
      Record one field decision; schema violations are REJECTED (exit 1,
      file untouched).
  claim  --output R --kind K --text T --quote Q --page N [--paragraph-id P]
      Add a claim (conclusion|limitation|speculation).
  check  --output R
      Verify contract completeness and status consistency; exit 0 PASS.

The tool enforces: scalar verbatim inside quote; condition mandatory for
numeric reported values; comparator mandatory for comparative quotes;
not_reported requires searched-terms notes; extraction_failed requires a
location. A guessed value cannot pass.
"""
import argparse
import json
import os
import re
import sys

STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
OVERALL = {"answered", "partial", "insufficient_evidence", "input_error"}
CLAIM_KINDS = {"conclusion", "limitation", "speculation"}
COMPARATIVE = re.compile(
    r"\b(over|vs\.?|versus|than|compared (to|with)|outperform|improvement"
    r"|higher than|lower than|relative to)\b|相比|优于|高于|低于", re.IGNORECASE)
NUMERIC = re.compile(r"[-+]?\d")


def fail(msg):
    print("REJECTED: %s" % msg, file=sys.stderr)
    return 1


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_fields(input_dir):
    tf = os.path.join(input_dir, "target-fields.json")
    fields = []
    if os.path.isfile(tf):
        d = json.load(open(tf, encoding="utf-8"))
        for f in d.get("fields", []):
            fields.append(f["field_id"])
    if not fields:
        # fall back: fields listed in task.md as "- field_id: xxx" lines
        tm = os.path.join(input_dir, "task.md")
        if os.path.isfile(tm):
            fields = re.findall(r"field_id[\": ]+([A-Za-z0-9_.-]+)",
                                open(tm, encoding="utf-8").read())
    return fields


def cmd_draft(a):
    case_path = os.path.join(a.input_dir, "case.json")
    if not os.path.isfile(case_path):
        return fail("case.json not found in %s" % a.input_dir)
    case = json.load(open(case_path, encoding="utf-8"))
    contract = case.get("output_contract") or {}
    fields = read_fields(a.input_dir)
    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "result": {
            "field_results": [
                {"field_id": fid, "status": "not_reported",
                 "scalar": None, "units": None, "statistic": None,
                 "condition": None, "comparator": None,
                 "quote": None, "page": None, "paragraph_id": None,
                 "notes": "skeleton: not yet adjudicated"}
                for fid in fields
            ]
        },
        "claims": [],
        "uncertainties": [],
    }
    for k in contract:
        result.setdefault(k, None)
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    save(a.output, result)
    print("draft -> %s (%d fields, all not_reported)" % (a.output, len(fields)))
    return 0


def cmd_set(a):
    d = load(a.output)
    frs = d["result"]["field_results"]
    rec = next((r for r in frs if r["field_id"] == a.field), None)
    if rec is None:
        return fail("unknown field_id %r (draft first; known: %s)" % (
            a.field, [r["field_id"] for r in frs]))
    if a.status not in STATUSES:
        return fail("status must be one of %s" % sorted(STATUSES))
    if a.status == "reported":
        for need in ("scalar", "units", "quote", "page"):
            if getattr(a, need) in (None, ""):
                return fail("reported requires --%s" % need)
        if a.scalar not in a.quote:
            return fail("scalar %r is not verbatim inside --quote" % a.scalar)
        if NUMERIC.search(a.scalar) and not (a.condition or "").strip():
            return fail("numeric reported value requires --condition "
                        "(sample/setting/time point); values never stand alone")
        if COMPARATIVE.search(a.quote) and not (a.comparator or "").strip():
            return fail("comparative quote requires --comparator")
        rec.update(scalar=a.scalar, units=a.units, statistic=a.statistic,
                   condition=a.condition, comparator=a.comparator,
                   quote=a.quote, page=a.page, paragraph_id=a.paragraph_id,
                   status="reported", notes=a.notes or rec.get("notes"))
    elif a.status == "source_conflict":
        if not a.quote or not a.notes:
            return fail("source_conflict requires --quote (one reading) and "
                        "--notes listing the conflicting readings+locations")
        rec.update(status="source_conflict", scalar=a.scalar, units=a.units,
                   quote=a.quote, page=a.page, paragraph_id=a.paragraph_id,
                   condition=a.condition, comparator=a.comparator,
                   statistic=a.statistic, notes=a.notes)
    elif a.status == "not_reported":
        if not a.notes or len(a.notes) < 8:
            return fail("not_reported requires --notes with searched terms "
                        "(or the explicit 'n.d.' cell quote)")
        rec.update(status="not_reported", scalar=None, units=None,
                   statistic=None, condition=None, comparator=None,
                   quote=a.quote, page=a.page, paragraph_id=a.paragraph_id,
                   notes=a.notes)
    else:  # extraction_failed
        if a.page is None and not a.paragraph_id:
            return fail("extraction_failed requires a location (--page or "
                        "--paragraph-id) so a human can take over")
        if not a.notes:
            return fail("extraction_failed requires --notes: what is "
                        "unreadable and what to check manually")
        rec.update(status="extraction_failed", scalar=a.scalar, units=a.units,
                   quote=a.quote, page=a.page, paragraph_id=a.paragraph_id,
                   notes=a.notes)
    # refresh overall status + uncertainties mirror
    sts = [r["status"] for r in frs]
    if all(s == "reported" for s in sts):
        d["status"] = "answered"
    elif all(s in ("not_reported", "extraction_failed") for s in sts) and \
            "skeleton" in " ".join(str(r.get("notes")) for r in frs):
        d["status"] = "partial"
    else:
        d["status"] = "partial"
    d["uncertainties"] = [
        {"field_id": r["field_id"], "status": r["status"], "notes": r.get("notes")}
        for r in frs if r["status"] != "reported"
    ]
    save(a.output, d)
    print("set %s -> %s" % (a.field, a.status))
    return 0


def cmd_claim(a):
    if a.kind not in CLAIM_KINDS:
        return fail("claim kind must be one of %s" % sorted(CLAIM_KINDS))
    if not a.quote or a.page is None:
        return fail("claim requires --quote and --page (evidence location)")
    d = load(a.output)
    d["claims"].append({
        "kind": a.kind, "text": a.text,
        "evidence": {"quote": a.quote, "page": a.page,
                     "paragraph_id": a.paragraph_id},
        "source_id": a.source_id or "MAIN",
        "location": "page %s%s" % (a.page,
                                   ("/" + a.paragraph_id) if a.paragraph_id else ""),
    })
    save(a.output, d)
    print("claim added (%s)" % a.kind)
    return 0


def cmd_check(a):
    d = load(a.output)
    errors, warns = [], []
    for k in ("case_id", "status", "result", "claims", "uncertainties"):
        if k not in d or d[k] is None and k != "claims":
            errors.append("missing/empty contract key: %s" % k)
    if not d.get("case_id"):
        errors.append("case_id missing")
    if d.get("status") not in OVERALL:
        errors.append("status %r not in %s" % (d.get("status"), sorted(OVERALL)))
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
            continue
        if st == "reported":
            if not r.get("scalar") or r.get("scalar") not in (r.get("quote") or ""):
                errors.append("%s: scalar not verbatim in quote" % fid)
            if NUMERIC.search(r.get("scalar") or "") and not r.get("condition"):
                errors.append("%s: numeric value without condition" % fid)
        if st == "not_reported" and not r.get("notes"):
            errors.append("%s: not_reported without searched-terms notes" % fid)
    for c in d.get("claims", []):
        if c.get("kind") not in CLAIM_KINDS:
            errors.append("claim with bad kind: %r" % c.get("kind"))
        ev = c.get("evidence") or {}
        if not ev.get("quote") or ev.get("page") is None:
            errors.append("claim without located evidence: %s" % str(c)[:60])
        if c.get("kind") == "conclusion" and re.search(
                r"\b(may|might|suggests?|possibly)\b|可能|提示", c.get("text", "")):
            warns.append("conclusion contains hedge words: %s" % c["text"][:60])
    unc_fids = {u.get("field_id") for u in d.get("uncertainties", [])}
    for r in frs:
        if r.get("status") != "reported" and r.get("field_id") not in unc_fids:
            warns.append("%s (%s) not mirrored in uncertainties"
                         % (r["field_id"], r["status"]))
    if d.get("status") == "answered" and any(
            r.get("status") != "reported" for r in frs):
        errors.append("status=answered but not all fields reported")
    for e in errors:
        print("ERROR: %s" % e)
    for w in warns:
        print("WARN: %s" % w)
    print("check: %s (%d fields, %d errors, %d warnings)" % (
        "PASS" if not errors else "FAIL", len(frs), len(errors), len(warns)))
    return 0 if not errors else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("draft")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("set")
    p.add_argument("--output", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--scalar")
    p.add_argument("--units")
    p.add_argument("--statistic")
    p.add_argument("--condition")
    p.add_argument("--comparator")
    p.add_argument("--quote")
    p.add_argument("--page", type=int)
    p.add_argument("--paragraph-id")
    p.add_argument("--notes")
    p = sub.add_parser("claim")
    p.add_argument("--output", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--quote", required=True)
    p.add_argument("--page", type=int, required=True)
    p.add_argument("--paragraph-id")
    p.add_argument("--source-id")
    p = sub.add_parser("check")
    p.add_argument("--output", required=True)
    a = ap.parse_args()
    return {"draft": cmd_draft, "set": cmd_set,
            "claim": cmd_claim, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
