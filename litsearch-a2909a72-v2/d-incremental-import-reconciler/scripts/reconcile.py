#!/usr/bin/env python3
"""Incremental import reconciliation engine (incremental-import-reconciler).

Literature retrieval is treated as a *stateful import*: an organizer-local prior
import state already exists, and a new candidate pool (Crossref / EuropePMC /
OpenAlex shaped snapshots saved on disk) must be reconciled against it
record-by-record. Every candidate is classified with an auditable reason code:

  ALREADY_IMPORTED  identity match (DOI, else normalized title) + identical
                    content fingerprint        -> skipped, ledgered
  UPDATED           identity match, fingerprint differs -> field-level diff,
                    applied to state with a change record
  NEW               no match in state          -> imported
  CONFLICT          same DOI but contradictory title, or same normalized title
                    but different DOI          -> NOT imported; queued for
                    human resolution with both records shown
  SUSPECT           no DOI and no title, or implausible year -> excluded

Only NEW and UPDATED are ever applied. Conflicts wait for a human; suspects are
excluded with a reason. A corrupt prior-state file aborts the run loudly (exit
3) - silently starting over would re-import everything.

Exit codes: 0 ok | 1 idempotency assertion failed | 2 empty candidate pool |
3 prior state corrupt / unreadable.

Fully offline, Python 3 standard library only.

Usage:
  reconcile.py --case /input/case.json --input /input [--corpus DIR] \
      --out /app/output [--verify-idempotent]
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

CORE_FIELDS = ("title", "year", "venue", "authors", "abstract")

# Filename fragments (lowercased) that plausibly hold a prior import state.
STATE_FILE_HINTS = ("import_state", "imported", "state", "library")
# Top-level JSON keys under which state entries may live.
STATE_KEYS = ("imported", "records", "state", "entries", "library")
# Keys inside case.json that may embed the prior state directly.
CASE_STATE_KEYS = ("import_state", "already_imported", "existing_library")

YEAR_MIN, YEAR_MAX = 1450, 2100
STATE_SCHEMA = "incremental-import-reconciler/state/v1"


# --------------------------------------------------------------------------
# small utilities

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha12_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def ws(s):
    """Whitespace-collapsed, stripped string (None-safe)."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def fp_norm(s):
    """Field normalization used inside the content fingerprint."""
    return ws(s).lower()


def norm_doi(raw):
    if not raw:
        return ""
    d = str(raw).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip().rstrip(".")


def title_key(raw):
    """Match key for titles: case/punctuation/space-insensitive, CJK kept."""
    return re.sub(r"[\W_]+", "", str(raw or "").lower())


def plausible_year(year):
    return isinstance(year, int) and YEAR_MIN <= year <= YEAR_MAX


