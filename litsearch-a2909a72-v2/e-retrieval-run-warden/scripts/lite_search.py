#!/usr/bin/env python3
"""lite_search.py -- deliberately simple, honest baseline retrieval run.

This is NOT a smart search engine. It exists so that every retrieval run has a
real, auditable artifact trail for the warden (scripts/warden.py) to check,
and so the agent has a working fallback when nothing better is available.

What it does, deterministically and offline (Python 3 stdlib only):
  1. walks --input (organizer material) and optional --corpus (agent-saved raw
     responses) for Crossref / EuropePMC / OpenAlex-shaped JSON snapshots;
  2. copies every consulted snapshot BYTE-IDENTICALLY into
     <work>/run/evidence/<sha256_12>__<basename> -- the evidence pool the
     warden will re-hash and re-scan;
  3. normalizes records (doi / title / abstract / year / source_type);
  4. dedups by DOI, else by normalized title;
  5. scores by LITERAL term presence (title +2, abstract +1) against the case
     research question;
  6. writes <work>/run/candidates.json + candidates.md (each candidate carries
     evidence pointers: source file, json_index, sha256_12) and
     <work>/run/run_log.jsonl (one JSON object per pipeline step, including a
     PRISMA-style flow: identified -> after-dedup -> scored -> included, with
     reason codes for every exclusion).

Usage:
  lite_search.py --case /input/case.json --input /input \
      [--corpus /app/work/corpus] --work /app/work [--out /app/output]

Exit codes: 0 = run completed (>=0 candidates), 2 = zero records identified.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "have", "has", "not", "but", "all", "can", "its", "their", "they", "them",
    "into", "about", "between", "among", "via", "use", "using", "used", "based",
    "study", "studies", "review", "analysis", "effect", "effects", "find",
    "literature", "papers", "paper", "research", "what", "which", "how", "does",
    "recent", "advances", "current", "state", "art", "evidence", "impact",
    "role", "applications", "application", "approach", "approaches", "methods",
}

CJK_RE = re.compile(r"[一-鿿]+")
TOKEN_RE = re.compile(r"[a-z0-9]+")
DOI_RE = re.compile(r"10\.\d{4,9}/\S+")

# files that are never treated as snapshots
SKIP_NAMES = {"case.json", "result.json", "run_log.jsonl", "candidates.json",
              "audit_report.json", "verified_corpus.json"}


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def query_terms(question):
    """Lowercase alnum tokens (len>2, stopword-filtered) + CJK bigrams."""
    terms = []
    for tok in TOKEN_RE.findall((question or "").lower()):
        if len(tok) > 2 and tok not in STOPWORDS and tok not in terms:
            terms.append(tok)
    for run in CJK_RE.findall(question or ""):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in terms:
                terms.append(bg)
    return terms


def classify(payload):
    """Return (source_type, record_list) for a parsed JSON payload."""
    if isinstance(payload, dict):
        msg = payload.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            return "crossref", msg["items"]
        rl = payload.get("resultList")
        if isinstance(rl, dict) and isinstance(rl.get("result"), list):
            return "europepmc", rl["result"]
        if isinstance(payload.get("results"), list):
            return "openalex", payload["results"]
        if isinstance(payload.get("records"), list):
            return "generic-records", payload["records"]
    return None, []


def strip_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.rstrip(".")


def first_str(v):
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v) if v else ""


def normalize_record(rec, source_type):
    """Best-effort flat record; missing metadata stays empty, never invented."""
    rec = rec if isinstance(rec, dict) else {}
    title = first_str(rec.get("title")) or first_str(rec.get("display_name"))
    abstract = rec.get("abstract") or ""
    if isinstance(abstract, str):
        abstract = re.sub(r"<[^>]+>", " ", abstract)
    else:
        abstract = ""
    if not abstract:  # OpenAlex inverted index reconstruction
        inv = rec.get("abstract_inverted_index")
        if isinstance(inv, dict):
            pos = [(i, w) for w, idxs in inv.items() for i in idxs]
            abstract = " ".join(w for _i, w in sorted(pos))
    year = rec.get("publication_year") or rec.get("pubYear") or ""
    if not year:
        dp = ((rec.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = dp[0] or ""
    doi = strip_doi(rec.get("DOI") or rec.get("doi"))
    return {
        "doi": doi,
        "title": re.sub(r"\s+", " ", str(title)).strip(),
        "abstract": re.sub(r"\s+", " ", str(abstract)).strip(),
        "year": str(year),
        "source_type": source_type,
    }


def norm_key(rec):
    if rec["doi"]:
        return "doi:" + rec["doi"]
    t = re.sub(r"[^a-z0-9一-鿿]", "", rec["title"].lower())
    return "title:" + t if t else "anon:" + str(id(rec))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None,
                    help="also copy candidates.md/candidates.json here")
    args = ap.parse_args()

    case = json.load(open(args.case, encoding="utf-8"))
    question = (case.get("research_question") or case.get("question")
                or case.get("query") or "")
    terms = query_terms(question)

    run_dir = os.path.join(args.work, "run")
    ev_dir = os.path.join(run_dir, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    log_path = os.path.join(run_dir, "run_log.jsonl")
    logf = open(log_path, "w", encoding="utf-8")

    def log(step, **kw):
        entry = {"step": step, "ts": utcnow()}
        entry.update(kw)
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()

    # ---- step: discover ------------------------------------------------
    roots = [args.input] + ([args.corpus] if args.corpus else [])
    snap_files = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _d, files in os.walk(root):
            for fn in sorted(files):
                if fn.lower().endswith(".json") and fn not in SKIP_NAMES \
                        and os.path.join(dirpath, fn) != os.path.abspath(args.case):
                    snap_files.append(os.path.join(dirpath, fn))
    log("discover", counts={"out": len(snap_files)},
        notes={"roots": [r for r in roots if r],
               "files": [os.path.basename(f) for f in snap_files]})

    # ---- step: evidence_copy -------------------------------------------
    evidence_map = {}  # original abs path -> {copy_name, sha256_12, bytes}
    for path in snap_files:
        digest = sha256_12(path)
        copy_name = "%s__%s" % (digest, os.path.basename(path))
        copy_path = os.path.join(ev_dir, copy_name)
        if not os.path.isfile(copy_path):
            shutil.copyfile(path, copy_path)  # byte-identical by construction
        evidence_map[os.path.abspath(path)] = {
            "original_path": os.path.abspath(path),
            "copy_name": copy_name,
            "sha256_12": digest,
            "bytes": os.path.getsize(path),
        }
    log("evidence_copy", counts={"in": len(snap_files), "out": len(evidence_map)},
        notes={"evidence_dir": os.path.abspath(ev_dir)})

    # ---- step: ingest ---------------------------------------------------
    records = []  # each: normalized record + provenance
    per_file = []
    for path in snap_files:
        key = os.path.abspath(path)
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception as exc:
            per_file.append({"file": os.path.basename(path), "records": 0,
                             "note": "PARSE_ERROR: %s" % exc})
            continue
        stype, raw_list = classify(payload)
        n = 0
        for idx, raw in enumerate(raw_list):
            rec = normalize_record(raw, stype)
            rec["evidence"] = dict(evidence_map[key])
            rec["evidence"]["json_index"] = idx
            records.append(rec)
            n += 1
        per_file.append({"file": os.path.basename(path), "source_type": stype,
                         "records": n})
    log("ingest", counts={"in": len(evidence_map), "out": len(records)},
        notes={"per_file": per_file})

    # ---- step: dedup -----------------------------------------------------
    winners = {}
    unique = []
    exclusions = []
    for rec in records:
        k = norm_key(rec)
        if k in winners:
            exclusions.append({
                "key": k, "reason": "DUPLICATE_OF",
                "detail": "same dedup key as earlier record from %s"
                          % winners[k]["evidence"]["copy_name"],
                "source": rec["evidence"]["copy_name"],
                "json_index": rec["evidence"]["json_index"],
                "title": rec["title"], "doi": rec["doi"]})
            winners[k].setdefault("also_in", []).append(
                {"copy_name": rec["evidence"]["copy_name"],
                 "json_index": rec["evidence"]["json_index"]})
        else:
            rec["dedup_key"] = k
            winners[k] = rec
            unique.append(rec)
    log("dedup", counts={"in": len(records), "out": len(unique)},
        notes={"duplicates_removed": len(records) - len(unique)})

    # ---- step: score ------------------------------------------------------
    scored = []
    term_hits = {t: 0 for t in terms}
    for rec in unique:
        title_l = rec["title"].lower()
        abs_l = rec["abstract"].lower()
        score = 0
        matched = []
        for t in terms:
            if t in title_l:
                score += 2
                matched.append(t)
                term_hits[t] += 1
            elif t in abs_l:
                score += 1
                matched.append(t)
                term_hits[t] += 1
        rec["score"] = score
        rec["matched_terms"] = matched
        if score > 0:
            scored.append(rec)
        else:
            exclusions.append({
                "key": rec["dedup_key"], "reason": "NO_TERM_MATCH",
                "detail": "literal score 0 against query terms",
                "source": rec["evidence"]["copy_name"],
                "json_index": rec["evidence"]["json_index"],
                "title": rec["title"], "doi": rec["doi"]})
    zero_hit = sorted(t for t, c in term_hits.items() if c == 0)
    scored.sort(key=lambda r: (-r["score"], r["title"].lower()))
    for rank, rec in enumerate(scored, 1):
        rec["rank"] = rank
    log("score", counts={"in": len(unique), "out": len(scored)},
        notes={"query_terms": terms, "zero_hit_terms": zero_hit})

    # ---- step: exclusions ledger -----------------------------------------
    log("exclusions", counts={"out": len(exclusions)},
        notes={"items": exclusions})

    # ---- step: prisma ------------------------------------------------------
    log("prisma", counts={
        "identified": len(records),
        "after_dedup": len(unique),
        "scored": len(scored),
        "included": len(scored),
    }, notes={"flow": "identified -> after-dedup -> scored -> included",
              "excluded_total": len(exclusions)})

    # ---- artifacts ----------------------------------------------------------
    pub = []
    for r in scored:
        entry = {k: r[k] for k in ("rank", "score", "doi", "title", "year",
                                   "source_type", "matched_terms", "evidence",
                                   "dedup_key")}
        entry["also_in"] = r.get("also_in", [])
        pub.append(entry)
    cj = {
        "case_id": case.get("case_id") or case.get("id") or "UNKNOWN",
        "question": question,
        "query_terms": terms,
        "generated_by": "retrieval-run-warden lite_search.py (offline, stdlib)",
        "counts": {"identified": len(records), "after_dedup": len(unique),
                   "included": len(scored), "excluded": len(exclusions)},
        "candidates": pub,
    }
    with open(os.path.join(run_dir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(cj, f, ensure_ascii=False, indent=1)

    lines = ["# Retrieval candidates — case %s" % cj["case_id"], "",
             "Question: %s" % question, "",
             "Query terms: %s" % ", ".join(terms) if terms else "(none)", "",
             "Counts: identified=%d after_dedup=%d included=%d excluded=%d"
             % (len(records), len(unique), len(scored), len(exclusions)), "",
             "Every row cites its evidence copy (byte-identical snapshot under "
             "`run/evidence/`), the record index inside that file, and the "
             "file's sha256_12. A reviewer can re-hash and re-scan each file.", ""]
    for r in scored:
        ev = r["evidence"]
        lines.append("## %d. %s" % (r["rank"], r["title"] or "(no title)"))
        lines.append("- score: %d | year: %s | source: %s"
                     % (r["score"], r["year"] or "?", r["source_type"]))
        lines.append("- doi: %s" % (r["doi"] or "(none)"))
        lines.append("- matched_terms: %s" % ", ".join(r["matched_terms"]))
        lines.append("- evidence: `%s` json_index=%d sha256_12=%s"
                     % (ev["copy_name"], ev["json_index"], ev["sha256_12"]))
        if r.get("also_in"):
            lines.append("- also_in: %s" % "; ".join(
                "%s#%d" % (a["copy_name"], a["json_index"])
                for a in r["also_in"]))
        lines.append("")
    with open(os.path.join(run_dir, "candidates.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for fn in ("candidates.md", "candidates.json"):
            shutil.copyfile(os.path.join(run_dir, fn),
                            os.path.join(args.out, fn))

    log("finalize", counts={"out": len(scored)},
        notes={"run_dir": os.path.abspath(run_dir)})
    logf.close()

    digest = {"ENGINE_STATUS": "ok" if records else "empty",
              "snapshots": len(evidence_map), "identified": len(records),
              "after_dedup": len(unique), "included": len(scored),
              "zero_hit_terms": zero_hit, "run_dir": os.path.abspath(run_dir)}
    print(json.dumps(digest, ensure_ascii=False))
    sys.exit(0 if records else 2)


if __name__ == "__main__":
    main()
