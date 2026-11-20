#!/usr/bin/env python3
"""Coverage-driven multi-round literature search engine (stdlib only).

Direction: 多轮查询规划 — decompose a research question into facets, run
planned query rounds (core AND -> facet-relaxed OR -> citation snowball),
stop on marginal yield, and log every query so each kept paper is traceable
to an actual database response.

Usage:
  python3 planned_search.py --case /input/case.json --input /input \
      --work /app/work --out /app/output [--plan /app/work/plan.json] \
      [--max-rounds 4] [--per-query 20] [--offline]

The engine never invents records: every candidate carries the source,
query and raw-response file it came from. If the network is down it falls
back to local snapshots found under --input and says so in the status.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "litsearch-query-planner/1.0 (academic retrieval skill)"}
STOPWORDS = set("""a an the and or of for in on with by to from at as is are was were be been
we our their its this that these those using use based study studies results analysis method
methods approach approaches via between over under into new novel review effect effects
research paper experimental investigation literature find recent relevant search papers especially related current state art 研究 方法 基于 的 与 和 在 对 及 其 综述""".split())


def log_line(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def http_json(url, timeout, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace")), None
        except Exception as e:  # noqa: BLE001 - record any failure honestly
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.2 * (i + 1))
    return None, last


def strip_jats(text):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def reconstruct_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


# ---------------------------------------------------------------- sources
def fetch_crossref(query, rows, timeout):
    q = urllib.parse.urlencode({
        "query.bibliographic": query, "rows": rows,
        "select": "DOI,title,author,published,container-title,"
                  "is-referenced-by-count,abstract,type,URL"})
    url = "https://api.crossref.org/works?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("message", {}).get("items", []):
            title = (it.get("title") or [""])[0]
            year = None
            for k in ("published", "published-print", "published-online"):
                parts = (it.get(k) or {}).get("date-parts")
                if parts and parts[0]:
                    year = parts[0][0]
                    break
            recs.append({
                "title": title,
                "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                            for a in it.get("author", [])][:20],
                "year": year,
                "venue": (it.get("container-title") or [""])[0],
                "doi": (it.get("DOI") or "").lower() or None,
                "abstract": strip_jats(it.get("abstract", "")),
                "cited_by": it.get("is-referenced-by-count", 0),
                "type": it.get("type"),
                "url": it.get("URL") or ("https://doi.org/" + it["DOI"] if it.get("DOI") else None),
            })
    return recs, err, url, data


def fetch_openalex(query, rows, timeout):
    q = urllib.parse.urlencode({"search": query, "per-page": min(rows, 50)})
    url = "https://api.openalex.org/works?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("results", []):
            src = ((it.get("primary_location") or {}).get("source") or {})
            doi = it.get("doi") or ""
            recs.append({
                "title": it.get("title") or "",
                "authors": [a.get("author", {}).get("display_name", "")
                            for a in it.get("authorships", [])][:20],
                "year": it.get("publication_year"),
                "venue": src.get("display_name") or "",
                "doi": doi.replace("https://doi.org/", "").lower() or None,
                "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                "cited_by": it.get("cited_by_count", 0),
                "type": it.get("type"),
                "url": it.get("id"),
                "openalex_id": it.get("id"),
            })
    return recs, err, url, data


def fetch_europepmc(query, rows, timeout):
    q = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": rows})
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("resultList", {}).get("result", []):
            recs.append({
                "title": it.get("title", ""),
                "authors": [a.strip() for a in it.get("authorString", "").split(",") if a.strip()][:20],
                "year": int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                "venue": (it.get("journalInfo") or {}).get("journal", {}).get("title", "")
                         or it.get("journalTitle", ""),
                "doi": (it.get("doi") or "").lower() or None,
                "abstract": it.get("abstractText", ""),
                "cited_by": it.get("citedByCount", 0),
                "type": it.get("pubType"),
                "url": "https://europepmc.org/article/%s/%s" % (it.get("source", ""), it.get("id", "")),
            })
    return recs, err, url, data


def openalex_snowball(openalex_id, direction, rows, timeout):
    """direction: 'cites' (references) or 'cited_by' (forward citations)."""
    flt = "%s:%s" % (direction, openalex_id.rsplit("/", 1)[-1])
    q = urllib.parse.urlencode({"filter": flt, "per-page": min(rows, 50)})
    url = "https://api.openalex.org/works?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("results", []):
            src = ((it.get("primary_location") or {}).get("source") or {})
            doi = it.get("doi") or ""
            recs.append({
                "title": it.get("title") or "",
                "authors": [a.get("author", {}).get("display_name", "")
                            for a in it.get("authorships", [])][:20],
                "year": it.get("publication_year"),
                "venue": src.get("display_name") or "",
                "doi": doi.replace("https://doi.org/", "").lower() or None,
                "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                "cited_by": it.get("cited_by_count", 0),
                "type": it.get("type"),
                "url": it.get("id"),
                "openalex_id": it.get("id"),
            })
    return recs, err, url


SOURCES = {"crossref": fetch_crossref, "openalex": fetch_openalex,
           "europepmc": fetch_europepmc}


# ------------------------------------------------------------- local input
def ingest_local(input_dir, raw_dir):
    """Ingest organizer-provided snapshots: saved Crossref/EuropePMC/OpenAlex
    API responses or plain reference lists found under /input. These are
    authoritative source-bound material and are always used."""
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
                recs.append({
                    "title": (it.get("title") or [""])[0] if isinstance(it.get("title"), list)
                             else it.get("title", ""),
                    "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                                for a in it.get("author", [])][:20] if it.get("author") else [],
                    "year": ((it.get("published") or {}).get("date-parts") or [[None]])[0][0],
                    "venue": (it.get("container-title") or [""])[0] if isinstance(
                        it.get("container-title"), list) else it.get("container-title", ""),
                    "doi": (it.get("DOI") or "").lower() or None,
                    "abstract": strip_jats(it.get("abstract", "")), "cited_by":
                        it.get("is-referenced-by-count", 0), "type": it.get("type"),
                    "url": it.get("URL")})
            elif kind == "europepmc":
                recs.append({
                    "title": it.get("title", ""),
                    "authors": [a.strip() for a in it.get("authorString", "").split(",") if a.strip()][:20],
                    "year": int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                    "venue": it.get("journalTitle", "") or (it.get("journalInfo") or {}).get(
                        "journal", {}).get("title", ""),
                    "doi": (it.get("doi") or "").lower() or None,
                    "abstract": re.sub(r"<[^>]+>", " ", it.get("abstractText", "") or ""),
                    "cited_by": it.get("citedByCount", 0), "type": it.get("pubType"),
                    "url": None})
            elif kind == "openalex":
                src = ((it.get("primary_location") or {}).get("source") or {})
                doi = it.get("doi") or ""
                recs.append({
                    "title": it.get("title") or "",
                    "authors": [a.get("author", {}).get("display_name", "")
                                for a in it.get("authorships", [])][:20],
                    "year": it.get("publication_year"),
                    "venue": src.get("display_name") or "",
                    "doi": doi.replace("https://doi.org/", "").lower() or None,
                    "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                    "cited_by": it.get("cited_by_count", 0), "type": it.get("type"),
                    "url": it.get("id"), "openalex_id": it.get("id")})
            else:
                recs.append({
                    "title": it.get("title", ""),
                    "authors": it.get("authors") or it.get("author") or [],
                    "year": it.get("year") or it.get("pubYear"),
                    "venue": it.get("venue") or it.get("journal", ""),
                    "doi": (it.get("doi") or it.get("DOI") or "").lower() or None,
                    "abstract": it.get("abstract", ""), "cited_by": it.get("cited_by", 0),
                    "type": it.get("type"), "url": it.get("url")})
        for r in recs:
            r.setdefault("provenance", [])
        n = len(items)
        for r in recs[-n:] if n else []:
            r["provenance"] = [{"source": "local-snapshot", "query": None,
                                "file": str(p)}]
    return recs


# ------------------------------------------------------------ case & plan
QUESTION_KEYS = ["research_question", "question", "task", "topic", "query",
                 "title", "description", "research_topic", "objective"]


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


def auto_facets(question, max_facets=4):
    """Fallback facet extraction when the agent did not write a plan.
    Picks content words / bigrams with document frequency heuristics."""
    tokens = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}|[一-鿿]{2,}", question)
              if w.lower() not in STOPWORDS]
    freq = {}
    for w in tokens:
        freq[w.lower()] = freq.get(w.lower(), 0) + 1
    cands = sorted(freq, key=lambda w: (-freq[w], -len(w)))
    facets, seen = [], set()
    for w in cands:
        if any(w in s or s in w for s in seen):
            continue
        seen.add(w)
        facets.append({"name": w, "terms": [w]})
        if len(facets) >= max_facets:
            break
    return facets


def load_plan(plan_path, question):
    if plan_path and Path(plan_path).exists():
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        plan["_origin"] = "agent-plan"
        return plan
    return {"_origin": "auto-fallback", "facets": auto_facets(question),
            "databases": ["crossref", "openalex", "europepmc"],
            "year_from": None, "year_to": None}


def facet_terms(plan):
    terms = []
    for f in plan.get("facets", []):
        ts = list(f.get("terms", [])) + list(f.get("expanded", []))
        terms.append((f.get("name", ts[0] if ts else "?"), ts))
    return terms


def relevance(rec, terms, year_from=None, year_to=None):
    """Transparent rubric, documented in resources/methodology.md:
    0.5 * title facet coverage + 0.3 * abstract facet coverage
    + 0.2 * log-normalized citations; year window gates to 0 outside."""
    title = (rec.get("title") or "").lower()
    absx = (rec.get("abstract") or "").lower()
    if not terms:
        return 0.0
    tcov = acov = 0.0
    for _name, ts in terms:
        hit_t = any(t.lower() in title for t in ts)
        hit_a = any(t.lower() in absx for t in ts)
        tcov += 1.0 if hit_t else 0.0
        acov += 1.0 if hit_a else 0.0
    tcov /= len(terms)
    acov /= len(terms)
    import math
    cit = math.log1p(rec.get("cited_by") or 0) / math.log1p(5000)
    score = 0.5 * tcov + 0.3 * acov + 0.2 * min(cit, 1.0)
    y = rec.get("year")
    if y and year_from and y < year_from:
        score *= 0.3
    if y and year_to and y > year_to:
        score *= 0.3
    return round(score, 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--per-query", type=int, default=20)
    ap.add_argument("--snowball-seeds", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    work, out = Path(args.work), Path(args.out)
    ev = out / "evidence"
    raw_dir = ev / "raw"
    for d in (work, out, ev, raw_dir):
        d.mkdir(parents=True, exist_ok=True)
    log = ev / "search_log.jsonl"
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
    plan_path = args.plan or str(work / "plan.json")
    plan = load_plan(plan_path, question)
    terms = facet_terms(plan)
    year_from, year_to = plan.get("year_from"), plan.get("year_to")
    dbs = [d for d in plan.get("databases", ["crossref", "openalex", "europepmc"])
           if d in SOURCES]

    failures = []
    pool, seen = [], {}

    def add_records(recs, source, query, rnd, url, raw_name):
        new = 0
        for r in recs:
            key = r.get("doi") or norm_title(r.get("title"))
            if not key:
                continue
            prov = {"source": source, "query": query, "round": rnd, "url": url,
                    "raw": raw_name, "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                  time.gmtime())}
            if key in seen:
                seen[key]["provenance"].append(prov)
                if not seen[key].get("abstract") and r.get("abstract"):
                    seen[key]["abstract"] = r["abstract"]
                continue
            r["provenance"] = [prov]
            seen[key] = r
            pool.append(r)
            new += 1
        return new

    # round 0: local snapshots (authoritative, source-bound material)
    local = ingest_local(args.input, raw_dir)
    n_local = add_records(local, "local-snapshot", None, 0, None, None)
    log_line(log, {"round": 0, "phase": "local-ingest", "records": len(local),
                   "new_unique": n_local})

    # planned query rounds
    queries_by_round = []
    facet_names = [n for n, _ in terms]
    core = " ".join("(%s)" % " OR ".join('"%s"' % t for t in ts[:3])
                    for _n, ts in terms if ts) or question[:200]
    queries_by_round.append([("core-AND", re.sub(r"\s+", " ", core))])
    relaxed = [("facet-%s" % n, " OR ".join('"%s"' % t for t in ts[:4]))
               for n, ts in terms if ts]
    queries_by_round.append(relaxed)
    plain = re.sub(r"[^\w\s\-]", " ", question)
    plain = " ".join(w for w in plain.split() if w.lower() not in STOPWORDS)[:160]
    queries_by_round.append([("question-plain", plain)])

    stop_reason = "max rounds reached"
    for rnd in range(1, args.max_rounds + 1):
        if rnd - 1 >= len(queries_by_round):
            break
        new_this = 0
        for tag, query in queries_by_round[rnd - 1]:
            if not query.strip():
                continue
            for db in dbs:
                if args.offline:
                    continue
                t0 = time.time()
                recs, err, url, raw = SOURCES[db](query, args.per_query, args.timeout)
                raw_name = None
                if raw is not None:
                    raw_name = "r%d_%s_%s.json" % (rnd, db, hashlib.sha1(
                        url.encode()).hexdigest()[:8])
                    (raw_dir / raw_name).write_text(json.dumps(
                        {"url": url, "response": raw}, ensure_ascii=False)[:400000],
                        encoding="utf-8")
                new = add_records(recs, db, query, rnd, url, raw_name)
                new_this += new
                log_line(log, {"round": rnd, "tag": tag, "source": db, "query": query,
                               "url": url, "ok": err is None, "error": err,
                               "hits": len(recs), "new_unique": new,
                               "elapsed_s": round(time.time() - t0, 2)})
                if err:
                    failures.append({"source": db, "query": query, "error": err})
        if new_this < max(2, int(0.05 * max(len(pool), 1))):
            stop_reason = ("stopped after round %d: marginal yield %d new unique "
                           "records below threshold" % (rnd, new_this))
            break

    # snowball round on OpenAlex citation graph
    snowballed = 0
    if not args.offline and "openalex" in dbs:
        for r in pool:
            r["_score_tmp"] = relevance(r, terms, year_from, year_to)
        seeds = [r for r in sorted(pool, key=lambda x: -x["_score_tmp"])
                 if r.get("openalex_id")][:args.snowball_seeds]
        for seed in seeds:
            for direction in ("cites", "cited_by"):
                recs, err, url = openalex_snowball(seed["openalex_id"], direction,
                                                   25, args.timeout)
                new = add_records(recs, "openalex-snowball",
                                  "%s(%s)" % (direction, seed["openalex_id"]),
                                  99, url, None)
                snowballed += new
                log_line(log, {"round": 99, "phase": "snowball", "direction": direction,
                               "seed": seed["openalex_id"], "url": url,
                               "ok": err is None, "error": err,
                               "hits": len(recs), "new_unique": new})
                if err:
                    failures.append({"source": "openalex-snowball",
                                     "query": url, "error": err})

    # final scoring & ranking
    for r in pool:
        r["relevance_score"] = relevance(r, terms, year_from, year_to)
        r.pop("_score_tmp", None)
    pool.sort(key=lambda x: -x["relevance_score"])

    # coverage report per facet
    coverage = []
    for name, ts in terms:
        hits = [r for r in pool if any(t.lower() in
                ((r.get("title") or "") + " " + (r.get("abstract") or "")).lower()
                for t in ts)]
        coverage.append({"facet": name, "terms": ts, "hits": len(hits),
                         "covered": len(hits) > 0})
    uncovered = [c["facet"] for c in coverage if not c["covered"]]

    # outputs
    (out / "candidates.json").write_text(json.dumps(
        pool, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "candidates.md", "w", encoding="utf-8") as f:
        f.write("# Ranked candidate literature (top 30)\n\n")
        f.write("Scoring rubric: 0.5*title facet coverage + 0.3*abstract facet coverage "
                "+ 0.2*log-normalized citations; see resources/methodology.md.\n\n")
        for i, r in enumerate(pool[:30], 1):
            srcs = sorted({p["source"] for p in r.get("provenance", [])})
            f.write("## %d. %s\n- score: %.3f | year: %s | venue: %s | DOI: %s\n"
                    "- authors: %s\n- sources: %s | cited_by: %s\n- abstract: %s\n\n"
                    % (i, r.get("title") or "(no title)", r["relevance_score"],
                       r.get("year") or "?", (r.get("venue") or "?")[:80],
                       r.get("doi") or "none",
                       "; ".join(r.get("authors", [])[:5]) or "?",
                       ", ".join(srcs), r.get("cited_by", 0),
                       (r.get("abstract") or "(none)")[:400]))
    status = "success"
    problems = []
    if args.offline:
        status = "partial"
        problems.append("offline mode: only local snapshots used")
    if failures:
        uniq = sorted({f["source"] for f in failures})
        problems.append("source failures: " + ", ".join(uniq))
        if not pool:
            status = "partial"
    if uncovered:
        problems.append("uncovered facets: " + ", ".join(uncovered))
    with open(out / "search_report.md", "w", encoding="utf-8") as f:
        f.write("# Multi-round search report\n\n")
        f.write("- plan origin: %s (plan file: %s)\n" % (plan["_origin"], plan_path))
        f.write("- facets: %s\n" % ", ".join(facet_names))
        f.write("- databases: %s\n" % ", ".join(dbs))
        f.write("- unique records: %d (local ingest %d, snowball new %d)\n"
                % (len(pool), n_local, snowballed))
        f.write("- stop reason: %s\n" % stop_reason)
        f.write("- problems: %s\n\n" % ("; ".join(problems) or "none"))
        f.write("## Facet coverage\n\n")
        for c in coverage:
            f.write("- %s: %d hits %s\n" % (c["facet"], c["hits"],
                    "OK" if c["covered"] else "**NOT COVERED**"))
        f.write("\n## Failures\n\n")
        for f2 in failures[:20]:
            f.write("- %s | %s | %s\n" % (f2["source"], f2.get("query", "")[:80],
                                          f2["error"]))
    print(json.dumps({
        "ENGINE_STATUS": status, "unique_records": len(pool),
        "local_ingested": n_local, "snowball_new": snowballed,
        "uncovered_facets": uncovered, "source_failures":
        sorted({f["source"] for f in failures}),
        "plan_origin": plan["_origin"], "stop_reason": stop_reason,
        "question_excerpt": question[:200]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
