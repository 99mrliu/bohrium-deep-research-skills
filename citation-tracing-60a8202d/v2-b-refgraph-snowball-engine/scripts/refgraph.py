#!/usr/bin/env python3
"""refgraph.py -- build a directed citation graph from heterogeneous local corpora.

Offline only. Python 3 standard library only. Location independent (all paths
come from argparse). Deterministic output (stable sorting).

Recursive scan of candidate roots (order: --roots > /input > /app/work > cwd,
keeping only roots that exist). Recognised inputs:

  .json       Crossref (message.items / single message), EuropePMC
              (resultList.result), OpenAlex (results / id+referenced_works),
              generic {"nodes": [...]}, generic {"edges": [...]},
              generic node lists, single generic record
  .jsonl      one record per line (generic node or Crossref-like work)
  .csv/.tsv   edge table (source/target | citing/cited | from/to) or node
              table (doi,title,year,references,citations,...)
  .edgelist   whitespace separated "citing cited" pairs ('#' = comment)
  .bib        BibTeX entries (nodes only, no edges)

Normalisation / identity merge baseline:
  DOI key   : lowercase, strip https://doi.org/ (and doi:) prefix -> exact match
  title key : lowercase, strip punctuation, collapse whitespace  -> exact match
  records with both keys missing stay independent (keyed by file+pointer).

Direction semantics:
  backward edge : source --cites----> target   (reference edge: citing -> cited)
  forward  edge : source --cited_by-> target   (citation edge: cited  -> citing)
Sources that only give reference lists get their forward edges restored from a
corpus-wide reverse index; those edges carry direction_restored: true.

Every normalised record and every edge carries source locators
{file, pointer} (pointer = JSON path or line number) so each claim can be
traced back to the raw corpus. Unresolvable reference targets become honest
stub nodes (locator only, never fabricated metadata).

Output: <workdir>/graph.json  {generated_by, stats, registry, nodes, edges}
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
WS_RE = re.compile(r"\s+")
SUPPORTED_EXT = {".json", ".jsonl", ".csv", ".tsv", ".edgelist", ".bib"}


# ---------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------

def norm_doi(raw):
    """Normalise a DOI: lowercase, strip resolver/doi: prefixes."""
    if raw is None:
        return None
    d = str(raw).strip().strip("<>").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "dx.doi.org/",
                   "doi:", "DOI:"):
        if d.lower().startswith(prefix.lower()):
            d = d[len(prefix):]
    d = d.strip().rstrip(".,;)")
    if not d:
        return None
    return d.lower()


def norm_title(raw):
    """Normalise a title: lowercase, strip punctuation, collapse whitespace."""
    if raw is None:
        return None
    t = PUNCT_RE.sub(" ", str(raw))
    t = WS_RE.sub(" ", t).strip().lower()
    return t or None


def looks_like_doi(value):
    return bool(value) and bool(DOI_RE.match(str(value).strip()))


def make_ref_token(value):
    """Classify a raw reference identifier into a token."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    nd = norm_doi(v)
    if nd and looks_like_doi(nd):
        return {"doi": nd}
    return {"raw": v}


# ---------------------------------------------------------------------------
# record store with identity merge
# ---------------------------------------------------------------------------

