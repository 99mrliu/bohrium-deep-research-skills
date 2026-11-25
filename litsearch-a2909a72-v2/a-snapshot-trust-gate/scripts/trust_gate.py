#!/usr/bin/env python3
"""snapshot-trust-gate engine: verify local literature snapshots BEFORE retrieval.

Offline-first. Reads every literature-relevant file under --input (organizer
snapshots) and --corpus (raw search responses the agent saved during the run),
verifies each snapshot's integrity, quarantines what cannot be trusted, builds a
normalized corpus from the survivors, retrieves against the research question,
and writes traceable ranked candidates. Stdlib only; no network.

Usage:
  python3 trust_gate.py --case /input/case.json --input /input \
      [--corpus /app/work/corpus] --work /app/work --out /app/output [--top 30]
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
STOPWORDS = set("""a an the and or of in on for with to from by is are was were be been
we our this that these those it its as at into about between among over under per via
using use used based study studies analysis approach method methods results review
the and or of in on for with to from by is are was were be been research paper
find literature recent related relevant search retrieve identify 的 了 与 和 在 对 为
及其 相关 文献 检索 查找 寻找 研究 综述 近年 最新 方法 应用 进展 基于 方面 领域
""".split())


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def norm_title(t):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (t or "").lower()).strip()


def norm_doi(d):
    if not d:
        return None
    d = d.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:", "doi.org/"):
        if d.startswith(p):
            d = d[len(p):]
    return d.strip() or None


# ---------------------------------------------------------------- extraction
def extract_records(payload):
    """Return (source_type, [raw record dicts]) for a parsed JSON snapshot."""
    if not isinstance(payload, dict):
        return None, []
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
    if isinstance(msg, dict) and msg.get("DOI"):  # single Crossref work
        return "crossref-single", [msg]
    return None, []


def get_year(raw, source):
    try:
        if source.startswith("crossref"):
            parts = (raw.get("issued") or {}).get("date-parts") or []
            return int(parts[0][0]) if parts and parts[0] else None
        if source == "europepmc":
            return int(raw["pubYear"]) if raw.get("pubYear") else None
        if source == "openalex":
            return int(raw["publication_year"]) if raw.get("publication_year") else None
    except (TypeError, ValueError, IndexError):
        return None
    return None


def get_title(raw, source):
    t = raw.get("title")
    if isinstance(t, list):
        t = t[0] if t else None
    return (t or "").strip() or None


def get_doi(raw, source):
    if source == "europepmc":
        return norm_doi(raw.get("doi"))
    return norm_doi(raw.get("DOI") or raw.get("doi"))


def get_venue(raw, source):
    if source.startswith("crossref"):
        c = raw.get("container-title")
        if isinstance(c, list):
            c = c[0] if c else None
        return c
    if source == "europepmc":
        return raw.get("journalTitle")
    if source == "openalex":
        loc = raw.get("primary_location") or {}
        src = loc.get("source") or {}
        return src.get("display_name")
    return raw.get("venue") or raw.get("journal")


def get_authors(raw, source):
    out = []
    try:
        if source.startswith("crossref") or source == "generic-records":
            for a in raw.get("author") or []:
                name = " ".join(x for x in [a.get("given"), a.get("family")] if x)
                if name:
                    out.append(name)
        elif source == "europepmc":
            s = raw.get("authorString") or ""
            out = [x.strip() for x in s.split(",") if x.strip()]
        elif source == "openalex":
            for a in raw.get("authorships") or []:
                nm = (a.get("author") or {}).get("display_name")
                if nm:
                    out.append(nm)
    except AttributeError:
        pass
    return out


def get_abstract(raw, source):
    a = raw.get("abstract") or raw.get("abstractText")
    if isinstance(a, str):
        return re.sub(r"<[^>]+>", " ", a).strip() or None
    inv = raw.get("abstract_inverted_index")  # OpenAlex
    if isinstance(inv, dict):
        pos = {}
        for w, ps in inv.items():
            for p in ps:
                pos[p] = w
        return " ".join(pos[i] for i in sorted(pos)) or None
    return None


# ---------------------------------------------------------------- gate
def verify_snapshot(path, payload, source, records):
    """Snapshot-level verification. Returns (quarantine_reason_or_None, notes)."""
    notes = []
    if source is None:
        return "SCHEMA_UNRECOGNIZED", notes
    if not records:
        if source == "crossref" and payload.get("message", {}).get("total-results", 1) == 0:
            notes.append("empty result page (total-results=0) — legitimate empty query response")
            return None, notes
        return "EMPTY_RECORD_LIST", notes
    return None, notes


def verify_record(raw, source):
    """Record-level flags; empty list = clean."""
    flags = []
    doi = get_doi(raw, source)
    if doi and not DOI_RE.match(doi):
        flags.append("DOI_FORMAT_INVALID")
    if not get_title(raw, source):
        flags.append("TITLE_MISSING")
    y = get_year(raw, source)
    if y is not None and not (1450 <= y <= 2100):
        flags.append("YEAR_IMPLAUSIBLE")
    if not doi and not get_title(raw, source):
        flags.append("NO_IDENTIFIER")
    return flags


# ---------------------------------------------------------------- query
def load_case(case_path):
    with open(case_path, encoding="utf-8") as f:
        return json.load(f)


def extract_question(case, task_md):
    for key in ("research_question", "question", "query", "topic", "task",
                "prompt", "title", "objective"):
        v = case.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    q = case.get("question") or case.get("task")
    if isinstance(q, dict):
        for key in ("text", "question", "title", "description"):
            if isinstance(q.get(key), str) and q[key].strip():
                return q[key].strip()
    for line in (task_md or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if len(line) >= 12 and not line.lower().startswith(("output", "input", "contract")):
            return line
    return ""


def tokenize(text):
    text = (text or "").lower()
    toks = re.findall(r"[a-z][a-z0-9\-]{1,}", text)
    toks = [t for t in toks if t not in STOPWORDS and len(t) > 2]
    zh = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    for seg in zh:
        toks.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return sorted(set(toks))


def score_record(rec, terms, year_from, year_to):
    title = (rec.get("title") or "").lower()
    abstract = (rec.get("abstract") or "").lower()
    venue = (rec.get("venue") or "").lower()
    hits, s = [], 0.0
    for t in terms:
        if t in title:
            s += 3.0
            hits.append(t)
        elif t in abstract:
            s += 1.0
            hits.append(t)
        elif t in venue:
            s += 0.5
    if year_from and rec.get("year") and rec["year"] < year_from:
        s *= 0.5
    if year_to and rec.get("year") and rec["year"] > year_to:
        s *= 0.5
    return s, hits


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--corpus", default=None,
                    help="extra dir of raw search responses saved by the agent")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    ev_dir = os.path.join(args.out, "evidence")
    os.makedirs(ev_dir, exist_ok=True)

    case = load_case(args.case)
    task_md = ""
    for cand in (os.path.join(args.input, "task.md"),):
        if os.path.isfile(cand):
            task_md = open(cand, encoding="utf-8", errors="replace").read()
    question = extract_question(case, task_md)
    terms = tokenize(question)
    year_from = case.get("year_from") or case.get("date_from")
    year_to = case.get("year_to") or case.get("date_to")
    try:
        year_from = int(str(year_from)[:4]) if year_from else None
        year_to = int(str(year_to)[:4]) if year_to else None
    except ValueError:
        year_from = year_to = None

    roots = [args.input]
    if args.corpus and os.path.isdir(args.corpus):
        roots.append(args.corpus)

    inventory, seen_hash = [], {}
    verified, quarantined = [], []
    zero_hit_terms = set(terms)

    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root)
                low = fn.lower()
                if not low.endswith((".json", ".xml")):
                    continue
                if fn in ("case.json", "result.json"):
                    continue
                digest = sha12(path)
                entry = {"file": rel, "root": root, "sha256_12": digest,
                         "bytes": os.path.getsize(path)}
                if digest in seen_hash:
                    entry["quarantine"] = "DUPLICATE_PAYLOAD"
                    entry["duplicate_of"] = seen_hash[digest]
                    quarantined.append(entry)
                    inventory.append(entry)
                    continue
                seen_hash[digest] = rel
                try:
                    raw_text = open(path, encoding="utf-8", errors="replace").read()
                    payload = json.loads(raw_text)
                except (json.JSONDecodeError, OSError) as exc:
                    entry["quarantine"] = "PARSE_ERROR"
                    entry["detail"] = str(exc)[:200]
                    quarantined.append(entry)
                    inventory.append(entry)
                    continue
                source, raws = extract_records(payload)
                reason, notes = verify_snapshot(path, payload, source, raws)
                entry["source_type"] = source
                entry["notes"] = notes
                if reason:
                    entry["quarantine"] = reason
                    quarantined.append(entry)
                    inventory.append(entry)
                    continue
                entry["records"] = len(raws)
                n_flag = 0
                for i, r in enumerate(raws):
                    flags = verify_record(r, source)
                    if flags:
                        n_flag += 1
                    rec = {
                        "title": get_title(r, source),
                        "authors": get_authors(r, source),
                        "year": get_year(r, source),
                        "venue": get_venue(r, source),
                        "doi": get_doi(r, source),
                        "abstract": get_abstract(r, source),
                        "provenance": {"file": rel, "root": root,
                                       "json_index": i, "source_type": source,
                                       "sha256_12": digest},
                        "record_flags": flags,
                    }
                    verified.append(rec)
                entry["record_flags"] = n_flag
                entry["trust_tier"] = "T1-verified" if n_flag == 0 else "T2-flagged-records"
                inventory.append(entry)

    # dedup: DOI exact, else normalized title
    by_key = {}
    for rec in verified:
        key = ("doi:" + rec["doi"]) if rec.get("doi") else "title:" + norm_title(rec.get("title"))
        if not rec.get("doi") and not rec.get("title"):
            key = "anon:" + rec["provenance"]["file"] + "#" + str(rec["provenance"]["json_index"])
        if key in by_key:
            by_key[key].setdefault("also_in", []).append(rec["provenance"])
        else:
            by_key[key] = rec
    corpus = list(by_key.values())

    for rec in corpus:
        s, hits = score_record(rec, terms, year_from, year_to)
        rec["relevance_score"] = round(s, 3)
        rec["matched_terms"] = hits
        zero_hit_terms -= set(hits)
    corpus.sort(key=lambda r: (-r["relevance_score"], -(r.get("year") or 0),
                               r.get("title") or ""))
    ranked = [r for r in corpus if r["relevance_score"] > 0][:args.top]

    # ---- outputs
    with open(os.path.join(args.out, "verified_corpus.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_iso(), "unique_records": len(corpus),
                   "records": corpus}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump({"question": question, "ranked": ranked}, f, ensure_ascii=False, indent=1)

    lines = ["# Ranked candidates (snapshot-trust-gate)", "",
             "Question: %s" % (question or "(none extracted)"), "",
             "| # | score | year | title | venue | DOI | source |", "|-|-|-|-|-|-|-|"]
    for i, r in enumerate(ranked, 1):
        p = r["provenance"]
        lines.append("| %d | %.2f | %s | %s | %s | %s | %s#%d |" % (
            i, r["relevance_score"], r.get("year") or "—",
            (r.get("title") or "—")[:90], (r.get("venue") or "—")[:30],
            r.get("doi") or "—", p["file"], p["json_index"]))
    if not ranked:
        lines.append("| — | — | — | no verified record matched the query terms | | | |")
    open(os.path.join(args.out, "candidates.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    qlines = ["# Quarantine & trust report", "",
              "Every snapshot file under --input/--corpus was hashed, parsed and "
              "schema-checked BEFORE any record entered the corpus.", "",
              "## Quarantined (excluded from corpus)"]
    if quarantined:
        for q in quarantined:
            qlines.append("- `%s` — **%s**%s (sha256:%s)" % (
                q["file"], q["quarantine"],
                ("; " + q.get("detail", "")) if q.get("detail") else
                ("; duplicate of `%s`" % q["duplicate_of"]) if q.get("duplicate_of") else "",
                q["sha256_12"]))
    else:
        qlines.append("- none")
    qlines += ["", "## Verified snapshots", "",
               "| file | source type | records | flagged records | trust tier | sha256 |",
               "|-|-|-|-|-|-|"]
    for e in inventory:
        if "quarantine" not in e:
            qlines.append("| %s | %s | %d | %d | %s | %s |" % (
                e["file"], e.get("source_type"), e.get("records", 0),
                e.get("record_flags", 0), e.get("trust_tier"), e["sha256_12"]))
    open(os.path.join(args.out, "quarantine_report.md"), "w", encoding="utf-8") \
        .write("\n".join(qlines) + "\n")

    report = {
        "ENGINE_STATUS": "success" if verified else "partial",
        "question": question,
        "query_terms": terms,
        "snapshots_seen": len(inventory),
        "snapshots_verified": sum(1 for e in inventory if "quarantine" not in e),
        "snapshots_quarantined": len(quarantined),
        "records_verified": len(verified),
        "unique_records": len(corpus),
        "ranked_candidates": len(ranked),
        "zero_hit_terms": sorted(zero_hit_terms),
        "year_window": [year_from, year_to],
    }
    rlines = ["# Search report (snapshot-trust-gate)", "",
              "```json", json.dumps(report, ensure_ascii=False, indent=1), "```", "",
              "## Interpretation", "",
              "- Quarantined snapshots never entered the corpus; see quarantine_report.md.",
              "- `zero_hit_terms` lists query concepts with no match in the verified "
              "corpus — an honest coverage gap, to be copied into result.json uncertainty.",
              "- Every candidate carries provenance {file, json_index, sha256_12}; a "
              "reviewer can re-open the exact snapshot and record."]
    open(os.path.join(args.out, "search_report.md"), "w", encoding="utf-8") \
        .write("\n".join(rlines) + "\n")

    with open(os.path.join(ev_dir, "evidence_index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_iso(), "files": inventory}, f,
                  ensure_ascii=False, indent=1)

    print(json.dumps(report, ensure_ascii=False))
    return 0 if verified else 2


if __name__ == "__main__":
    sys.exit(main())