def fingerprint(rec):
    """Content fingerprint: sha256 (first 12 hex) of the normalized core
    fields. Applied identically to state entries and candidates."""
    parts = [
        fp_norm(rec.get("title")),
        str(rec.get("year") or ""),
        fp_norm(rec.get("venue")),
        ";".join(fp_norm(a) for a in (rec.get("authors") or [])),
        fp_norm(rec.get("abstract")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def strip_tags(s):
    return re.sub(r"<[^>]+>", " ", str(s or ""))


# --------------------------------------------------------------------------
# candidate pool: shape detection + record normalization

def shape_records(obj):
    """Return (shape_name, raw_record_list) for a recognized snapshot, None."""
    if not isinstance(obj, dict):
        return None
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("items"), list):
        return "crossref", msg["items"]
    if isinstance(msg, dict) and msg.get("DOI"):
        return "crossref-single", [msg]
    rl = obj.get("resultList")
    if isinstance(rl, dict) and isinstance(rl.get("result"), list):
        return "europepmc", rl["result"]
    if isinstance(obj.get("results"), list):
        return "openalex", obj["results"]
    if isinstance(obj.get("records"), list):
        return "generic-records", obj["records"]
    return None


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _openalex_abstract(inv):
    if not isinstance(inv, dict):
        return ""
    pos = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    return " ".join(w for _i, w in sorted(pos))


def normalize_record(raw, shape):
    """Normalize one raw record of a known shape into the common record."""
    rec = {"title": "", "authors": [], "year": None, "venue": "",
           "doi": "", "abstract": ""}
    if not isinstance(raw, dict):
        return rec
    if shape.startswith("crossref"):
        rec["title"] = ws(_first(raw.get("title")))
        for a in raw.get("author") or []:
            if isinstance(a, dict):
                name = ws("%s %s" % (a.get("given", ""), a.get("family", "")))
            else:
                name = ws(a)
            if name:
                rec["authors"].append(name)
        issued = raw.get("issued") or raw.get("published") or {}
        parts = issued.get("date-parts") if isinstance(issued, dict) else None
        if parts and parts[0]:
            rec["year"] = _to_int(parts[0][0])
        rec["venue"] = ws(_first(raw.get("container-title")))
        rec["doi"] = norm_doi(raw.get("DOI"))
        rec["abstract"] = ws(strip_tags(raw.get("abstract")))
    elif shape == "europepmc":
        rec["title"] = ws(raw.get("title"))
        rec["authors"] = [ws(a) for a in
                          str(raw.get("authorString") or "").split(",") if ws(a)]
        rec["year"] = _to_int(raw.get("pubYear"))
        jinfo = raw.get("journalInfo") or {}
        journal = jinfo.get("journal") or {}
        rec["venue"] = ws(raw.get("journalTitle") or journal.get("title"))
        rec["doi"] = norm_doi(raw.get("doi"))
        rec["abstract"] = ws(strip_tags(raw.get("abstractText")))
    elif shape == "openalex":
        rec["title"] = ws(raw.get("display_name") or raw.get("title"))
        for a in raw.get("authorships") or []:
            name = ws((a.get("author") or {}).get("display_name"))
            if name:
                rec["authors"].append(name)
        rec["year"] = _to_int(raw.get("publication_year"))
        loc = raw.get("primary_location") or {}
        rec["venue"] = ws((loc.get("source") or {}).get("display_name"))
        rec["doi"] = norm_doi(raw.get("doi"))
        rec["abstract"] = ws(raw.get("abstract")
                             or _openalex_abstract(raw.get("abstract_inverted_index")))
    else:  # generic-records
        rec["title"] = ws(_first(raw.get("title")))
        authors = raw.get("authors") or raw.get("author") or []
        if isinstance(authors, str):
            authors = [authors]
        rec["authors"] = [ws(a) for a in authors if ws(a)]
        rec["year"] = _to_int(raw.get("year"))
        rec["venue"] = ws(raw.get("venue") or raw.get("journal")
                          or raw.get("container_title"))
        rec["doi"] = norm_doi(raw.get("doi"))
        rec["abstract"] = ws(strip_tags(raw.get("abstract")))
    return rec


def collect_pool(dirs, exclude_paths):
    """Walk dirs for snapshots; return (candidates, consulted, skipped)."""
    candidates, consulted, skipped = [], [], []
    idx = 0
    for base in dirs:
        if not base or not os.path.isdir(base):
            continue
        for dirpath, _sub, files in os.walk(base):
            for fn in sorted(files):
                if not fn.lower().endswith(".json"):
                    continue
                path = os.path.join(dirpath, fn)
                apath = os.path.abspath(path)
                if apath in exclude_paths or fn in ("case.json", "result.json"):
                    continue
                consulted.append(apath)
                try:
                    with open(apath, encoding="utf-8") as fh:
                        obj = json.load(fh)
                except (OSError, ValueError) as exc:
                    skipped.append({"file": apath, "reason": "PARSE_ERROR",
                                    "detail": str(exc)[:200]})
                    continue
                shaped = shape_records(obj)
                if shaped is None:
                    skipped.append({"file": apath,
                                    "reason": "SCHEMA_UNRECOGNIZED",
                                    "detail": "no known snapshot shape"})
                    continue
                shape, raws = shaped
                for j, raw in enumerate(raws):
                    rec = normalize_record(raw, shape)
                    rec["fingerprint"] = fingerprint(rec)
                    rec["pool_index"] = idx
                    rec["source_file"] = apath
                    rec["json_index"] = j
                    rec["shape"] = shape
                    candidates.append(rec)
                    idx += 1
    return candidates, consulted, skipped


# --------------------------------------------------------------------------
# prior import state: discovery + loading

def entries_from_state_obj(obj, origin):
    """Extract {state_key: normalized entry} from a state object.

    Raises ValueError when a recognized state key holds malformed data -
    that is a corrupt state and must abort loudly, never silently reset.
    """
    for key in STATE_KEYS:
        if isinstance(obj, dict) and key in obj:
            blob = obj[key]
            items = []
            if isinstance(blob, dict):
                items = list(blob.items())
            elif isinstance(blob, list):
                items = [(None, e) for e in blob]
            else:
                raise ValueError("state key %r is neither object nor list" % key)
            entries = {}
            for n, (raw_key, e) in enumerate(items):
                if not isinstance(e, dict):
                    raise ValueError("state entry %d is not an object" % n)
                ent = {
                    "doi": norm_doi(e.get("doi") or e.get("DOI")),
                    "title": ws(_first(e.get("title"))),
                    "year": _to_int(e.get("year")),
                    "venue": ws(e.get("venue") or e.get("journal")),
                    "authors": e.get("authors") or e.get("author") or [],
                    "abstract": ws(strip_tags(e.get("abstract"))),
                    "imported_at": e.get("imported_at"),
                    "source": e.get("source") or origin,
                    "provenance": e.get("provenance"),
                }
                if isinstance(ent["authors"], str):
                    ent["authors"] = [ent["authors"]]
                ent["authors"] = [ws(a) for a in ent["authors"] if ws(a)]
                # a stored fingerprint is advisory only; recompute so both
                # sides of the comparison always use the same definition
                ent["fingerprint"] = fingerprint(ent)
                if ent["doi"]:
                    skey = "doi:" + ent["doi"]
                elif title_key(ent["title"]):
                    skey = "title:" + title_key(ent["title"])
                else:
                    skey = "anon:%s" % hashlib.sha256(
                        json.dumps(e, sort_keys=True).encode()).hexdigest()[:12]
                entries[skey] = ent
            return entries
    return None


def load_state_file(path):
    """Load a state file; any parse/shape failure is fatal (exit 3)."""
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            "FATAL: prior import state %s is unreadable/corrupt (%s).\n"
            "Refusing to fall back to an empty state - that would silently\n"
            "re-import everything. Fix or remove the file and re-run.\n"
            % (path, exc))
        sys.exit(3)
    try:
        entries = entries_from_state_obj(obj, "file:" + path)
    except ValueError as exc:
        sys.stderr.write("FATAL: prior import state %s is malformed: %s\n"
                         % (path, exc))
        sys.exit(3)
    if entries is None:
        sys.stderr.write(
            "FATAL: %s was explicitly given as import state but holds no "
            "recognized state key %s.\n" % (path, STATE_KEYS))
        sys.exit(3)
    return entries