class RecordStore:
    """Collects normalised records; merges on DOI key then title key."""

    def __init__(self):
        self.nodes = {}          # id -> record
        self.doi_index = {}      # norm doi -> id
        self.title_index = {}    # norm title -> id
        self.warnings = []

    def _key_for(self, doi, title):
        nd = norm_doi(doi)
        if nd:
            return "doi:" + nd
        nt = norm_title(title)
        if nt:
            return "title:" + nt
        return None

    def add(self, rec):
        """rec: dict with optional doi,title,year,authors,venue,cited_by_count,
        references (list of tokens), citations (list of tokens), locator."""
        locator = rec.get("locator") or {}
        doi = norm_doi(rec.get("doi"))
        title = (rec.get("title") or "").strip() or None
        key = self._key_for(doi, title)
        if key is None:
            # both keys missing -> keep independent, keyed by origin
            key = "misc:%s#%s" % (locator.get("file", "?"), locator.get("pointer", "?"))
        existing_id = None
        if doi and "doi:" + doi in self.doi_index:
            existing_id = self.doi_index["doi:" + doi]
        elif title and norm_title(title) and "title:" + norm_title(title) in self.title_index:
            existing_id = self.title_index["title:" + norm_title(title)]
        elif key in self.nodes:
            existing_id = key

        if existing_id is None:
            node = {
                "id": key,
                "doi": doi,
                "title": title,
                "year": rec.get("year"),
                "authors": rec.get("authors") or [],
                "venue": rec.get("venue"),
                "cited_by_count": rec.get("cited_by_count"),
                "stub": False,
                "references": [],   # list of {token, locator}
                "citations": [],    # list of {token, locator}
                "sources": [],
            }
            self.nodes[key] = node
            if doi:
                self.doi_index["doi:" + doi] = key
            nt = norm_title(title)
            if nt:
                self.title_index.setdefault("title:" + nt, key)
        else:
            node = self.nodes[existing_id]
            # merge: fill missing scalar fields, never overwrite with null
            if not node.get("doi") and doi:
                node["doi"] = doi
                self.doi_index["doi:" + doi] = existing_id
            if not node.get("title") and title:
                node["title"] = title
                nt = norm_title(title)
                if nt:
                    self.title_index.setdefault("title:" + nt, existing_id)
            for field in ("year", "venue", "cited_by_count"):
                if node.get(field) is None and rec.get(field) is not None:
                    node[field] = rec.get(field)
            for a in rec.get("authors") or []:
                if a not in node["authors"]:
                    node["authors"].append(a)

        node["sources"].append(locator)
        for tok in rec.get("references") or []:
            node["references"].append({"token": tok, "locator": locator})
        for tok in rec.get("citations") or []:
            node["citations"].append({"token": tok, "locator": locator})
        return node["id"]

    def add_stub(self, token, locator):
        """Create (or reuse) an honest stub node for an unresolved target."""
        if token.get("doi"):
            key = "doi:" + token["doi"]
            if key in self.nodes:
                node = self.nodes[key]
                node["sources"].append(locator)
                return key
            node = {"id": key, "doi": token["doi"], "title": None,
                    "title_hint": token.get("title_hint"), "year": None,
                    "authors": [], "venue": None, "cited_by_count": None,
                    "stub": True, "references": [], "citations": [],
                    "sources": [locator]}
            self.nodes[key] = node
            self.doi_index[key] = key
            return key
        if token.get("title"):
            nt = norm_title(token["title"])
            key = "title:" + nt
            hit = self.title_index.get(key)
            if hit:
                self.nodes[hit]["sources"].append(locator)
                return hit
            node = {"id": key, "doi": None, "title": token["title"], "year": None,
                    "authors": [], "venue": None, "cited_by_count": None,
                    "stub": True, "references": [], "citations": [],
                    "sources": [locator]}
            self.nodes[key] = node
            self.title_index[key] = key
            return key
        key = "raw:" + str(token.get("raw", "?"))
        if key not in self.nodes:
            self.nodes[key] = {"id": key, "doi": None, "title": str(token.get("raw")),
                               "year": None, "authors": [], "venue": None,
                               "cited_by_count": None, "stub": True,
                               "references": [], "citations": [],
                               "sources": [locator]}
        else:
            self.nodes[key]["sources"].append(locator)
        return key

    def resolve_token(self, token, locator):
        """Resolve a reference/citation token to a node id (stub if absent)."""
        if token.get("doi"):
            hit = self.doi_index.get("doi:" + token["doi"])
            if hit:
                return hit
            return self.add_stub(token, locator)
        if token.get("title"):
            nt = norm_title(token["title"])
            hit = self.title_index.get("title:" + nt) if nt else None
            if hit:
                return hit
            return self.add_stub(token, locator)
        return self.add_stub({"raw": token.get("raw", "?")}, locator)


# ---------------------------------------------------------------------------
# format-specific parsers -> list of raw records
# ---------------------------------------------------------------------------

def _authors_from_crossref(item):
    out = []
    for a in item.get("author") or []:
        fam = a.get("family") or ""
        giv = a.get("given") or ""
        name = (fam + (", " + giv if giv else "")).strip(", ")
        if name:
            out.append(name)
    return out


def _year_from_crossref(item):
    for field in ("issued", "published-print", "published-online", "created"):
        dp = (item.get(field) or {}).get("date-parts")
        if dp and dp[0] and isinstance(dp[0][0], int):
            return dp[0][0]
    return None


