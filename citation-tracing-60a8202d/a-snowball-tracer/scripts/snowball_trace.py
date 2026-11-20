#!/usr/bin/env python3
"""Direction-aware multi-hop snowball tracer (backward references + forward citations).

Stdlib only (Python 3.8+). Deterministic, budget-bounded, fully provenance-logged.

What it does
------------
1. Discovers the local evidence corpus: scans /input, ./environment, /app/work and the
   current directory for JSON / JSONL / CSV / TSV / edge-list files and parses
   heterogeneous scholarly-record shapes (Crossref, EuropePMC, OpenAlex,
   Semantic Scholar, generic edge lists). Every parsed record and every parsed
   reference/citation pointer keeps a source locator (file + JSON path / line no).
2. Resolves the seed work from case.json identifiers (DOI, arXiv id, title).
3. Backward expansion: BFS over the seed's reference list, layer by layer.
4. Forward expansion: uses explicit citation lists when a source provides them,
   AND derives forward edges by inverting the local reference graph (works in the
   corpus whose reference list resolves to the seed or to an expanded node).
   This recovers direction even for sources that only expose reference lists.
5. Pruning / stop rules: per-layer caps, total node budget, year window, optional
   keyword gate taken from the task text, diminishing-yield stop. Every pruned
   branch and every stop decision is written to the log with its reason.
6. Writes a machine-readable trace JSON plus a human-readable evidence table,
   and assembles /app/output/result.json mirroring the case output_contract.

Nothing is fabricated: a work appears in the output only if it was parsed from a
real local record (or, with --allow-net, from a live API response whose URL is
recorded). Unresolved reference pointers are reported as stubs, never as full works.

Usage
-----
    python3 snowball_trace.py --case /input/case.json --out /app/output \
        [--workdir /app/work] [--max-depth 3] [--max-nodes 250] [--allow-net]

Exit code is 0 even for partial results; the status field carries the truth.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# ----------------------------------------------------------------------------- config

DEFAULT_ROOTS = ["/input", "./environment", "/app/work", "."]
DATA_DIR_NAMES = {"materials", "material", "data", "corpus", "graph", "graphs",
                  "references", "refs", "citations", "papers", "works", "dump",
                  "dumps", "import", "imports", "state", "states", "sources"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "output"}
SKIP_FILES = {"result.json", "trace_graph.json", "run_log.json", "verify_report.json",
              "dry-run.json", "arm-manifest-preflight.json", "case.json"}
MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_FILES = 400
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "be", "been", "via", "using",
    "based", "study", "analysis", "review", "towards", "toward", "new", "its",
    "their", "we", "this", "that", "these", "those", "between", "into", "over",
}

# ----------------------------------------------------------------------------- utils


def norm_doi(value):
    if not value:
        return None
    v = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v or None


def norm_title(value):
    if not value:
        return ""
    v = re.sub(r"<[^>]+>", " ", str(value))
    v = re.sub(r"[^a-z0-9]+", " ", v.lower())
    return " ".join(v.split())


def title_tokens(value):
    return {t for t in norm_title(value).split() if t and t not in STOPWORDS}


def norm_arxiv(value):
    if not value:
        return None
    v = str(value).strip().lower()
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", v)
    if m:
        return m.group(1)
    m = re.search(r"([a-z\-]+/\d{7})(v\d+)?", v)
    return m.group(1) if m else None


def first_surname(authors):
    if not authors:
        return None
    a = authors[0]
    if isinstance(a, dict):
        name = a.get("family") or a.get("name") or ""
    else:
        name = str(a)
    name = name.split(",")[0].strip().split()
    return name[-1].lower() if name else None


def token_jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))

# ----------------------------------------------------------------------------- corpus


class Work:
    __slots__ = ("key", "doi", "arxiv", "title", "year", "authors", "venue",
                 "type", "refs", "cites", "ref_count_hint", "cited_by_hint",
                 "locator", "stub")

    def __init__(self, key, locator):
        self.key = key
        self.doi = None
        self.arxiv = None
        self.title = ""
        self.year = None
        self.authors = []
        self.venue = None
        self.type = None
        self.refs = []          # list of pointer dicts {doi, arxiv, title, locator}
        self.cites = []         # list of pointer dicts (forward, as given by source)
        self.ref_count_hint = None
        self.cited_by_hint = None
        self.locator = locator  # {file, pointer}
        self.stub = False

    def brief(self):
        return {
            "key": self.key,
            "doi": self.doi,
            "arxiv": self.arxiv,
            "title": self.title,
            "year": self.year,
            "authors": [a if isinstance(a, str) else
                        (a.get("name") or " ".join(x for x in [a.get("given"), a.get("family")] if x))
                        for a in self.authors][:8],
            "venue": self.venue,
            "type": self.type,
            "cited_by_hint": self.cited_by_hint,
            "locator": self.locator,
            "stub": self.stub,
        }


class Corpus:
    def __init__(self):
        self.works = {}          # key -> Work
        self.doi_index = {}
        self.arxiv_index = {}
        self.title_index = {}
        self.edges = []          # {src_key, dst_key, kind, locator} kind: references|cites
        self.files_scanned = []
        self.parse_notes = []
        self._seq = 0

    # -- key management ------------------------------------------------------
    def _fresh_key(self, hint):
        self._seq += 1
        return "w%06d" % self._seq

    def canonical_key(self, doi=None, arxiv=None, title=None, year=None):
        if doi:
            return "doi:" + doi
        if arxiv:
            return "arxiv:" + arxiv
        if title:
            t = norm_title(title)
            if t:
                return "t:" + (t[:80] + ("|" + str(year) if year else ""))
        return None

    def add_work(self, work):
        key = self.canonical_key(work.doi, work.arxiv, work.title, work.year) \
            or self._fresh_key(work.title)
        existing = self.works.get(key)
        if existing is not None:
            # merge: fill missing fields, union pointers, keep both locators
            for field in ("doi", "arxiv", "title", "year", "venue", "type",
                          "ref_count_hint", "cited_by_hint"):
                if not getattr(existing, field) and getattr(work, field):
                    setattr(existing, field, getattr(work, field))
            if not existing.authors and work.authors:
                existing.authors = work.authors
            if existing.stub and not work.stub:
                existing.stub = False
                existing.locator = work.locator
            seen = {(p.get("doi"), p.get("arxiv"), norm_title(p.get("title")))
                    for p in existing.refs}
            for p in work.refs:
                sig = (p.get("doi"), p.get("arxiv"), norm_title(p.get("title")))
                if sig not in seen:
                    existing.refs.append(p)
                    seen.add(sig)
            seen = {(p.get("doi"), p.get("arxiv"), norm_title(p.get("title")))
                    for p in existing.cites}
            for p in work.cites:
                sig = (p.get("doi"), p.get("arxiv"), norm_title(p.get("title")))
                if sig not in seen:
                    existing.cites.append(p)
                    seen.add(sig)
            self._reindex(existing)
            return existing
        work.key = key
        self.works[key] = work
        self._reindex(work)
        return work

    def _reindex(self, work):
        if work.doi:
            self.doi_index[work.doi] = work.key
        if work.arxiv:
            self.arxiv_index[work.arxiv] = work.key
        t = norm_title(work.title)
        if t:
            self.title_index.setdefault(t, work.key)

    def lookup(self, doi=None, arxiv=None, title=None):
        if doi and norm_doi(doi) in self.doi_index:
            return self.works[self.doi_index[norm_doi(doi)]]
        if arxiv and norm_arxiv(arxiv) in self.arxiv_index:
            return self.works[self.arxiv_index[norm_arxiv(arxiv)]]
        if title and norm_title(title) in self.title_index:
            return self.works[self.title_index[norm_title(title)]]
        return None

# ----------------------------------------------------------------------------- parsers


def _authors_from(value):
    out = []
    if isinstance(value, list):
        for a in value[:25]:
            if isinstance(a, dict):
                if "family" in a or "given" in a:
                    out.append({"given": a.get("given"), "family": a.get("family")})
                elif "name" in a:
                    out.append({"name": a.get("name")})
                elif "author" in a and isinstance(a["author"], dict):
                    out.append({"name": a["author"].get("display_name")})
            elif isinstance(a, str):
                out.append({"name": a})
    elif isinstance(value, str):  # EuropePMC authorString
        for part in value.split(",")[:25]:
            part = part.strip()
            if part:
                out.append({"name": part})
    return out


def _year_from(obj):
    for k in ("year", "pubYear", "publication_year", "publishedYear"):
        v = obj.get(k)
        if v:
            try:
                return int(str(v)[:4])
            except ValueError:
                pass
    for k in ("issued", "published", "published-print", "published-online",
              "created", "publication_date", "firstPublicationDate"):
        v = obj.get(k)
        if isinstance(v, dict) and "date-parts" in v:
            try:
                return int(v["date-parts"][0][0])
            except (TypeError, IndexError, ValueError):
                pass
        elif isinstance(v, str):
            m = re.match(r"(\d{4})", v)
            if m:
                return int(m.group(1))
    return None


def _pointer_from(obj, locator):
    if isinstance(obj, str):
        s = obj.strip()
        if norm_doi(s):
            return {"doi": norm_doi(s), "locator": locator}
        if norm_arxiv(s):
            return {"arxiv": norm_arxiv(s), "locator": locator}
        if s:
            return {"title": s, "locator": locator}
        return None
    if not isinstance(obj, dict):
        return None
    p = {"locator": locator}
    doi = norm_doi(obj.get("DOI") or obj.get("doi"))
    if doi:
        p["doi"] = doi
    ax = norm_arxiv(obj.get("arxiv") or obj.get("arxiv_id") or
                    (obj.get("externalIds") or {}).get("ArXiv") if isinstance(obj.get("externalIds"), dict) else None)
    if ax:
        p["arxiv"] = ax
    title = obj.get("article-title") or obj.get("title") or obj.get("display_name") \
        or obj.get("unstructured")
    if isinstance(title, list):
        title = title[0] if title else None
    if title:
        p["title"] = str(title)
    for k in ("id", "paperId", "pmid", "pmcid"):
        if obj.get(k):
            p.setdefault("ext_ids", {})[k] = str(obj[k])
    if obj.get("year") or obj.get("pubYear"):
        try:
            p["year"] = int(str(obj.get("year") or obj.get("pubYear"))[:4])
        except ValueError:
            pass
    return p if (p.get("doi") or p.get("arxiv") or p.get("title") or p.get("ext_ids")) else None


def work_from_record(obj, locator):
    """Try to interpret one JSON object as a scholarly work record."""
    if not isinstance(obj, dict):
        return None
    title = obj.get("title") or obj.get("display_name")
    if isinstance(title, list):
        title = title[0] if title else None
    doi = norm_doi(obj.get("DOI") or obj.get("doi"))
    ids = obj.get("externalIds") if isinstance(obj.get("externalIds"), dict) else {}
    ax = norm_arxiv(obj.get("arxiv") or obj.get("arxiv_id") or ids.get("ArXiv"))
    if not (title or doi or ax):
        return None
    w = Work(None, locator)
    w.doi = doi
    w.arxiv = ax
    w.title = str(title) if title else ""
    w.year = _year_from(obj)
    w.authors = _authors_from(obj.get("author") or obj.get("authors")
                              or obj.get("authorString") or obj.get("authorships"))
    venue = obj.get("container-title") or obj.get("venue") or obj.get("journalTitle") \
        or obj.get("bookTitle")
    if isinstance(venue, list):
        venue = venue[0] if venue else None
    if isinstance(venue, dict):
        venue = venue.get("display_name")
    w.venue = venue
    w.type = obj.get("type") or obj.get("pubType") or obj.get("type_crossref")
    for hint_k, attr in (("is-referenced-by-count", "cited_by_hint"),
                         ("citedByCount", "cited_by_hint"),
                         ("citationCount", "cited_by_hint"),
                         ("cited_by_count", "cited_by_hint"),
                         ("reference-count", "ref_count_hint"),
                         ("referenceCount", "ref_count_hint")):
        v = obj.get(hint_k)
        if isinstance(v, int) and getattr(w, attr) is None:
            setattr(w, attr, v)
    for i, r in enumerate(obj.get("reference") or obj.get("references") or []):
        p = _pointer_from(r, dict(locator, pointer="%s/references/%d" % (locator["pointer"], i)))
        if p:
            w.refs.append(p)
    ref_list = obj.get("referenceList")
    if isinstance(ref_list, dict):
        for i, r in enumerate(ref_list.get("reference") or []):
            p = _pointer_from(r, dict(locator, pointer="%s/referenceList/%d" % (locator["pointer"], i)))
            if p:
                w.refs.append(p)
    for i, c in enumerate(obj.get("citations") or []):
        p = _pointer_from(c, dict(locator, pointer="%s/citations/%d" % (locator["pointer"], i)))
        if p:
            w.cites.append(p)
    cit_list = obj.get("citationList")
    if isinstance(cit_list, dict):
        for i, c in enumerate(cit_list.get("citation") or []):
            p = _pointer_from(c, dict(locator, pointer="%s/citationList/%d" % (locator["pointer"], i)))
            if p:
                w.cites.append(p)
    return w


def walk_json(obj, path, file_path, corpus, depth=0):
    """Recursively find work records inside an arbitrary JSON document."""
    if depth > 12:
        return
    if isinstance(obj, dict):
        w = work_from_record(obj, {"file": file_path, "pointer": path or "$"})
        if w is not None and (w.title or w.doi):
            corpus.add_work(w)
            return  # do not descend into a recognized record
        for k, v in obj.items():
            if k in ("reference", "references", "citations", "referenceList",
                     "citationList", "author", "authors", "authorships"):
                continue
            walk_json(v, "%s/%s" % (path, k), file_path, corpus, depth + 1)
    elif isinstance(obj, list):
        if len(obj) > 20000:
            corpus.parse_notes.append("list truncated at %s (%d items)" % (path, len(obj)))
        for i, v in enumerate(obj[:20000]):
            walk_json(v, "%s/%d" % (path, i), file_path, corpus, depth + 1)


def parse_csv_file(path, corpus):
    file_path = str(path)
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if sample.strip() else csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames:
            return
        cols = {c.lower().strip(): c for c in reader.fieldnames}
        # edge-list shape?
        src_c = next((cols[c] for c in ("from", "source", "src", "citing", "citing_doi") if c in cols), None)
        dst_c = next((cols[c] for c in ("to", "target", "dst", "cited", "cited_doi") if c in cols), None)
        for i, row in enumerate(reader):
            loc = {"file": file_path, "pointer": "row/%d" % (i + 2)}
            if src_c and dst_c and not any(c in cols for c in ("title", "doi")):
                s, d = (row.get(src_c) or "").strip(), (row.get(dst_c) or "").strip()
                if s and d:
                    corpus.edges.append({"src_raw": s, "dst_raw": d, "kind": "references",
                                         "locator": loc})
                continue
            w = work_from_record({k: v for k, v in row.items() if v}, loc)
            if w:
                corpus.add_work(w)


EDGE_RE = re.compile(r"^\s*[\"']?([^\s\"',;\->]+)[\"']?\s*(?:->|,|\t|;|\s)\s*[\"']?([^\s\"',;]+)[\"']?\s*$")


def parse_edgelist_file(path, corpus):
    file_path = str(path)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line or line.startswith(("#", "%", "//")):
                continue
            m = EDGE_RE.match(line)
            if m and (m.group(1) != m.group(2)):
                corpus.edges.append({"src_raw": m.group(1), "dst_raw": m.group(2),
                                     "kind": "references",
                                     "locator": {"file": file_path, "pointer": "line/%d" % (i + 1)}})


def discover_files(roots):
    seen, out = set(), []
    exts = (".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".edgelist", ".edges", ".graph")
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack and len(out) < MAX_FILES:
            node, depth = stack.pop()
            try:
                if node.is_dir():
                    if node.name in SKIP_DIRS or node.name.startswith("."):
                        continue
                    if depth <= 6:
                        for child in sorted(node.iterdir()):
                            stack.append((child, depth + 1))
                elif node.suffix.lower() in exts and node.name not in SKIP_FILES:
                    rp = str(node.resolve())
                    if rp in seen or node.stat().st_size > MAX_FILE_BYTES:
                        continue
                    seen.add(rp)
                    out.append(node)
            except (OSError, PermissionError):
                continue
    return out


def build_corpus(roots, log):
    corpus = Corpus()
    files = discover_files(roots)
    for path in files:
        file_path = str(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                with open(path, encoding="utf-8", errors="replace") as fh:
                    walk_json(json.load(fh), "$", file_path, corpus)
                corpus.files_scanned.append(file_path)
            elif suffix in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk_json(json.loads(line), "$/%d" % i, file_path, corpus)
                        except json.JSONDecodeError:
                            corpus.parse_notes.append("bad JSONL line %s:%d" % (file_path, i + 1))
                corpus.files_scanned.append(file_path)
            elif suffix in (".csv", ".tsv"):
                parse_csv_file(path, corpus)
                corpus.files_scanned.append(file_path)
            elif suffix in (".edgelist", ".edges", ".graph"):
                parse_edgelist_file(path, corpus)
                corpus.files_scanned.append(file_path)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            corpus.parse_notes.append("skipped %s: %s" % (file_path, exc))
    log.append("scanned %d data files, parsed %d work records, %d raw edges"
               % (len(corpus.files_scanned), len(corpus.works), len(corpus.edges)))
    return corpus

# ----------------------------------------------------------------------------- graph


def resolve_pointer(corpus, pointer):
    return corpus.lookup(doi=pointer.get("doi"), arxiv=pointer.get("arxiv"),
                         title=pointer.get("title"))


def build_graph(corpus, log):
    """Resolve reference/citation pointers to corpus works; invert local refs for
    forward edges. Returns adjacency: back[key] -> [(key, locator)], fwd[key] -> [...]."""
    back, fwd = {}, {}

    def add(adj, a, b, loc):
        adj.setdefault(a, {})
        if b not in adj[a]:
            adj[a][b] = loc

    # raw edge-list rows (from / to may be DOI, arXiv id, or title)
    for e in corpus.edges:
        src = corpus.lookup(doi=e["src_raw"], arxiv=e["src_raw"], title=e["src_raw"])
        dst = corpus.lookup(doi=e["dst_raw"], arxiv=e["dst_raw"], title=e["dst_raw"])
        if src is None:
            src = corpus.add_work(stub_from_pointer({"doi": norm_doi(e["src_raw"]),
                                                     "arxiv": norm_arxiv(e["src_raw"]),
                                                     "title": None if (norm_doi(e["src_raw"]) or norm_arxiv(e["src_raw"])) else e["src_raw"]},
                                                    e["locator"]))
        if dst is None:
            dst = corpus.add_work(stub_from_pointer({"doi": norm_doi(e["dst_raw"]),
                                                     "arxiv": norm_arxiv(e["dst_raw"]),
                                                     "title": None if (norm_doi(e["dst_raw"]) or norm_arxiv(e["dst_raw"])) else e["dst_raw"]},
                                                    e["locator"]))
        add(back, src.key, dst.key, e["locator"])
        add(fwd, dst.key, src.key, e["locator"])

    for w in list(corpus.works.values()):
        for p in w.refs:
            target = resolve_pointer(corpus, p)
            if target is None:
                target = corpus.add_work(stub_from_pointer(p, p["locator"]))
            add(back, w.key, target.key, p["locator"])
            add(fwd, target.key, w.key, p["locator"])
        for p in w.cites:
            source = resolve_pointer(corpus, p)
            if source is None:
                source = corpus.add_work(stub_from_pointer(p, p["locator"]))
            add(fwd, w.key, source.key, p["locator"])
            add(back, source.key, w.key, p["locator"])
    n_back = sum(len(v) for v in back.values())
    n_fwd = sum(len(v) for v in fwd.values())
    n_inverted = sum(1 for w in corpus.works.values() for p in w.refs)
    log.append("graph: %d backward edges, %d forward edges "
               "(%d reference pointers inverted for direction recovery)"
               % (n_back, n_fwd, n_inverted))
    return back, fwd


def stub_from_pointer(pointer, locator):
    w = Work(None, locator)
    w.doi = pointer.get("doi")
    w.arxiv = pointer.get("arxiv")
    w.title = pointer.get("title") or ""
    w.year = pointer.get("year")
    w.stub = True
    return w

# ----------------------------------------------------------------------------- seed


def load_case(case_path):
    with open(case_path, encoding="utf-8") as fh:
        case = json.load(fh)
    return case


def case_text(case):
    parts = []
    def rec(o):
        if isinstance(o, str):
            parts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec({k: v for k, v in case.items() if k != "output_contract"})
    return "\n".join(parts)


def find_seed_identifiers(case):
    text = json.dumps(case, ensure_ascii=False)
    ids = {"dois": [], "arxiv": [], "titles": []}
    for m in re.finditer(r"10\.\d{4,9}/[^\s\"',}\]]+", text):
        d = norm_doi(m.group(0))
        if d and d not in ids["dois"]:
            ids["dois"].append(d)
    for m in re.finditer(r"\b\d{4}\.\d{4,5}(v\d+)?\b", text):
        a = norm_arxiv(m.group(0))
        if a and a not in ids["arxiv"]:
            ids["arxiv"].append(a)
    for key in ("seed_title", "title", "paper_title", "seed"):
        v = case.get(key)
        if isinstance(v, str) and len(v) > 12:
            ids["titles"].append(v)
    seed_obj = case.get("seed_paper") or case.get("seed") or {}
    if isinstance(seed_obj, dict):
        for key in ("title", "paper_title"):
            if isinstance(seed_obj.get(key), str):
                ids["titles"].append(seed_obj[key])
    return ids


def resolve_seed(corpus, case, log):
    ids = find_seed_identifiers(case)
    attempts = []
    for d in ids["dois"]:
        w = corpus.lookup(doi=d)
        attempts.append({"by": "doi", "value": d, "hit": bool(w)})
        if w:
            log.append("seed resolved by DOI %s -> %s" % (d, w.key))
            return w, ids, attempts
    for a in ids["arxiv"]:
        w = corpus.lookup(arxiv=a)
        attempts.append({"by": "arxiv", "value": a, "hit": bool(w)})
        if w:
            log.append("seed resolved by arXiv %s -> %s" % (a, w.key))
            return w, ids, attempts
    for t in ids["titles"]:
        w = corpus.lookup(title=t)
        attempts.append({"by": "title", "value": t, "hit": bool(w)})
        if w:
            return w, ids, attempts
    # fuzzy title fallback
    q = None
    for t in ids["titles"]:
        q = title_tokens(t)
        if q:
            break
    if q:
        best, best_s = None, 0.0
        for w in corpus.works.values():
            s = token_jaccard(q, title_tokens(w.title))
            if s > best_s:
                best, best_s = w, s
        attempts.append({"by": "title_fuzzy", "value": " ".join(sorted(q))[:120],
                         "hit": bool(best and best_s >= 0.75), "score": round(best_s, 3)})
        if best and best_s >= 0.75:
            log.append("seed resolved by fuzzy title (%.2f) -> %s" % (best_s, best.key))
            return best, ids, attempts
    log.append("WARNING: seed not found in local corpus")
    return None, ids, attempts

# ----------------------------------------------------------------------------- traversal


def snowball(corpus, back, fwd, seed, case, args, log):
    keywords = title_tokens(case_text(case)) - title_tokens(seed.title)
    year_min = args.year_min
    if year_min is None and seed.year:
        year_min = seed.year - args.year_span
    visited = {seed.key: {"layer": 0, "direction": "seed", "via": None}}
    edges_out = []
    pruning_log, stop_log = [], []
    frontier = [seed.key]
    stats = {"backward_edges": 0, "forward_edges": 0, "stub_nodes": 0}

    for layer in range(1, args.max_depth + 1):
        next_frontier = []
        layer_added = 0
        for parent_key in frontier:
            if len(visited) >= args.max_nodes:
                stop_log.append({"layer": layer, "rule": "max_nodes",
                                 "detail": "node budget %d reached" % args.max_nodes})
                break
            parent_dir = visited[parent_key]["direction"]
            expand_back = parent_dir in ("seed", "backward") or layer == 1
            expand_fwd = parent_dir in ("seed", "forward") or layer == 1
            for direction, adj in (("backward", back), ("forward", fwd)):
                if direction == "backward" and not expand_back:
                    continue
                if direction == "forward" and not expand_fwd:
                    continue
                nbrs = adj.get(parent_key, {})
                if len(nbrs) > args.max_branch:
                    # prune the highest-degree branches: keep best-scored subset
                    scored = sorted(
                        nbrs.items(),
                        key=lambda kv: (
                            (corpus.works[kv[0]].cited_by_hint or 0),
                            bool(title_tokens(corpus.works[kv[0]].title) & keywords),
                            -(corpus.works[kv[0]].year or 0),
                        ), reverse=True)
                    kept, dropped = scored[:args.max_branch], scored[args.max_branch:]
                    for k, _ in dropped:
                        pruning_log.append({
                            "layer": layer, "parent": parent_key, "pruned": k,
                            "direction": direction, "rule": "max_branch",
                            "detail": "branch degree %d > cap %d; kept highest "
                                      "cited-by/keyword-relevant children"
                                      % (len(nbrs), args.max_branch)})
                    nbrs = dict(kept)
                for child_key, loc in nbrs.items():
                    child = corpus.works[child_key]
                    if child_key in visited:
                        continue
                    if direction == "backward" and year_min and child.year \
                            and child.year < year_min \
                            and not (child.cited_by_hint or 0) >= args.classic_cited_by:
                        pruning_log.append({
                            "layer": layer, "parent": parent_key, "pruned": child_key,
                            "direction": direction, "rule": "year_window",
                            "detail": "year %s < %s and cited_by_hint %s < %d "
                                      "(classic threshold)" % (child.year, year_min,
                                                               child.cited_by_hint,
                                                               args.classic_cited_by)})
                        continue
                    visited[child_key] = {"layer": layer, "direction": direction,
                                          "via": parent_key}
                    edges_out.append({
                        "from": parent_key, "to": child_key, "direction": direction,
                        "layer": layer,
                        "meaning": ("citing work -> cited work (reference)"
                                    if direction == "backward"
                                    else "cited work -> citing work (citation)"),
                        "source": loc})
                    stats[direction + "_edges"] += 1
                    if child.stub:
                        stats["stub_nodes"] += 1
                    next_frontier.append(child_key)
                    layer_added += 1
                    if len(visited) >= args.max_nodes:
                        break
        if layer_added == 0:
            stop_log.append({"layer": layer, "rule": "diminishing_yield",
                             "detail": "no new nodes; traversal stopped before "
                                       "max_depth %d" % args.max_depth})
            break
        frontier = next_frontier
        log.append("layer %d: +%d nodes (total %d)" % (layer, layer_added, len(visited)))
    return visited, edges_out, pruning_log, stop_log, stats

# ----------------------------------------------------------------------------- optional net


def maybe_fetch_crossref(seed, log, allow_net):
    if not allow_net or not seed or not seed.doi:
        return None
    url = "https://api.crossref.org/works/" + seed.doi
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.load(resp)
        log.append("live Crossref fetch ok: %s" % url)
        return {"url": url, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message_keys": sorted((data.get("message") or {}).keys())[:20]}
    except Exception as exc:  # network is best-effort only
        log.append("live Crossref fetch failed (non-fatal): %s" % exc)
        return None

# ----------------------------------------------------------------------------- result


def assemble_result(case, case_path, seed, seed_attempts, visited, edges_out,
                    pruning_log, stop_log, stats, corpus, log, args, net_note):
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    nodes = []
    for key, meta in sorted(visited.items(), key=lambda kv: (kv[1]["layer"], kv[0])):
        w = corpus.works[key]
        b = w.brief()
        b.update(meta)
        nodes.append(b)
    status = "ok" if seed else "partial"
    if seed and not edges_out:
        status = "partial"
    notes = []
    if seed is None:
        notes.append("seed work not found in local corpus; only corpus summary delivered")
    if stats["stub_nodes"]:
        notes.append("%d nodes are unresolved reference stubs (metadata incomplete "
                     "in the local sources); they are marked stub=true" % stats["stub_nodes"])
    if corpus.parse_notes:
        notes.append("parse notes: " + "; ".join(corpus.parse_notes[:5]))
    result = {
        "case_id": case_id,
        "skill": "dir-aware-snowball-tracer",
        "status": status,
        "seed": seed.brief() if seed else None,
        "seed_resolution_attempts": seed_attempts,
        "parameters": {"max_depth": args.max_depth, "max_nodes": args.max_nodes,
                       "max_branch": args.max_branch, "year_min_effective":
                       (args.year_min or (seed.year - args.year_span if seed and seed.year else None))},
        "nodes": nodes,
        "edges": edges_out,
        "layers": [
            {"layer": l,
             "n_nodes": sum(1 for m in visited.values() if m["layer"] == l),
             "n_backward": sum(1 for m in visited.values()
                               if m["layer"] == l and m["direction"] == "backward"),
             "n_forward": sum(1 for m in visited.values()
                              if m["layer"] == l and m["direction"] == "forward")}
            for l in range(0, args.max_depth + 1)
            if any(m["layer"] == l for m in visited.values())
        ],
        "pruning_log": pruning_log,
        "stop_log": stop_log,
        "stats": dict(stats, corpus_works=len(corpus.works),
                      corpus_files=len(corpus.files_scanned)),
        "sources": [{"file": f} for f in corpus.files_scanned]
                   + ([net_note] if net_note else []),
        "evidence_records": log,
        "uncertainty": notes,
        "change_records": [],
    }
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for field in contract:
            if field not in result:
                result[field] = None
        result["output_contract_fields"] = sorted(contract.keys())
    return result


def write_evidence_table(path, visited, edges_out, corpus):
    lines = ["# 引文追踪证据表（自动生成）", "",
             "| 层级 | 方向 | 文献（标题/年份） | 标识 | 经由此节点 | 数据源定位 |", 
             "|-|-|-|-|-|-|"]
    for key, meta in sorted(visited.items(), key=lambda kv: (kv[1]["layer"], kv[0])):
        w = corpus.works[key]
        loc = w.locator
        lines.append("| %d | %s | %s (%s) | %s | %s | %s %s |" % (
            meta["layer"], meta["direction"],
            (w.title or "(no title)")[:60].replace("|", "\\|"),
            w.year or "?",
            w.doi or w.arxiv or w.key,
            meta["via"] or "-",
            loc.get("file", "?"), loc.get("pointer", "")))
    lines += ["", "## 引用边（含方向与数据源）", "",
              "| 从 | 到 | 方向 | 层级 | 数据源定位 |", "|-|-|-|-|-|"]
    for e in edges_out:
        lines.append("| %s | %s | %s | %d | %s %s |" % (
            e["from"], e["to"], e["direction"], e["layer"],
            (e["source"] or {}).get("file", "?"), (e["source"] or {}).get("pointer", "")))
    Path(path).write_text("\n".join(lines), encoding="utf-8")

# ----------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", default=None,
                    help="comma-separated extra corpus roots")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--max-nodes", type=int, default=250)
    ap.add_argument("--max-branch", type=int, default=40)
    ap.add_argument("--year-min", type=int, default=None)
    ap.add_argument("--year-span", type=int, default=45)
    ap.add_argument("--classic-cited-by", type=int, default=200,
                    help="keep older works only if cited-by hint >= this")
    ap.add_argument("--allow-net", action="store_true",
                    help="best-effort live API check; provenance-recorded, off by default")
    args = ap.parse_args()

    started = time.time()
    out_dir = Path(args.out)
    work_dir = Path(args.workdir)
    for d in (out_dir, work_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    log = ["snowball_trace started " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]
    roots = [r for r in DEFAULT_ROOTS if r]
    if args.roots:
        roots += [r.strip() for r in args.roots.split(",") if r.strip()]
    case_dir = str(Path(args.case).resolve().parent)
    if case_dir not in roots:
        roots.insert(0, case_dir)

    try:
        case = load_case(args.case)
    except (OSError, json.JSONDecodeError) as exc:
        log.append("FATAL: cannot read case file %s: %s" % (args.case, exc))
        result = {"case_id": "unknown_case", "skill": "dir-aware-snowball-tracer",
                  "status": "failed", "evidence_records": log,
                  "uncertainty": ["case file unreadable: %s" % exc],
                  "nodes": [], "edges": [], "sources": [], "change_records": []}
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False))
        return 0

    corpus = build_corpus(roots, log)
    back, fwd = build_graph(corpus, log)
    seed, ids, attempts = resolve_seed(corpus, case, log)
    if seed is None:
        visited, edges_out, pruning_log, stop_log = {}, [], [], []
        stats = {"backward_edges": 0, "forward_edges": 0, "stub_nodes": 0}
    else:
        visited, edges_out, pruning_log, stop_log, stats = \
            snowball(corpus, back, fwd, seed, case, args, log)
    net_note = maybe_fetch_crossref(seed, log, args.allow_net)
    result = assemble_result(case, args.case, seed, attempts, visited, edges_out,
                             pruning_log, stop_log, stats, corpus, log, args, net_note)
    log.append("finished in %.1fs: %d nodes, %d edges, status=%s"
               % (time.time() - started, len(visited), len(edges_out), result["status"]))

    try:
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        (out_dir / "trace_graph.json").write_text(json.dumps(
            {"nodes": result["nodes"], "edges": result["edges"]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        write_evidence_table(out_dir / "evidence_table.md", visited, edges_out, corpus)
    except OSError as exc:
        log.append("WARNING: could not write to %s: %s" % (out_dir, exc))
        fallback = work_dir / "result.json"
        fallback.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    (work_dir / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps({"status": result["status"], "nodes": len(visited),
                      "edges": len(edges_out), "seed": bool(seed),
                      "corpus_works": len(corpus.works)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
