#!/usr/bin/env python3
"""Terminology-expansion + PRISMA-style two-stage screening engine (stdlib only).

Direction: 关键词扩展 + 筛选依据 — expand the research question's terms
(abbreviation pairs, spelling/hyphen variants, morphological variants, zh<->en
glossary), issue a bounded set of expanded queries, then screen every
retrieved record through an explicit two-stage rubric (title screen, abstract
screen) with documented reason codes. Every kept AND every dropped record
lands in screening_ledger.csv with its decision, stage, reason code and the
title/abstract evidence snippet the decision was based on.

Usage:
  python3 termxpand_screen.py --case /input/case.json --input /input \
      --work /app/work --out /app/output [--terms /app/work/terms.json] \
      [--threshold 0.35] [--max-queries 12] [--offline]

The engine never invents records and never silently discards one: exclusion
is a logged decision with a reason code, not a delete.
"""
import argparse
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "litsearch-termxpand-screen/1.0 (academic retrieval skill)"}
STOPWORDS = set("""a an the and or of for in on with by to from at as is are was were be been
we our their its this that these those using use based study studies results analysis method
methods approach approaches via between over under into new novel review effect effects
research paper experimental investigation literature find recent relevant search papers especially related current state art 研究 方法 基于 的 与 和 在 对 及 其 综述""".split())

# small built-in variant tables; the agent extends them via terms.json / glossary_extra.md
US_UK = [("ize", "ise"), ("ization", "isation"), ("or", "our"), ("emia", "aemia"),
         ("tumor", "tumour"), ("color", "colour"), ("fiber", "fibre"), ("center", "centre")]
QUESTION_KEYS = ["research_question", "question", "task", "topic", "query",
                 "title", "description", "research_topic", "objective"]

# reason codes (documented in resources/screening_rubric.md)
CODES = {
    "I1": "core: title and abstract both cover the question's concepts",
    "I2": "peripheral: relevant but partial concept coverage",
    "I3": "include-uncertain: no abstract available, title on-topic, needs full-text check",
    "E1": "off-topic at title screen: no concept term in title and <2 in abstract",
    "E2": "low abstract relevance: below score threshold at stage 2",
    "E3": "duplicate of an already screened record",
    "E4": "excluded publication type (retracted/preprint-server-suppressed/etc.)",
    "E5": "outside requested year window",
}


def http_json(url, timeout, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace")), None
        except Exception as e:  # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.2 * (i + 1))
    return None, last


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


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


# ------------------------------------------------------------------ sources
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
                         "type": it.get("type"), "url": it.get("URL")})
    return recs, err, url


def fetch_openalex(query, rows, timeout):
    q = urllib.parse.urlencode({"search": query, "per-page": min(rows, 50)})
    url = "https://api.openalex.org/works?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("results", []):
            src = ((it.get("primary_location") or {}).get("source") or {})
            doi = it.get("doi") or ""
            recs.append({"title": it.get("title") or "",
                         "authors": [a.get("author", {}).get("display_name", "")
                                     for a in it.get("authorships", [])][:20],
                         "year": it.get("publication_year"),
                         "venue": src.get("display_name") or "",
                         "doi": doi.replace("https://doi.org/", "").lower() or None,
                         "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                         "cited_by": it.get("cited_by_count", 0),
                         "type": it.get("type"), "url": it.get("id")})
    return recs, err, url


def fetch_europepmc(query, rows, timeout):
    q = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": rows})
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + q
    data, err = http_json(url, timeout)
    recs = []
    if data:
        for it in data.get("resultList", {}).get("result", []):
            recs.append({"title": it.get("title", ""),
                         "authors": [a.strip() for a in it.get("authorString", "").split(",")
                                     if a.strip()][:20],
                         "year": int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None,
                         "venue": it.get("journalTitle", "") or (it.get("journalInfo") or {})
                                  .get("journal", {}).get("title", ""),
                         "doi": (it.get("doi") or "").lower() or None,
                         "abstract": strip_jats(it.get("abstractText", "")),
                         "cited_by": it.get("citedByCount", 0),
                         "type": it.get("pubType"),
                         "url": "https://europepmc.org/article/%s/%s"
                                % (it.get("source", ""), it.get("id", ""))})
    return recs, err, url


