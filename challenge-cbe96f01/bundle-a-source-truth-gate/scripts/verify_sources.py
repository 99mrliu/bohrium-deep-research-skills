#!/usr/bin/env python3
"""verify_sources.py -- source-truth-gate stage 1b: seven-state source gate.

Verifies every reference entry against a trusted metadata snapshot (JSON).
States (see references/verdict_states.md):
  verified | metadata_conflict | not_found_in_snapshot |
  suspected_fabricated | retraction_flagged | version_mismatch | not_checked

Snapshot record schema (list under key "records"):
  {"doi": "...", "title": "...", "first_author": "...", "year": 2021,
   "status": "published|preprint|retracted|corrected",
   "version_of": "10.xxxx/published-doi (optional, on preprint records)",
   "note": "optional human note"}

With --online, entries carrying a syntactically valid DOI are queried
against the public Crossref API (stdlib urllib, short timeout, at most one
retry is NOT performed -- failures are recorded and degrade to the
snapshot/offline path). Query responses are cached next to --out so the
run log can cite them.

Exit code 1 if any entry lands in suspected_fabricated, metadata_conflict,
retraction_flagged or version_mismatch; else 0. Never deletes entries.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HARD_STATES = {"suspected_fabricated", "metadata_conflict",
               "retraction_flagged", "version_mismatch"}


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(r"[^a-z0-9一-鿿]+", " ", s).strip()


def token_overlap(a, b):
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def load_snapshot(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    records = data.get("records", data if isinstance(data, list) else [])
    by_doi = {}
    by_title = {}
    for r in records:
        if r.get("doi"):
            by_doi[r["doi"].lower()] = r
        if r.get("title"):
            by_title[norm(r["title"])] = r
    return {"records": records, "by_doi": by_doi, "by_title": by_title,
            "source": data.get("source", "case-supplied") if isinstance(data, dict) else "case-supplied"}


def crossref_lookup(doi, cache):
    if doi in cache:
        return cache[doi]
    url = ("https://api.crossref.org/works/" +
           urllib.parse.quote(doi, safe=""))
    rec = None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "source-truth-gate/1.0 (audit)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.load(resp)
        m = payload.get("message", {})
        title = (m.get("title") or [""])[0]
        year = None
        for k in ("published-print", "published-online", "issued"):
            if m.get(k, {}).get("date-parts"):
                year = m[k]["date-parts"][0][0]
                break
        author = None
        if m.get("author"):
            author = m["author"][0].get("family")
        status = "published"
        rel = m.get("relation", {})
        rec = {"doi": doi.lower(), "title": title, "first_author": author,
               "year": year, "status": status,
               "source": "crossref-online",
               "queried_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())}
        if m.get("subtype") == "preprint":
            rec["status"] = "preprint"
            upd = (rel.get("is-preprint-of") or rel.get("has-published-version") or [])
            if upd and upd[0].get("id"):
                rec["version_of"] = upd[0]["id"]
        if rel.get("is-retraction-of") or m.get("update-to"):
            for u in m.get("update-to", []):
                if "retract" in str(u.get("type", "")).lower():
                    rec["status"] = "retracted"
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
            TimeoutError, KeyError) as exc:
        rec = {"doi": doi.lower(), "error": f"crossref query failed: {exc}",
               "source": "crossref-online",
               "queried_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())}
    cache[doi] = rec
    return rec


def judge(entry, snap, online, cache):
    reasons = []
    cand = None
    lookup_note = "snapshot"
    if snap:
        if entry.get("doi") and entry["doi"].lower() in snap["by_doi"]:
            cand = snap["by_doi"][entry["doi"].lower()]
        elif entry.get("title_guess"):
            t = norm(entry["title_guess"])
            if t in snap["by_title"]:
                cand = snap["by_title"][t]
    if cand is None and online and entry.get("doi") \
            and entry.get("doi_syntax_ok"):
        rec = crossref_lookup(entry["doi"], cache)
        if rec and "error" not in rec:
            cand = rec
            lookup_note = "crossref-online"
        elif rec:
            reasons.append(rec["error"])

    if cand is None:
        if snap is None and not online:
            return "not_checked", reasons + ["no snapshot and no online lookup"]
        if entry.get("doi") and not entry.get("doi_syntax_ok"):
            return "suspected_fabricated", reasons + [
                "not found in trusted source AND DOI syntax invalid"]
        if not entry.get("doi") and not entry.get("parse_ok"):
            return "suspected_fabricated", reasons + [
                "not found in trusted source AND entry metadata unparseable"]
        return "not_found_in_snapshot", reasons + [
            "no matching record in trusted source"]

    st = (cand.get("status") or "published").lower()
    if st == "retracted":
        return "retraction_flagged", [
            f"trusted source marks record as retracted: {cand.get('note', '')}"]
    if st == "preprint":
        vo = cand.get("version_of")
        if vo and (not entry.get("doi")
                   or entry["doi"].lower() != vo.lower()):
            return "version_mismatch", [
                f"cited preprint but published version exists: {vo}"]

    conflicts = []
    if cand.get("year") and entry.get("year") \
            and int(cand["year"]) != int(entry["year"]):
        conflicts.append(f"year {entry['year']} vs trusted {cand['year']}")
    if cand.get("first_author") and entry.get("first_author"):
        if norm(cand["first_author"]) != norm(entry["first_author"]):
            conflicts.append(
                f"first author {entry['first_author']} vs trusted "
                f"{cand['first_author']}")
    if cand.get("title") and entry.get("title_guess"):
        ov = token_overlap(cand["title"], entry["title_guess"])
        if ov < 0.4:
            conflicts.append(
                f"title overlap {ov:.2f} < 0.40 vs trusted "
                f"'{cand['title'][:80]}'")
    if conflicts:
        return "metadata_conflict", [f"matched via {lookup_note}"] + conflicts
    return "verified", [f"matched via {lookup_note}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", required=True)
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--online", action="store_true",
                    help="query Crossref for DOI-bearing entries")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.refs, encoding="utf-8") as fh:
        refs = json.load(fh)
    snap = load_snapshot(args.snapshot)
    cache_path = args.out + ".crossref-cache.json"
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}

    report = {"snapshot_source": (snap["source"] if snap else
                                  ("crossref-online" if args.online else "none")),
              "counts": {}, "entries": []}
    for e in refs.get("entries", []):
        state, reasons = judge(e, snap, args.online, cache)
        report["counts"][state] = report["counts"].get(state, 0) + 1
        report["entries"].append({
            "ref_id": e.get("ref_id"), "doi": e.get("doi"),
            "title_guess": e.get("title_guess"), "state": state,
            "reasons": reasons})
    if not refs.get("reference_section_found", True):
        report["warning"] = ("reference section was not located; states are "
                             "computed on rebuilt entries only")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    if args.online:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=2)
    hard = sum(report["counts"].get(s, 0) for s in HARD_STATES)
    print(json.dumps({"counts": report["counts"], "hard_alerts": hard},
                     ensure_ascii=False))
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