def discover_state(case_obj, input_dirs):
    """Find the prior import state.

    Returns (entries, origin, state_files, notes). Never fabricates a state:
    when nothing is found, returns an empty state and the caller runs in
    'initial import' mode, saying so in every artifact.
    """
    notes = []
    if case_obj:
        for key in CASE_STATE_KEYS:
            if key in case_obj:
                try:
                    entries = entries_from_state_obj(case_obj[key]
                                                     if isinstance(case_obj[key], dict)
                                                     else {key: case_obj[key]},
                                                     "case.json:" + key)
                except ValueError as exc:
                    sys.stderr.write(
                        "FATAL: import state embedded in case.json key %r is "
                        "malformed: %s\n" % (key, exc))
                    sys.exit(3)
                if entries is not None:
                    notes.append("prior state embedded in case.json key %r" % key)
                    return entries, "case.json:" + key, [], notes
    name_hits = []
    for base in input_dirs:
        if not base or not os.path.isdir(base):
            continue
        for dirpath, _sub, files in os.walk(base):
            for fn in sorted(files):
                low = fn.lower()
                if low.endswith(".json") and any(h in low for h in STATE_FILE_HINTS):
                    name_hits.append(os.path.join(dirpath, fn))
    for path in sorted(name_hits):
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.stderr.write(
                "FATAL: %s looks like a prior import state by name but is "
                "corrupt (%s). Refusing to silently start over.\n" % (path, exc))
            sys.exit(3)
        try:
            entries = entries_from_state_obj(obj, "file:" + path)
        except ValueError as exc:
            sys.stderr.write("FATAL: prior import state %s is malformed: %s\n"
                             % (path, exc))
            sys.exit(3)
        if entries is not None:
            if len(name_hits) > 1:
                notes.append("multiple state-like files %s; used %s (sorted first)"
                             % ([os.path.basename(p) for p in name_hits], path))
            return entries, "file:" + path, [os.path.abspath(path)], notes
        notes.append("ignored %s: state-like name but no recognized state key"
                     % path)
    notes.append("no prior import state found: running in INITIAL IMPORT mode; "
                 "every candidate classifies as NEW")
    return {}, "none", [], notes