SOURCES = {"crossref": fetch_crossref, "openalex": fetch_openalex,
           "europepmc": fetch_europepmc}


def ingest_local(input_dir):
    """Organizer-provided snapshots are authoritative and always ingested."""
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
                recs.append({"title": (it.get("title") or [""])[0] if isinstance(
                    it.get("title"), list) else it.get("title", ""),
                    "authors": [], "year": ((it.get("published") or {}).get(
                        "date-parts") or [[None]])[0][0],
                    "venue": "", "doi": (it.get("DOI") or "").lower() or None,
                    "abstract": strip_jats(it.get("abstract", "")),
                    "cited_by": it.get("is-referenced-by-count", 0),
                    "type": it.get("type"), "url": it.get("URL")})
            elif kind == "openalex":
                doi = it.get("doi") or ""
                recs.append({"title": it.get("title") or "", "authors": [],
                             "year": it.get("publication_year"), "venue": "",
                             "doi": doi.replace("https://doi.org/", "").lower() or None,
                             "abstract": reconstruct_abstract(it.get("abstract_inverted_index")),
                             "cited_by": it.get("cited_by_count", 0),
                             "type": it.get("type"), "url": it.get("id")})
            else:
                recs.append({"title": it.get("title", ""), "authors": [],
                             "year": it.get("year") or it.get("pubYear"),
                             "venue": it.get("venue", "") or it.get("journalTitle", ""),
                             "doi": (it.get("doi") or it.get("DOI") or "").lower() or None,
                             "abstract": strip_jats(it.get("abstractText",
                                                           it.get("abstract", ""))),
                             "cited_by": it.get("citedByCount", it.get("cited_by", 0)),
                             "type": it.get("type"), "url": it.get("url")})
        for r in recs[-len(items):] if items else []:
            r["provenance"] = [{"source": "local-snapshot", "query": None, "file": str(p)}]
    return recs


# --------------------------------------------------------- term expansion
def detect_abbrev_pairs(text):
    """'full name (ABBR)' and 'ABBR (full name)' patterns -> {ABBR: full}."""
    pairs = {}
    for m in re.finditer(r"([A-Za-z][A-Za-z\- ]{3,60}?)\s*\(([A-Z][A-Z0-9]{1,9})\)", text):
        pairs[m.group(2)] = m.group(1).strip()
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,9})\s*\(([A-Za-z][A-Za-z\- ]{3,60}?)\)", text):
        pairs.setdefault(m.group(1), m.group(2).strip())
    return pairs


def variants(term):
    """Spelling / hyphen / morphology variants of one term."""
    out = {term}
    if "-" in term:
        out.add(term.replace("-", " "))
    if " " in term:
        out.add(term.replace(" ", "-"))
    low = term.lower()
    for a, b in US_UK:
        if low.endswith(a):
            out.add(term[:-len(a)] + b)
        if low.endswith(b):
            out.add(term[:-len(b)] + a)
    words = term.split()
    last = words[-1]
    if last.endswith("s") and len(last) > 3:
        out.add(" ".join(words[:-1] + [last[:-1]]))
    else:
        out.add(" ".join(words[:-1] + [last + "s"]))
    return {v for v in out if v and v.lower() not in STOPWORDS}


def load_glossary(paths):
    """Parse markdown tables: | term | synonyms | zh | en | (header variants ok)."""
    gloss = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0].lower() in ("term", "术语"):
                continue
            term = cells[0]
            syns = []
            for c in cells[1:]:
                syns += [s.strip() for s in re.split(r"[,;，；/]", c) if s.strip()]
            gloss.setdefault(term, [])
            gloss[term] += [s for s in syns if s != term]
    return gloss