def parse_crossref_items(items, fname, base):
    records = []
    for i, item in enumerate(items):
        ptr = "%s/%d" % (base, i)
        title = None
        if item.get("title"):
            title = item["title"][0] if isinstance(item["title"], list) else item["title"]
        venue = None
        if item.get("container-title"):
            ct = item["container-title"]
            venue = ct[0] if isinstance(ct, list) and ct else ct
        refs = []
        for j, r in enumerate(item.get("reference") or []):
            tok = None
            if r.get("DOI"):
                tok = {"doi": norm_doi(r["DOI"])}
                if r.get("article-title"):
                    tok["title_hint"] = r["article-title"]
            elif r.get("article-title"):
                tok = {"title": r["article-title"]}
            elif r.get("key"):
                tok = {"raw": r["key"]}
            if tok:
                tok["_pointer"] = "%s/reference/%d" % (ptr, j)
                refs.append(tok)
        records.append({
            "doi": item.get("DOI"),
            "title": title,
            "year": _year_from_crossref(item),
            "authors": _authors_from_crossref(item),
            "venue": venue,
            "cited_by_count": item.get("is-referenced-by-count"),
            "references": refs,
            "citations": [],
            "locator": {"file": fname, "pointer": ptr},
        })
    return records, "crossref"


def parse_europepmc(obj, fname):
    results = (obj.get("resultList") or {}).get("result") or []
    records = []
    for i, r in enumerate(results):
        ptr = "/resultList/result/%d" % i
        refs = []
        for j, ref in enumerate(((r.get("referenceList") or {}).get("reference")) or []):
            tok = None
            if ref.get("doi"):
                tok = {"doi": norm_doi(ref["doi"])}
            elif ref.get("id"):
                tok = {"raw": str(ref["id"])}
            if tok:
                tok["_pointer"] = "%s/referenceList/reference/%d" % (ptr, j)
                refs.append(tok)
        authors = []
        if r.get("authorString"):
            authors = [a.strip() for a in str(r["authorString"]).split(",") if a.strip()]
        year = None
        try:
            year = int(str(r.get("pubYear")).strip())
        except (TypeError, ValueError):
            year = None
        cbc = r.get("citedByCount")
        try:
            cbc = int(cbc) if cbc is not None else None
        except (TypeError, ValueError):
            cbc = None
        records.append({
            "doi": r.get("doi"),
            "title": r.get("title"),
            "year": year,
            "authors": authors,
            "venue": (r.get("journalInfo") or {}).get("journal", {}).get("title")
                     or r.get("journalTitle"),
            "cited_by_count": cbc,
            "references": refs,
            "citations": [],
            "locator": {"file": fname, "pointer": ptr},
        })
    return records, "europepmc"


def parse_openalex_items(items, fname, base):
    records = []
    for i, item in enumerate(items):
        ptr = "%s/%d" % (base, i)
        refs = []
        for j, wid in enumerate(item.get("referenced_works") or []):
            refs.append({"raw": str(wid), "_pointer": "%s/referenced_works/%d" % (ptr, j)})
        cits = []
        for j, wid in enumerate(item.get("cited_by") or item.get("citing_works") or []):
            cits.append({"raw": str(wid), "_pointer": "%s/cited_by/%d" % (ptr, j)})
        authors = []
        for a in item.get("authorships") or []:
            name = ((a or {}).get("author") or {}).get("display_name")
            if name:
                authors.append(name)
        oid = item.get("id")
        records.append({
            "doi": item.get("doi"),
            "title": item.get("title") or item.get("display_name"),
            "year": item.get("publication_year"),
            "authors": authors,
            "venue": ((item.get("primary_location") or {}).get("source") or {}).get("display_name"),
            "cited_by_count": item.get("cited_by_count"),
            "references": refs,
            "citations": cits,
            "raw_id": oid,
            "locator": {"file": fname, "pointer": ptr},
        })
    return records, "openalex"