# --------------------------------------------------------------------------
# classification + application

def build_indexes(entries):
    by_doi, by_title = {}, {}
    for skey, ent in entries.items():
        if ent["doi"]:
            by_doi[ent["doi"]] = skey
        tk = title_key(ent["title"])
        if tk:
            by_title[tk] = skey
    return by_doi, by_title


def diff_fields(old, new):
    """Field-level diff over CORE_FIELDS (normalized comparison)."""
    diffs = []
    for field in CORE_FIELDS:
        ov, nv = old.get(field), new.get(field)
        if field == "authors":
            same = [fp_norm(a) for a in (ov or [])] == [fp_norm(a) for a in (nv or [])]
        elif field == "year":
            same = (ov or None) == (nv or None)
        else:
            same = fp_norm(ov) == fp_norm(nv)
        if not same:
            diffs.append({"field": field,
                          "old": ov if ov not in (None, "", []) else None,
                          "new": nv if nv not in (None, "", []) else None})
    return diffs


def brief(rec):
    return {"doi": rec.get("doi") or None, "title": rec.get("title") or None,
            "year": rec.get("year"), "venue": rec.get("venue") or None,
            "fingerprint": rec.get("fingerprint")}


def classify(cand, entries, by_doi, by_title):
    """Classify one candidate against the state. Returns a decision dict."""
    dec = {"pool_index": cand["pool_index"], "doi": cand["doi"] or None,
           "title": cand["title"] or None, "year": cand["year"],
           "fingerprint": cand["fingerprint"],
           "source_file": cand["source_file"], "json_index": cand["json_index"],
           "matched_state_key": None, "diff": None, "conflict": None}
    if not cand["doi"] and not cand["title"]:
        dec.update(action="SUSPECT", reason_code="NO_IDENTIFIER",
                   reason="record has neither DOI nor title; cannot be matched "
                          "or imported safely")
        return dec
    if cand["year"] is not None and not plausible_year(cand["year"]):
        dec.update(action="SUSPECT", reason_code="YEAR_IMPLAUSIBLE",
                   reason="year %r outside %d-%d" % (cand["year"], YEAR_MIN, YEAR_MAX))
        return dec
    skey, via = None, None
    if cand["doi"] and cand["doi"] in by_doi:
        skey, via = by_doi[cand["doi"]], "doi"
    else:
        tk = title_key(cand["title"])
        if tk and tk in by_title:
            skey, via = by_title[tk], "title"
    if skey is None:
        dec.update(action="NEW", reason_code="NO_STATE_MATCH",
                   reason="no DOI or normalized-title match in prior state")
        return dec
    st = entries[skey]
    dec["matched_state_key"] = skey
    if via == "doi":
        stk, ctk = title_key(st["title"]), title_key(cand["title"])
        if stk and ctk and stk != ctk:
            dec.update(action="CONFLICT", reason_code="DOI_MATCH_TITLE_MISMATCH",
                       reason="DOI already in state but titles disagree; queued "
                              "for human resolution, NOT imported",
                       conflict={"state_record": brief(st),
                                 "candidate_record": brief(cand)})
            return dec
    else:
        if cand["doi"] and st["doi"] and cand["doi"] != st["doi"]:
            dec.update(action="CONFLICT", reason_code="TITLE_MATCH_DOI_MISMATCH",
                       reason="normalized title already in state under a "
                              "different DOI; queued for human resolution, "
                              "NOT imported",
                       conflict={"state_record": brief(st),
                                 "candidate_record": brief(cand)})
            return dec
    if st["fingerprint"] == cand["fingerprint"]:
        dec.update(action="ALREADY_IMPORTED",
                   reason_code=("DOI_MATCH_IDENTICAL" if via == "doi"
                                else "TITLE_MATCH_IDENTICAL"),
                   reason="identity match with identical content fingerprint; skipped")
        return dec
    dec.update(action="UPDATED",
               reason_code=("DOI_MATCH_CONTENT_CHANGED" if via == "doi"
                            else "TITLE_MATCH_CONTENT_CHANGED"),
               reason="identity match but content fingerprint differs; applied "
                      "as an update",
               diff=diff_fields(st, cand))
    return dec