def build_concepts(question, terms_path, glossary_paths, max_concepts=6):
    """Concept list: [{name, terms:[expanded...]}]. Agent terms.json wins."""
    if terms_path and Path(terms_path).exists():
        data = json.loads(Path(terms_path).read_text(encoding="utf-8"))
        concepts = data.get("concepts", [])
        for c in concepts:
            exp = set(c.get("terms", [])) | set(c.get("expanded", []))
            for t in list(exp):
                exp |= variants(t)
            c["all_terms"] = sorted(exp)
        return concepts[:max_concepts], data
    gloss = load_glossary(glossary_paths)
    abbr = detect_abbrev_pairs(question)
    toks = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}|[一-鿿]{2,}", question)
            if w.lower() not in STOPWORDS]
    freq = {}
    for w in toks:
        freq[w] = freq.get(w, 0) + 1
    concepts, seen = [], set()
    for w in sorted(freq, key=lambda x: (-freq[x], -len(x))):
        if any(w.lower() in s or s in w.lower() for s in seen):
            continue
        seen.add(w)
        terms = set(variants(w))
        for g, syns in gloss.items():
            if w.lower() == g.lower() or w.lower() in (s.lower() for s in syns):
                terms.add(g)
                terms.update(syns)
        for a, full in abbr.items():
            if w.lower() == a.lower() or w.lower() in full.lower():
                terms.update([a, full])
        concepts.append({"name": w, "terms": [w], "expanded": sorted(terms - {w}),
                         "all_terms": sorted(terms)})
        if len(concepts) >= max_concepts:
            break
    return concepts, {"_origin": "auto-fallback"}


# --------------------------------------------------------------- screening
def concept_hits(text, concepts):
    text = text.lower()
    n = 0
    for c in concepts:
        if any(t.lower() in text for t in c["all_terms"]):
            n += 1
    return n


def relevance_score(rec, concepts):
    title = (rec.get("title") or "").lower()
    absx = (rec.get("abstract") or "").lower()
    if not concepts:
        return 0.0
    th = concept_hits(title, concepts) / len(concepts)
    ah = concept_hits(absx, concepts) / len(concepts)
    cit = math.log1p(rec.get("cited_by") or 0) / math.log1p(5000)
    return round(0.55 * th + 0.30 * ah + 0.15 * min(cit, 1.0), 4)