def parse_generic_nodes(items, fname, base):
    """Generic 'node carries references/citations lists' JSON."""
    records = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        ptr = "%s/%d" % (base, i)
        refs = []
        for j, v in enumerate(item.get("references") or []):
            tok = make_ref_token(v if not isinstance(v, dict) else
                                 (v.get("doi") or v.get("id") or v.get("target")))
            if tok:
                tok["_pointer"] = "%s/references/%d" % (ptr, j)
                refs.append(tok)
        cits = []
        for j, v in enumerate(item.get("citations") or item.get("cited_by") or []):
            tok = make_ref_token(v if not isinstance(v, dict) else
                                 (v.get("doi") or v.get("id") or v.get("source")))
            if tok:
                tok["_pointer"] = "%s/citations/%d" % (ptr, j)
                cits.append(tok)
        rid = item.get("doi") or item.get("DOI") or item.get("id")
        rec = {
            "doi": item.get("doi") or item.get("DOI"),
            "title": item.get("title"),
            "year": item.get("year") or item.get("pubYear"),
            "authors": item.get("authors") or [],
            "venue": item.get("venue") or item.get("journal"),
            "cited_by_count": item.get("cited_by_count") or item.get("citedByCount"),
            "references": refs,
            "citations": cits,
            "locator": {"file": fname, "pointer": ptr},
        }
        if rid and not rec["doi"] and looks_like_doi(str(rid)):
            rec["doi"] = rid
        elif rid and not rec["doi"]:
            rec["raw_id"] = str(rid)
        records.append(rec)
    return records, "generic-nodes"


def detect_and_parse_json(obj, fname):
    """Return (records, edges, fmt). edges: list of {src_token,tgt_token,locator}."""
    edges = []
    if isinstance(obj, dict):
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("items"), list):
            recs, fmt = parse_crossref_items(msg["items"], fname, "/message/items")
            return recs, edges, fmt
        if isinstance(msg, dict) and msg.get("DOI"):
            recs, fmt = parse_crossref_items([msg], fname, "/message")
            return recs, edges, fmt
        if isinstance(obj.get("resultList"), dict):
            recs, fmt = parse_europepmc(obj, fname)
            return recs, edges, fmt
        if isinstance(obj.get("results"), list):
            recs, fmt = parse_openalex_items(obj["results"], fname, "/results")
            return recs, edges, fmt
        if isinstance(obj.get("nodes"), list):
            recs, fmt = parse_generic_nodes(obj["nodes"], fname, "/nodes")
            for j, e in enumerate(obj.get("edges") or []):
                s = make_ref_token(e.get("source"))
                t = make_ref_token(e.get("target"))
                if s and t:
                    edges.append({"src": s, "tgt": t,
                                  "locator": {"file": fname, "pointer": "/edges/%d" % j}})
            return recs, edges, fmt
        if isinstance(obj.get("edges"), list):
            for j, e in enumerate(obj["edges"]):
                s = make_ref_token(e.get("source"))
                t = make_ref_token(e.get("target"))
                if s and t:
                    edges.append({"src": s, "tgt": t,
                                  "locator": {"file": fname, "pointer": "/edges/%d" % j}})
            return [], edges, "generic-edges"
        if obj.get("DOI") or obj.get("doi") or obj.get("title"):
            recs, fmt = parse_generic_nodes([obj], fname, "")
            return recs, edges, fmt + "-single"
    if isinstance(obj, list):
        recs, fmt = parse_generic_nodes(obj, fname, "")
        return recs, edges, fmt + "-list"
    raise ValueError("unrecognised JSON structure")


def parse_jsonl(text, fname):
    records, edges = [], []
    for ln, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("DOI"):
            recs, _ = parse_crossref_items([obj], fname, "/line/%d" % ln)
            records.extend(recs)
        elif isinstance(obj, dict):
            recs, _ = parse_generic_nodes([obj], fname, "/line/%d" % ln)
            records.extend(recs)
    return records, edges, "jsonl"