def apply_decisions(decisions, candidates, entries, ts):
    """Apply NEW/UPDATED decisions to a copy of the state. Returns
    (new_state, change_records)."""
    state = {k: dict(v) for k, v in entries.items()}
    changes = []
    seq = 0
    for dec, cand in zip(decisions, candidates):
        if dec["action"] == "NEW":
            skey = ("doi:" + cand["doi"] if cand["doi"]
                    else "title:" + title_key(cand["title"]))
            state[skey] = {
                "doi": cand["doi"], "title": cand["title"],
                "year": cand["year"], "venue": cand["venue"],
                "authors": cand["authors"], "abstract": cand["abstract"],
                "fingerprint": cand["fingerprint"],
                "imported_at": ts, "updated_at": None,
                "source": "reconcile:add",
                "provenance": {"file": cand["source_file"],
                               "json_index": cand["json_index"]},
            }
            seq += 1
            changes.append({"change_id": "CHG-%04d" % seq, "ts": ts, "kind": "add",
                            "state_key": skey, "doi": cand["doi"] or None,
                            "title": cand["title"], "fingerprint": cand["fingerprint"],
                            "diff": None,
                            "provenance": {"file": cand["source_file"],
                                           "json_index": cand["json_index"]}})
            dec["state_key"] = skey
        elif dec["action"] == "UPDATED":
            skey = dec["matched_state_key"]
            prev = state[skey]
            state[skey] = dict(prev, **{
                "doi": cand["doi"] or prev["doi"], "title": cand["title"],
                "year": cand["year"], "venue": cand["venue"],
                "authors": cand["authors"], "abstract": cand["abstract"],
                "fingerprint": cand["fingerprint"],
                "updated_at": ts, "previous_fingerprint": prev["fingerprint"],
                "source": "reconcile:update",
                "provenance": {"file": cand["source_file"],
                               "json_index": cand["json_index"]},
            })
            seq += 1
            changes.append({"change_id": "CHG-%04d" % seq, "ts": ts, "kind": "update",
                            "state_key": skey, "doi": cand["doi"] or None,
                            "title": cand["title"], "fingerprint": cand["fingerprint"],
                            "previous_fingerprint": prev["fingerprint"],
                            "diff": dec["diff"],
                            "provenance": {"file": cand["source_file"],
                                           "json_index": cand["json_index"]}})
    return state, changes


# --------------------------------------------------------------------------
# artifact writers