def evidence_snippet(rec, concepts, width=220):
    """First abstract sentence containing a concept term, else title."""
    absx = rec.get("abstract") or ""
    for sent in re.split(r"(?<=[.!?。！？])\s+", absx):
        if any(t.lower() in sent.lower() for c in concepts for t in c["all_terms"]):
            return sent[:width]
    return (rec.get("title") or "")[:width]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--terms", default=None)
    ap.add_argument("--glossary", default=None,
                    help="extra glossary.md; built-in resources/glossary.md always used")
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--max-queries", type=int, default=12)
    ap.add_argument("--per-query", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    work, out = Path(args.work), Path(args.out)
    ev = out / "evidence"
    for d in (work, out, ev):
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

    def walk(o, acc):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in QUESTION_KEYS and isinstance(v, str) and len(v) > 10:
                    acc.append(v)
                else:
                    walk(v, acc)
        elif isinstance(o, list):
            for v in o:
                walk(v, acc)
    texts = []
    walk(case, texts)
    if task_md:
        texts.append(task_md[:4000])
    question = "\n".join(texts)

    skill_dir = Path(__file__).resolve().parent.parent
    gloss_paths = [skill_dir / "resources" / "glossary.md"]
    if args.glossary:
        gloss_paths.append(args.glossary)
    if (work / "glossary_extra.md").exists():
        gloss_paths.append(work / "glossary_extra.md")
    concepts, origin = build_concepts(
        question, args.terms or str(work / "terms.json"), gloss_paths)

    year_from = year_to = None
    databases = ["crossref", "openalex"]
    if Path(args.terms or str(work / "terms.json")).exists():
        td = json.loads(Path(args.terms or str(work / "terms.json")).read_text(
            encoding="utf-8"))
        year_from, year_to = td.get("year_from"), td.get("year_to")
        databases = [d for d in td.get("databases", databases) if d in SOURCES]
    if any("europepmc" in (c.get("name") or "").lower() for c in concepts):
        pass

    # ---------- retrieval with expanded queries
    queries = []
    core = " AND ".join("(%s)" % " OR ".join('"%s"' % t for t in c["all_terms"][:4])
                        for c in concepts[:4])
    if core:
        queries.append(("core-expanded-AND", core))
    for c in concepts:
        if len(c["all_terms"]) > 1:
            queries.append(("expand-%s" % c["name"],
                            " OR ".join('"%s"' % t for t in c["all_terms"][:6])))
    queries = queries[:args.max_queries]

    failures, pool, seen = [], [], {}
    ledger = []

    def add(recs, source, query, url):
        new = 0
        for r in recs:
            key = r.get("doi") or norm_title(r.get("title"))
            if not key:
                continue
            if key in seen:
                seen[key]["provenance"].append({"source": source, "query": query,
                                                "url": url})
                if not seen[key].get("abstract") and r.get("abstract"):
                    seen[key]["abstract"] = r["abstract"]
                ledger.append({"id": key, "title": r.get("title", ""),
                               "decision": "excluded", "stage": "dedup",
                               "reason_code": "E3",
                               "reason": CODES["E3"] + " (kept canonical record)",
                               "evidence": "", "source_db": source,
                               "year": r.get("year"), "doi": r.get("doi") or ""})
                continue
            r["provenance"] = r.get("provenance") or [{"source": source,
                                                       "query": query, "url": url}]
            seen[key] = r
            pool.append(r)
            new += 1
        return new

    local = ingest_local(args.input)
    add(local, "local-snapshot", None, None)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"phase": "local-ingest", "records": len(local)},
                           ensure_ascii=False) + "\n")

    for tag, query in queries:
        for db in databases:
            if args.offline:
                continue
            t0 = time.time()
            recs, err, url = SOURCES[db](query, args.per_query, args.timeout)
            new = add(recs, db, query, url)
            with open(log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"tag": tag, "source": db, "query": query,
                                    "url": url, "ok": err is None, "error": err,
                                    "hits": len(recs), "new_unique": new,
                                    "elapsed_s": round(time.time() - t0, 2)},
                                   ensure_ascii=False) + "\n")
            if err:
                failures.append({"source": db, "query": query, "error": err})

    # ---------- two-stage screening
    n_identified = len(pool) + sum(1 for l in ledger if l["reason_code"] == "E3")
    n_dup = sum(1 for l in ledger if l["reason_code"] == "E3")
    included, stage1_excl, stage2_excl = [], 0, 0
    for r in pool:
        score = relevance_score(r, concepts)
        r["relevance_score"] = score
        title_hits = concept_hits(r.get("title") or "", concepts)
        abs_hits = concept_hits(r.get("abstract") or "", concepts)
        entry = {"id": r.get("doi") or norm_title(r.get("title")),
                 "title": r.get("title", ""), "year": r.get("year"),
                 "doi": r.get("doi") or "",
                 "source_db": ";".join(sorted({p["source"] for p in r["provenance"]})),
                 "score": score}
        if r.get("type") in ("retraction", "retracted"):
            entry.update(decision="excluded", stage="type", reason_code="E4",
                         reason=CODES["E4"], evidence="")
            ledger.append(entry)
            continue
        if (year_from and r.get("year") and r["year"] < year_from) or \
           (year_to and r.get("year") and r["year"] > year_to):
            entry.update(decision="excluded", stage="type", reason_code="E5",
                         reason=CODES["E5"], evidence="")
            ledger.append(entry)
            continue
        if title_hits == 0 and abs_hits < 2:
            entry.update(decision="excluded", stage="title", reason_code="E1",
                         reason=CODES["E1"], evidence=(r.get("title") or "")[:220])
            ledger.append(entry)
            stage1_excl += 1
            continue
        if score < args.threshold:
            entry.update(decision="excluded", stage="abstract", reason_code="E2",
                         reason=CODES["E2"] + " (score %.3f < %.2f)"
                         % (score, args.threshold),
                         evidence=evidence_snippet(r, concepts))
            ledger.append(entry)
            stage2_excl += 1
            continue
        code = "I1" if (title_hits >= max(1, len(concepts) // 2) and abs_hits >= 1) \
            else ("I3" if not r.get("abstract") else "I2")
        entry.update(decision="included", stage="abstract", reason_code=code,
                     reason=CODES[code], evidence=evidence_snippet(r, concepts))
        ledger.append(entry)
        included.append(r)

    included.sort(key=lambda x: -x["relevance_score"])

    # ---------- outputs
    with open(out / "screening_ledger.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "title", "year", "doi", "source_db",
                                          "decision", "stage", "reason_code",
                                          "reason", "score", "evidence"])
        w.writeheader()
        for l in sorted(ledger, key=lambda x: (x["decision"], -(x.get("score") or 0))):
            l.setdefault("score", "")
            w.writerow(l)
    with open(out / "prisma_flow.md", "w", encoding="utf-8") as f:
        f.write("# Screening flow (PRISMA-style)\n\n")
        f.write("- records identified (all sources, before dedup): %d\n" % n_identified)
        f.write("- duplicates removed (E3, kept canonical copy): %d\n" % n_dup)
        f.write("- records screened (title/abstract): %d\n" % len(pool))
        f.write("- excluded at title screen (E1): %d\n" % stage1_excl)
        f.write("- excluded at abstract screen (E2): %d\n" % stage2_excl)
        f.write("- excluded by type/year (E4/E5): %d\n"
                % sum(1 for l in ledger if l["reason_code"] in ("E4", "E5")))
        f.write("- included: %d (I1 core %d, I2 peripheral %d, I3 uncertain %d)\n"
                % (len(included),
                   sum(1 for l in ledger if l["reason_code"] == "I1"),
                   sum(1 for l in ledger if l["reason_code"] == "I2"),
                   sum(1 for l in ledger if l["reason_code"] == "I3")))
        f.write("\nReason codes: " + "; ".join("%s=%s" % kv for kv in CODES.items()) + "\n")
    with open(out / "candidates.md", "w", encoding="utf-8") as f:
        f.write("# Included literature after two-stage screening (ranked)\n\n")
        f.write("Threshold %.2f; rubric in resources/screening_rubric.md. "
                "Exclusions with reasons: screening_ledger.csv.\n\n" % args.threshold)
        for i, r in enumerate(included[:40], 1):
            code = next((l["reason_code"] for l in ledger
                         if l["id"] == (r.get("doi") or norm_title(r.get("title")))
                         and l["decision"] == "included"), "?")
            f.write("## %d. %s\n- score %.3f | code %s | %s | %s | DOI: %s\n- %s\n\n"
                    % (i, r.get("title") or "(no title)", r["relevance_score"], code,
                       r.get("year") or "?", (r.get("venue") or "?")[:80],
                       r.get("doi") or "none",
                       evidence_snippet(r, concepts, 300)))
    with open(out / "omissions.md", "w", encoding="utf-8") as f:
        f.write("# Omissions and near-misses (honest gaps)\n\n")
        for c in concepts:
            n = sum(1 for r in pool if any(t.lower() in
                    ((r.get("title") or "") + (r.get("abstract") or "")).lower()
                    for t in c["all_terms"]))
            if n == 0:
                f.write("- concept **%s** (%s): no record found at all — coverage gap.\n"
                        % (c["name"], ", ".join(c["all_terms"][:5])))
        near = [l for l in ledger if l["reason_code"] == "E2"]
        near.sort(key=lambda x: -(x.get("score") or 0))
        if near:
            f.write("\n## Closest exclusions (E2, highest scores below threshold)\n\n")
            for l in near[:10]:
                f.write("- %s (%s, score %.3f)\n" % (l["title"][:100], l["year"] or "?",
                                                     l.get("score") or 0))
    with open(out / "expansion_report.md", "w", encoding="utf-8") as f:
        f.write("# Terminology expansion report\n\n- origin: %s\n\n" % origin)
        for c in concepts:
            f.write("- **%s** -> %s\n" % (c["name"], ", ".join(c["all_terms"])))
        f.write("\n## Queries executed (%d)\n\n" % len(queries))
        for tag, q in queries:
            f.write("- [%s] %s\n" % (tag, q[:200]))

    status = "success"
    problems = []
    if args.offline:
        status, problems = "partial", ["offline: only local snapshots used"]
    if failures:
        problems.append("source failures: " + ", ".join(sorted({f["source"] for f in failures})))
    uncovered = [c["name"] for c in concepts if not any(
        t.lower() in " ".join((r.get("title") or "") + " " + (r.get("abstract") or "")
                              for r in pool).lower() for t in c["all_terms"])]
    if uncovered:
        status = "partial"
        problems.append("uncovered concepts: " + ", ".join(uncovered))
    (out / "candidates.json").write_text(json.dumps(
        {"included": included, "screened_pool_size": len(pool),
         "concepts": concepts, "status": status, "problems": problems},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ENGINE_STATUS": status, "identified": n_identified,
                      "screened": len(pool), "included": len(included),
                      "excluded_E1": stage1_excl, "excluded_E2": stage2_excl,
                      "concepts": [c["name"] for c in concepts],
                      "queries": len(queries), "problems": problems},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