def parse_table(text, fname, delim):
    records, edges = [], []
    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    if not reader.fieldnames:
        return records, edges, "table-empty"
    cols = {c.lower().strip(): c for c in reader.fieldnames if c}
    src_col = next((cols[c] for c in ("source", "citing", "from", "src") if c in cols), None)
    tgt_col = next((cols[c] for c in ("target", "cited", "to", "dst") if c in cols), None)
    if src_col and tgt_col:
        for ln, row in enumerate(reader, start=2):
            s = make_ref_token(row.get(src_col))
            t = make_ref_token(row.get(tgt_col))
            if s and t:
                edges.append({"src": s, "tgt": t,
                              "locator": {"file": fname, "pointer": "line %d" % ln}})
        return records, edges, "table-edges"
    doi_col = next((cols[c] for c in ("doi", "id") if c in cols), None)
    if doi_col or "title" in cols:
        for ln, row in enumerate(reader, start=2):
            refs, cits = [], []
            for j, v in enumerate(re.split(r"[;|]", row.get(cols.get("references", ""), "") or "")):
                tok = make_ref_token(v)
                if tok:
                    tok["_pointer"] = "line %d references[%d]" % (ln, j)
                    refs.append(tok)
            for j, v in enumerate(re.split(r"[;|]", row.get(cols.get("citations", ""), "") or "")):
                tok = make_ref_token(v)
                if tok:
                    tok["_pointer"] = "line %d citations[%d]" % (ln, j)
                    cits.append(tok)
            year = row.get(cols.get("year", ""), "") or None
            try:
                year = int(str(year).strip()) if year else None
            except ValueError:
                year = None
            cbc = row.get(cols.get("cited_by_count", ""), "") if "cited_by_count" in cols else None
            try:
                cbc = int(str(cbc).strip()) if cbc else None
            except ValueError:
                cbc = None
            records.append({
                "doi": row.get(doi_col) if doi_col else None,
                "title": row.get(cols.get("title", ""), None) if "title" in cols else None,
                "year": year,
                "authors": [a.strip() for a in re.split(r"[;|]", row.get(cols.get("authors", ""), "") or "") if a.strip()],
                "venue": row.get(cols.get("venue", ""), None) if "venue" in cols else None,
                "cited_by_count": cbc,
                "references": refs,
                "citations": cits,
                "locator": {"file": fname, "pointer": "line %d" % ln},
            })
        return records, edges, "table-nodes"
    raise ValueError("table has neither edge columns nor node columns")


def parse_edgelist(text, fname):
    edges = []
    for ln, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        s, t = make_ref_token(parts[0]), make_ref_token(parts[1])
        if s and t:
            edges.append({"src": s, "tgt": t,
                          "locator": {"file": fname, "pointer": "line %d" % ln}})
    return [], edges, "edgelist"


BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+),(.*?)\n?\}\s*", re.DOTALL)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.*?)[\}\"]\s*,?", re.DOTALL)


def parse_bib(text, fname):
    records = []
    for i, m in enumerate(BIB_ENTRY_RE.finditer(text)):
        body = m.group(2)
        fields = {k.lower(): v.strip() for k, v in BIB_FIELD_RE.findall(body)}
        year = None
        try:
            year = int(fields.get("year", "")) or None
        except ValueError:
            year = None
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        records.append({
            "doi": fields.get("doi"),
            "title": fields.get("title"),
            "year": year,
            "authors": authors,
            "venue": fields.get("journal") or fields.get("booktitle"),
            "cited_by_count": None,
            "references": [],
            "citations": [],
            "locator": {"file": fname, "pointer": "entry %d (%s)" % (i, m.group(1).strip())},
        })
    return records, [], "bibtex"


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------

def iter_files(root):
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            yield p