def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def render_report(ctx):
    counts = ctx["counts"]
    L = []
    L.append("# Reconciliation report — incremental-import-reconciler")
    L.append("")
    L.append("- generated_at: `%s`" % ctx["generated_at"])
    L.append("- mode: **%s**%s" % (ctx["mode"],
             " (no prior state found; everything classified as NEW)"
             if ctx["mode"] == "initial" else ""))
    L.append("- state origin: `%s` (%d entries)" % (ctx["state_origin"],
                                                    ctx["state_entries"]))
    L.append("- pool: %d candidate(s) from %d file(s); %d file(s) skipped"
             % (ctx["candidates"], len(ctx["pool_files"]), len(ctx["skipped"])))
    L.append("")
    L.append("## Counts")
    L.append("")
    L.append("| action | count |")
    L.append("|-|-|")
    for k in ("ALREADY_IMPORTED", "UPDATED", "NEW", "CONFLICT", "SUSPECT"):
        L.append("| %s | %d |" % (k, counts.get(k, 0)))
    L.append("| **total candidates** | %d |" % ctx["candidates"])
    L.append("")

    def row(dec):
        return "- `%s` fp `%s` — %s (%s)" % (
            dec["doi"] or dec["title"], dec["fingerprint"],
            dec["title"] or "(no title)", dec["reason_code"])

    adds = [d for d in ctx["decisions"] if d["action"] == "NEW"]
    L.append("## Added (%d)" % len(adds))
    L.append("")
    L.extend(row(d) for d in adds) if adds else L.append("_none_")
    L.append("")

    ups = [d for d in ctx["decisions"] if d["action"] == "UPDATED"]
    L.append("## Updated (%d)" % len(ups))
    L.append("")
    if not ups:
        L.append("_none_")
    for d in ups:
        L.append("- `%s` (state key `%s`):" % (d["doi"] or d["title"],
                                               d["matched_state_key"]))
        for df in d["diff"] or []:
            ov, nv = df["old"], df["new"]
            if df["field"] == "authors":
                ov = "; ".join(ov or []) or None
                nv = "; ".join(nv or []) or None
            if df["field"] == "abstract":
                ov = (str(ov)[:120] + "…") if ov else None
                nv = (str(nv)[:120] + "…") if nv else None
            L.append("  - **%s**: `%s` → `%s`" % (df["field"], ov, nv))
    L.append("")

    skips = [d for d in ctx["decisions"] if d["action"] == "ALREADY_IMPORTED"]
    L.append("## Already imported — skipped (%d)" % len(skips))
    L.append("")
    L.extend(row(d) for d in skips) if skips else L.append("_none_")
    L.append("")

    confs = [d for d in ctx["decisions"] if d["action"] == "CONFLICT"]
    L.append("## Conflict queue — NOT imported, awaiting human resolution (%d)"
             % len(confs))
    L.append("")
    if not confs:
        L.append("_none_")
    for d in confs:
        st, ca = d["conflict"]["state_record"], d["conflict"]["candidate_record"]
        L.append("- **%s** on candidate `%s`:" % (d["reason_code"],
                                                  d["doi"] or d["title"]))
        L.append("  - in state: title=%r, doi=%r, year=%r, venue=%r, fp `%s`"
                 % (st["title"], st["doi"], st["year"], st["venue"],
                    st["fingerprint"]))
        L.append("  - candidate: title=%r, doi=%r, year=%r, venue=%r, fp `%s` (from %s)"
                 % (ca["title"], ca["doi"], ca["year"], ca["venue"],
                    ca["fingerprint"], d["source_file"]))
        L.append("  - resolution requires a human: pick the authoritative "
                 "identity, then re-run")
    L.append("")

    susp = [d for d in ctx["decisions"] if d["action"] == "SUSPECT"]
    L.append("## Suspect — excluded with reason (%d)" % len(susp))
    L.append("")
    if not susp:
        L.append("_none_")
    for d in susp:
        L.append("- pool_index %d from %s: **%s** — %s"
                 % (d["pool_index"], d["source_file"], d["reason_code"],
                    d["reason"]))
    L.append("")

    L.append("## Notes (honest)")
    L.append("")
    for n in ctx["notes"]:
        L.append("- %s" % n)
    for s in ctx["skipped"]:
        L.append("- skipped pool file `%s`: %s (%s)"
                 % (s["file"], s["reason"], s["detail"]))
    L.append("- title-only matching (when a side lacks a DOI) is normalized "
             "string equality, not semantic matching")
    L.append("- conflicts are never auto-merged; the state is unchanged for "
             "every queued conflict")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# main reconciliation driver (used by both the run and the verification pass)

def reconcile_pool(entries, candidates):
    by_doi, by_title = build_indexes(entries)
    return [classify(c, entries, by_doi, by_title) for c in candidates]


