#!/usr/bin/env python3
"""Federated multi-source literature fetcher with per-source status (stdlib only).

Direction: 数据库检索 + 来源记录 — query several scholarly sources through
independent adapters (Crossref, OpenAlex, EuropePMC, arXiv, plus local
snapshots found under /input), normalize every hit into one schema, cache
the raw responses, and report each source's status (ok / timeout / error /
empty) so degraded runs are visible rather than silent. Deduplication,
merging and verification happen in dedup_verify.py.

Usage:
  python3 federated_search.py --case /input/case.json --input /input \
      --work /app/work --out /app/output [--queries /app/work/queries.json] \
      [--sources crossref,openalex,europepmc,arxiv] [--per-query 20] [--offline]

Output pool: /app/work/pool.json  (one record per raw hit, each with a
provenance entry: source, query, url, retrieved_at, raw cache file).
"""
import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = {"User-Agent": "litsearch-federated-provenance/1.0 (academic retrieval skill)"}
STOPWORDS = set("""a an the and or of for in on with by to from at as is are was were be been
we our their its this that these those using use based study studies results analysis method
methods approach approaches via between over under into new novel review effect effects
research paper experimental investigation literature find recent relevant search papers especially related current state art 研究 方法 基于 的 与 和 在 对 及 其 综述""".split())
QUESTION_KEYS = ["research_question", "question", "task", "topic", "query",
                 "title", "description", "research_topic", "objective"]


def http_get(url, timeout, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), None
        except Exception as e:  # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.2 * (i + 1))
    return None, last


def strip_jats(text):
    return re.sub(r"<[^>]+>", " ", text or "").replace("\n", " ").strip()


def reconstruct_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


# ----------------------------------------------------------------- adapters
def ad_crossref(query, rows, timeout):
    q = urllib.parse.urlencode({
        "query.bibliographic": query, "rows": rows,
        "select": "DOI,title,author,published,container-title,"
                  "is-referenced-by-count,abstract,type,URL"})
    url = "https://api.crossref.org/works?" + q
    raw, err = http_get(url, timeout)
    recs = []
    if raw:
        data = json.loads(raw.decode("utf-8", "replace"))
        for it in data.get("message", {}).get("items", []):
            year = None
            parts = (it.get("published") or {}).get("date-parts")
            if parts and parts[0]:
                year = parts[0][0]
            recs.append({"title": (it.get("title") or [""])[0],
                         "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                                     for a in it.get("author", [])][:20],
                         "year": year,
                         "venue": (it.get("container-title") or [""])[0],
                         "doi": (it.get("DOI") or "").lower() or None,
                         "abstract": strip_jats(it.get("abstract", "")),
                         "cited_by": it.get("is-referenced-by-count", 0),
                         "type": it.get("type"), "url": it.get("URL"),
                         "ids": {"doi": (it.get("DOI") or "").lower() or None}})
    return recs, err, url, raw


def ad_openalex(query, rows, timeout):
    q = urllib.parse.urlencode({"search": query, "per-page": min(rows, 50)})
    url = "https://api.openalex.org/works?" + q
    raw, err = http_get(url, timeout)
    recs = []
    if raw:
        data = json.loads(raw.decode("utf-8", "replace"))
        for it in data.get("results", []):
            src = ((it.get("primary_location") or {}).get("source") or {})
            doi = (it.get("doi") or "").replace("https://doi.org/", "").lower() or None
            recs.append({"title": it.get("title") or "",
                         "authors": [a.get("author", {}).get("display_name", "")
                                     for a in it.get("authorships", [])][:20],
                         "year": it.get("publication_year"),
                         "venue": src.get("display_name") or "",
                         "doi": doi,
                         "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                         "cited_by": it.get("cited_by_count", 0),
                         "type": it.get("type"), "url": it.get("id"),
                         "ids": {"doi": doi, "openalex": it.get("id")}})
    return recs, err, url, raw


def ad_europepmc(query, rows, timeout):
    q = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": rows})
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + q
    raw, err = http_get(url, timeout)
    recs = []
    if raw:
        data = json.loads(raw.decode("utf-8", "replace"))
        for it in data.get("resultList", {}).get("result", []):
            doi = (it.get("doi") or "").lower() or None
            recs.append({"title": it.get("title", ""),
                         "authors": [a.strip() for a in it.get("authorString", "").split(",")
                                     if a.strip()][:20],
                         "year": int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                         "venue": it.get("journalTitle", "") or (it.get("journalInfo") or {})
                                  .get("journal", {}).get("title", ""),
                         "doi": doi,
                         "abstract": strip_jats(it.get("abstractText", "")),
                         "cited_by": it.get("citedByCount", 0),
                         "type": it.get("pubType"),
                         "url": "https://europepmc.org/article/%s/%s"
                                % (it.get("source", ""), it.get("id", "")),
                         "ids": {"doi": doi, "pmid": it.get("id")}})
    return recs, err, url, raw