def main():
    ap = argparse.ArgumentParser(description="Build directed citation graph (offline).")
    ap.add_argument("--roots", action="append", default=None,
                    help="candidate root(s) to scan recursively; repeatable. "
                         "Default: /input, /app/work, cwd (whichever exist).")
    ap.add_argument("--workdir", default="/app/work",
                    help="work directory; graph.json is written here (default /app/work).")
    ap.add_argument("--out", default=None, help="accepted for pipeline symmetry; unused.")
    args = ap.parse_args()

    roots = args.roots or ["/input", "/app/work", str(Path.cwd())]
    roots = [r for r in dict.fromkeys(roots) if Path(r).exists()]
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out_graph = (workdir / "graph.json").resolve()

    store = RecordStore()
    registry = []
    n_edges_raw = 0

    for root in roots:
        for path in iter_files(root):
            if path.resolve() == out_graph:
                continue  # never re-ingest our own product
            fname = str(path)
            entry = {"file": fname, "format": None, "status": "ok",
                     "records": 0, "edges": 0, "error": None}
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                suffix = path.suffix.lower()
                if suffix == ".json":
                    obj = json.loads(text)
                    recs, edges, fmt = detect_and_parse_json(obj, fname)
                elif suffix == ".jsonl":
                    recs, edges, fmt = parse_jsonl(text, fname)
                elif suffix in (".csv", ".tsv"):
                    recs, edges, fmt = parse_table(text, fname, "," if suffix == ".csv" else "\t")
                elif suffix == ".edgelist":
                    recs, edges, fmt = parse_edgelist(text, fname)
                else:
                    recs, edges, fmt = parse_bib(text, fname)
                entry["format"] = fmt
                for rec in recs:
                    if rec.get("raw_id") and not rec.get("doi") and not rec.get("title"):
                        rec["title"] = None
                    store.add(rec)
                    entry["records"] += 1
                # register free-standing edges as stub-node pairs
                for e in edges:
                    s = store.add_stub(e["src"], e["locator"])
                    t = store.add_stub(e["tgt"], e["locator"])
                    store.nodes[s]["references"].append({"token": e["tgt"], "locator": e["locator"]})
                    entry["edges"] += 1
                    n_edges_raw += 1
            except Exception as exc:  # keep scanning; register the failure
                entry["status"] = "failed"
                entry["error"] = "%s: %s" % (type(exc).__name__, exc)
            registry.append(entry)

    # ---- resolve reference/citation tokens to node ids --------------------
    edge_map = {}  # (source, target, direction) -> edge record
    unresolved = 0
    for nid in sorted(store.nodes):
        node = store.nodes[nid]
        resolved_refs, resolved_cits = [], []
        for item in node["references"]:
            tok = dict(item["token"])
            ptr = tok.pop("_pointer", None)
            loc = dict(item["locator"])
            if ptr:
                loc = {"file": loc.get("file"), "pointer": ptr}
            tgt = store.resolve_token(tok, loc)
            resolved_refs.append(tgt)
            key = (nid, tgt, "backward")
            e = edge_map.setdefault(key, {
                "source": nid, "target": tgt, "direction": "backward",
                "semantics": "cites", "direction_restored": False, "sources": []})
            if loc not in e["sources"]:
                e["sources"].append(loc)
            if store.nodes[tgt].get("stub"):
                unresolved += 1
        for item in node["citations"]:
            tok = dict(item["token"])
            ptr = tok.pop("_pointer", None)
            loc = dict(item["locator"])
            if ptr:
                loc = {"file": loc.get("file"), "pointer": ptr}
            src = store.resolve_token(tok, loc)
            resolved_cits.append(src)
            key = (nid, src, "forward")
            e = edge_map.setdefault(key, {
                "source": nid, "target": src, "direction": "forward",
                "semantics": "cited_by", "direction_restored": False, "sources": []})
            if loc not in e["sources"]:
                e["sources"].append(loc)
        node["references"] = sorted(set(resolved_refs))
        node["citations"] = sorted(set(resolved_cits))

    # ---- reverse-index restoration of missing forward edges ---------------
    restored = 0
    for (u, v, d) in list(edge_map):
        if d != "backward":
            continue
        key = (v, u, "forward")
        if key not in edge_map:
            edge_map[key] = {
                "source": v, "target": u, "direction": "forward",
                "semantics": "cited_by", "direction_restored": True,
                "sources": list(edge_map[(u, v, "backward")]["sources"])}
            restored += 1

    edges = sorted(edge_map.values(),
                   key=lambda e: (e["source"], e["target"], e["direction"]))
    nodes = [store.nodes[k] for k in sorted(store.nodes)]
    stats = {
        "roots_scanned": roots,
        "files_ok": sum(1 for r in registry if r["status"] == "ok"),
        "files_failed": sum(1 for r in registry if r["status"] == "failed"),
        "nodes": len(nodes),
        "stub_nodes": sum(1 for n in nodes if n.get("stub")),
        "edges": len(edges),
        "backward_edges": sum(1 for e in edges if e["direction"] == "backward"),
        "forward_edges": sum(1 for e in edges if e["direction"] == "forward"),
        "forward_edges_restored": restored,
        "reference_targets_stubbed": unresolved,
    }
    graph = {"generated_by": "refgraph.py", "stats": stats,
             "registry": registry, "nodes": nodes, "edges": edges}
    out_graph.write_text(json.dumps(graph, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(json.dumps({"ok": True, "graph": str(out_graph), "stats": stats},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