def run(args):
    case_obj, case_path = None, None
    evidence_files = []
    if args.case:
        case_path = os.path.abspath(args.case)
        with open(case_path, encoding="utf-8") as fh:
            case_obj = json.load(fh)
        evidence_files.append((case_path, "case"))

    input_dirs = [args.input] + ([args.corpus] if args.corpus else [])
    entries, origin, state_files, notes = discover_state(case_obj, input_dirs)
    mode = "initial" if origin == "none" else "incremental"
    for p in state_files:
        evidence_files.append((p, "state"))

    candidates, consulted, skipped = collect_pool(
        input_dirs, exclude_paths=set(state_files) | {case_path or ""})
    for p in consulted:
        evidence_files.append((p, "pool"))

    decisions = reconcile_pool(entries, candidates)
    counts = {}
    for d in decisions:
        counts[d["action"]] = counts.get(d["action"], 0) + 1

    ts = utcnow()
    new_state, changes = apply_decisions(decisions, candidates, entries, ts)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    manifest = {
        "tool": "incremental-import-reconciler",
        "generated_at": ts,
        "mode": mode,
        "state_origin": origin,
        "state_entries": len(entries),
        "counts": counts,
        "decisions": decisions,
    }
    write_json(os.path.join(out, "import_manifest.json"), manifest)

    updated_state = {
        "schema": STATE_SCHEMA,
        "mode": mode,
        "prior_state_origin": origin,
        "generated_at": ts,
        "imported": new_state,
    }
    write_json(os.path.join(out, "updated_state.json"), updated_state)

    ctx = {"generated_at": ts, "mode": mode, "state_origin": origin,
           "state_entries": len(entries), "candidates": len(candidates),
           "pool_files": consulted, "skipped": skipped, "counts": counts,
           "decisions": decisions, "notes": notes}
    with open(os.path.join(out, "reconciliation_report.md"), "w",
              encoding="utf-8") as fh:
        fh.write(render_report(ctx))

    with open(os.path.join(out, "change_records.jsonl"), "w",
              encoding="utf-8") as fh:
        for ch in changes:
            fh.write(json.dumps(ch, ensure_ascii=False) + "\n")

    evidence = {"generated_at": ts,
                "files": [{"path": p, "role": role,
                           "sha256_12": sha12_file(p),
                           "bytes": os.path.getsize(p)}
                          for p, role in evidence_files]}
    write_json(os.path.join(out, "evidence", "evidence_index.json"), evidence)

    digest = {"ENGINE_STATUS": "success" if candidates else "partial",
              "mode": mode, "state_origin": origin,
              "state_entries": len(entries),
              "pool_files": len(consulted), "candidates": len(candidates),
              "already_imported": counts.get("ALREADY_IMPORTED", 0),
              "updated": counts.get("UPDATED", 0),
              "new": counts.get("NEW", 0),
              "conflicts": counts.get("CONFLICT", 0),
              "suspects": counts.get("SUSPECT", 0),
              "pool_files_skipped": len(skipped),
              "out": out}
    print(json.dumps(digest, ensure_ascii=False))

    if not candidates:
        sys.stderr.write("candidate pool is empty; wrote partial artifacts "
                         "and an unchanged state copy\n")
        return 2

    if args.verify_idempotent:
        return verify_idempotent(args, state_files, case_obj)
    return 0


def verify_idempotent(args, state_files, case_obj):
    """A REAL second execution: reload the just-written updated_state.json
    from disk, re-collect the same pool, re-classify, and assert that the
    second pass is change-free (0 adds, 0 updates). Conflicts may persist -
    they are queued, never applied, hence not state changes."""
    state_path = os.path.join(os.path.abspath(args.out), "updated_state.json")
    if not os.path.isfile(state_path):
        sys.stderr.write("VERIFY FAILED: %s does not exist; run the "
                         "reconciliation first\n" % state_path)
        return 1
    entries2 = load_state_file(state_path)
    input_dirs = [args.input] + ([args.corpus] if args.corpus else [])
    candidates2, _c, _s = collect_pool(
        input_dirs, exclude_paths={os.path.abspath(state_path)})
    decisions2 = reconcile_pool(entries2, candidates2)
    adds = [d for d in decisions2 if d["action"] == "NEW"]
    ups = [d for d in decisions2 if d["action"] == "UPDATED"]
    confs = [d for d in decisions2 if d["action"] == "CONFLICT"]
    if not adds and not ups:
        print("IDEMPOTENT: second pass = 0 adds, 0 updates")
        return 0
    sys.stderr.write("VERIFY FAILED: second pass against updated_state.json "
                     "is not change-free:\n")
    for d in adds:
        sys.stderr.write("  unexpected ADD: %s (%s)\n"
                         % (d["doi"] or d["title"], d["fingerprint"]))
    for d in ups:
        sys.stderr.write("  unexpected UPDATE: %s (%s) diff=%s\n"
                         % (d["doi"] or d["title"], d["fingerprint"], d["diff"]))
    sys.stderr.write("  (recurring conflicts: %d - expected, still queued)\n"
                     % len(confs))
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="case.json (optional; consulted for an "
                                   "embedded import state and the evidence index)")
    ap.add_argument("--input", required=True,
                    help="directory with organizer material (state + snapshots)")
    ap.add_argument("--corpus", help="optional extra directory with agent-saved "
                                     "raw snapshot responses")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--verify-idempotent", action="store_true",
                    help="after the run, re-execute reconciliation against the "
                         "just-written updated_state.json and assert zero "
                         "adds/updates")
    args = ap.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