def ad_arxiv(query, rows, timeout):
    terms = " AND ".join('all:"%s"' % w for w in query.split()[:6])
    q = urllib.parse.urlencode({"search_query": terms, "max_results": min(rows, 30)})
    url = "https://export.arxiv.org/api/query?" + q
    raw, err = http_get(url, timeout)
    recs = []
    if raw:
        try:
            root = ET.fromstring(raw.decode("utf-8", "replace"))
        except ET.ParseError as e:
            return [], "ParseError: %s" % e, url, raw
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for ent in root.findall("a:entry", ns):
            aid = (ent.findtext("a:id", "", ns) or "").strip()
            doi = ent.findtext("a:doi", "", ns)
            recs.append({"title": re.sub(r"\s+", " ",
                                         ent.findtext("a:title", "", ns) or "").strip(),
                         "authors": [a.findtext("a:name", "", ns) or ""
                                     for a in ent.findall("a:author", ns)][:20],
                         "year": int((ent.findtext("a:published", "", ns) or "0000")[:4]) or None,
                         "venue": "arXiv",
                         "doi": (doi or "").lower() or None,
                         "abstract": re.sub(r"\s+", " ",
                                            ent.findtext("a:summary", "", ns) or "").strip(),
                         "cited_by": 0, "type": "preprint", "url": aid,
                         "ids": {"doi": (doi or "").lower() or None, "arxiv": aid}})
    return recs, err, url, raw


ADAPTERS = {"crossref": ad_crossref, "openalex": ad_openalex,
            "europepmc": ad_europepmc, "arxiv": ad_arxiv}


def ingest_local(input_dir):
    """Organizer-provided snapshots: saved Crossref/EuropePMC/OpenAlex JSON
    responses or plain reference lists under /input. Always authoritative."""
    recs = []
    for p in sorted(Path(input_dir).rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        items, kind = [], None
        if isinstance(data, dict) and isinstance(data.get("message"), dict) \
                and isinstance(data["message"].get("items"), list):
            items, kind = data["message"]["items"], "crossref"
        elif isinstance(data, dict) and isinstance(data.get("resultList"), dict):
            items, kind = data["resultList"].get("result", []), "europepmc"
        elif isinstance(data, dict) and isinstance(data.get("results"), list):
            items, kind = data["results"], "openalex"
        elif isinstance(data, list) and data and isinstance(data[0], dict) \
                and any(k in data[0] for k in ("title", "doi", "DOI")):
            items, kind = data, "reference-list"
        if not kind:
            continue
        for it in items:
            if kind == "crossref":
                doi = (it.get("DOI") or "").lower() or None
                recs.append({"title": (it.get("title") or [""])[0] if isinstance(
                    it.get("title"), list) else it.get("title", ""),
                    "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                                for a in it.get("author", [])][:20] if it.get("author") else [],
                    "year": ((it.get("published") or {}).get("date-parts") or [[None]])[0][0],
                    "venue": (it.get("container-title") or [""])[0] if isinstance(
                        it.get("container-title"), list) else it.get("container-title", ""),
                    "doi": doi, "abstract": strip_jats(it.get("abstract", "")),
                    "cited_by": it.get("is-referenced-by-count", 0),
                    "type": it.get("type"), "url": it.get("URL"),
                    "ids": {"doi": doi}})
            elif kind == "europepmc":
                doi = (it.get("doi") or "").lower() or None
                recs.append({"title": it.get("title", ""), "authors": [],
                             "year": int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                             "venue": it.get("journalTitle", ""), "doi": doi,
                             "abstract": strip_jats(it.get("abstractText", "")),
                             "cited_by": it.get("citedByCount", 0),
                             "type": it.get("pubType"), "url": None,
                             "ids": {"doi": doi, "pmid": it.get("id")}})
            elif kind == "openalex":
                doi = (it.get("doi") or "").replace("https://doi.org/", "").lower() or None
                recs.append({"title": it.get("title") or "", "authors": [],
                             "year": it.get("publication_year"), "venue": "",
                             "doi": doi,
                             "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                             "cited_by": it.get("cited_by_count", 0),
                             "type": it.get("type"), "url": it.get("id"),
                             "ids": {"doi": doi, "openalex": it.get("id")}})
            else:
                doi = (it.get("doi") or it.get("DOI") or "").lower() or None
                recs.append({"title": it.get("title", ""),
                             "authors": it.get("authors") or [],
                             "year": it.get("year") or it.get("pubYear"),
                             "venue": it.get("venue", "") or it.get("journalTitle", ""),
                             "doi": doi,
                             "abstract": strip_jats(it.get("abstractText",
                                                           it.get("abstract", ""))),
                             "cited_by": it.get("citedByCount", it.get("cited_by", 0)),
                             "type": it.get("type"), "url": it.get("url"),
                             "ids": {"doi": doi}})
        for r in recs[-len(items):] if items else []:
            r["provenance"] = [{"source": "local-snapshot", "query": None,
                                "url": None, "file": str(p)}]
    return recs


def extract_question(case, task_md):
    texts = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in QUESTION_KEYS and isinstance(v, str) and len(v) > 10:
                    texts.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(case)
    if task_md:
        texts.append(task_md[:4000])
    return "\n".join(texts)


def auto_queries(question, n=3):
    toks = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}|[一-鿿]{2,}", question)
            if w.lower() not in STOPWORDS]
    seen, out = set(), []
    for w in toks:
        if w.lower() in seen:
            continue
        seen.add(w.lower())
        out.append(w)
    plain = " ".join(out[:8])
    queries = [{"tag": "question-plain", "query": plain}]
    if len(out) > 4:
        queries.append({"tag": "core-half", "query": " ".join(out[:4])})
        queries.append({"tag": "rest-half", "query": " ".join(out[4:10])})
    return queries[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--queries", default=None,
                    help="JSON: [{tag, query}] written by the agent after reading the case")
    ap.add_argument("--sources", default="crossref,openalex,europepmc,arxiv")
    ap.add_argument("--per-query", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    work, out = Path(args.work), Path(args.out)
    raw_dir = out / "evidence" / "raw"
    for d in (work, out, raw_dir):
        d.mkdir(parents=True, exist_ok=True)
    log = out / "evidence" / "fetch_log.jsonl"
    if log.exists():
        log.unlink()

    case = {}
    if Path(args.case).exists():
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8", errors="replace"))
        except Exception as e:  # noqa: BLE001
            case = {"_parse_error": str(e)}
    task_md = Path(args.task).read_text(encoding="utf-8", errors="replace") \
        if Path(args.task).exists() else ""
    question = extract_question(case, task_md)

    qpath = args.queries or str(work / "queries.json")
    if Path(qpath).exists():
        queries = json.loads(Path(qpath).read_text(encoding="utf-8"))
        qorigin = "agent-queries"
    else:
        queries = auto_queries(question)
        qorigin = "auto-fallback"

    sources = [s for s in args.sources.split(",") if s in ADAPTERS]
    pool, status = [], []

    local = ingest_local(args.input)
    pool.extend(local)
    status.append({"source": "local-snapshot", "status": "ok",
                   "records": len(local)})
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"source": "local-snapshot", "records": len(local)},
                           ensure_ascii=False) + "\n")

    for q in queries:
        for src in sources:
            if args.offline:
                status.append({"source": src, "query": q["query"],
                               "status": "skipped-offline", "records": 0})
                continue
            t0 = time.time()
            recs, err, url, raw = ADAPTERS[src](q["query"], args.per_query, args.timeout)
            raw_name = None
            if raw is not None:
                raw_name = "%s_%s.raw" % (src, hashlib.sha1(url.encode()).hexdigest()[:10])
                (raw_dir / raw_name).write_bytes(raw[:400000])
            for r in recs:
                r["provenance"] = [{"source": src, "query": q["query"], "url": url,
                                    "raw": raw_name,
                                    "retrieved_at": time.strftime(
                                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]
            pool.extend(recs)
            st = "ok" if err is None else ("timeout" if "timed out" in err else "error")
            if err is None and not recs:
                st = "empty"
            status.append({"source": src, "query": q["query"][:80], "status": st,
                           "error": err, "records": len(recs),
                           "elapsed_s": round(time.time() - t0, 2)})
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tag": q.get("tag"), "source": src,
                                    "query": q["query"], "url": url, "status": st,
                                    "error": err, "hits": len(recs), "raw": raw_name,
                                    "elapsed_s": round(time.time() - t0, 2)},
                                   ensure_ascii=False) + "\n")

    (work / "pool.json").write_text(json.dumps(pool, ensure_ascii=False),
                                    encoding="utf-8")
    with open(out / "source_status.md", "w", encoding="utf-8") as f:
        f.write("# Source status (federated fetch)\n\n- queries: %d (%s)\n\n"
                % (len(queries), qorigin))
        f.write("| source | query | status | records | error |\n|-|-|-|-|-|\n")
        for s in status:
            f.write("| %s | %s | %s | %s | %s |\n"
                    % (s["source"], (s.get("query") or "-")[:50], s["status"],
                       s["records"], (s.get("error") or "-")[:80]))
    degraded = sorted({s["source"] for s in status
                       if s["status"] not in ("ok", "empty")})
    print(json.dumps({"FETCH_STATUS": "partial" if degraded else "success",
                      "pool_records": len(pool), "local_records": len(local),
                      "queries": len(queries), "query_origin": qorigin,
                      "degraded_sources": degraded,
                      "source_summary": {s["source"]: s["status"] for s in status}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
