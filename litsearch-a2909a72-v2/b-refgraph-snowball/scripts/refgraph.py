#!/usr/bin/env python3
"""refgraph-snowball engine: citation-graph snowballing over a LOCAL corpus.

Source-bound literature retrieval without any network: the engine ingests
organizer-provided snapshots (Crossref / EuropePMC / OpenAlex shaped JSON) and
standalone reference files found under --input (plus an optional --corpus dir
of raw responses the agent saved during the run), reconstructs the retained
reference graph, resolves every reference against the local corpus, and then
snowballs from the seed set: backward over outgoing citations, forward over
local records that cite a seed, up to --max-hops. Ranking is a documented
deterministic graph score with a small question-relevance tie-breaker. Every
reference that cannot be resolved locally is written to an explicit ledger -
an unresolved reference is a finding, never a silent drop.

Stdlib only; fully offline.

Usage:
  python3 refgraph.py --case /input/case.json --input /input \
      [--corpus /app/work/corpus] --work /app/work --out /app/output \
      [--max-hops 2] [--top 30]
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

DOI_IN_TEXT_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\],;)}]+", re.I)
TITLE_MATCH_THRESHOLD = 0.92
AMBIGUITY_EPSILON = 0.005

STOPWORDS = set("""
a an the and or of in on for with to from by is are was were be been being
we our this that these those it its as at into about between among over under
per via using use used based study studies analysis approach method methods
results review paper papers work works research find literature recent related
relevant search retrieve identify map trace survey overview around towards
的 了 与 和 在 对 为 及其 相关 文献 检索 查找 寻找 研究 综述 近年 最新 方法 应用
进展 基于 方面 领域 梳理 追溯
""".split())


# ------------------------------------------------------------------ helpers
def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def clean_doi(raw):
    """Lowercase, strip resolver prefixes and trailing punctuation."""
    if not raw:
        return None
    d = str(raw).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.strip().rstrip(".,;)")
    return d or None


def clean_title(raw):
    """Lowercase alphanumeric+CJK title used as fuzzy/dedup key."""
    return re.sub(r"[^a-z0-9一-鿿]+", " ", (raw or "").lower()).strip()


def openalex_id(raw):
    """Extract the W... identifier from an OpenAlex URL or bare id."""
    if not raw:
        return None
    m = re.search(r"(W\d{2,})", str(raw))
    return m.group(1) if m else None


# ----------------------------------------------------------- case handling
def load_case(case_path):
    with open(case_path, encoding="utf-8") as f:
        return json.load(f)


def extract_question(case, task_md):
    for key in ("research_question", "question", "query", "topic", "title"):
        v = case.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for sub in ("text", "question", "title", "description"):
                if isinstance(v.get(sub), str) and v[sub].strip():
                    return v[sub].strip()
    for line in (task_md or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if len(line) >= 12 and not line.lower().startswith(
                ("output", "input", "contract", "deliver")):
            return line
    return ""


def tokenize(text):
    text = (text or "").lower()
    toks = re.findall(r"[a-z][a-z0-9\-]{1,}", text)
    toks = [t for t in toks if len(t) > 2 and t not in STOPWORDS]
    for seg in re.findall(r"[一-鿿]{2,}", text):
        toks.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return sorted(set(toks))


def _seed_tokens_from_value(v, out):
    """Accept str / dict / list seed specifications; append {doi|title}."""
    if isinstance(v, str) and v.strip():
        s = v.strip()
        if DOI_IN_TEXT_RE.search(s) and " " not in s.strip():
            out.append({"doi": clean_doi(s)})
        elif DOI_IN_TEXT_RE.search(s):
            out.append({"doi": clean_doi(DOI_IN_TEXT_RE.search(s).group(0))})
        else:
            out.append({"title": s})
    elif isinstance(v, dict):
        d = clean_doi(v.get("doi") or v.get("DOI"))
        if d:
            out.append({"doi": d})
        elif isinstance(v.get("title"), str) and v["title"].strip():
            out.append({"title": v["title"].strip()})
    elif isinstance(v, list):
        for item in v:
            _seed_tokens_from_value(item, out)


def find_seed_specs(case, input_dir):
    """Return (seed_specs, origin). origin in explicit-case|explicit-file|derived|none."""
    specs = []
    for key in ("seed_dois", "seeds", "seed_papers", "seed_records"):
        if case.get(key):
            _seed_tokens_from_value(case[key], specs)
            if specs:
                return specs, "explicit-case"
    for name in ("seeds.json", "seed_papers.json", "seeds.txt"):
        p = os.path.join(input_dir, name)
        if not os.path.isfile(p):
            continue
        text = open(p, encoding="utf-8", errors="replace").read()
        if name.endswith(".json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                if isinstance(payload, dict):
                    payload = payload.get("seeds") or payload.get("seed_dois") or []
                _seed_tokens_from_value(payload, specs)
        else:
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    _seed_tokens_from_value(line, specs)
        if specs:
            return specs, "explicit-file:%s" % name
    return [], "none"


# ------------------------------------------------------- snapshot ingestion
def snapshot_shape(payload):
    """Recognize organizer snapshot shapes. Returns (source_type, raw records)."""
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
    if isinstance(msg, dict) and msg.get("DOI"):
        return "crossref-single", [msg]
    return None, []


def rec_title(raw):
    t = raw.get("title") or raw.get("display_name")
    if isinstance(t, list):
        t = t[0] if t else None
    return (t or "").strip() or None


def rec_doi(raw, source):
    if source == "europepmc":
        return clean_doi(raw.get("doi"))
    return clean_doi(raw.get("DOI") or raw.get("doi"))


def rec_year(raw, source):
    try:
        if source.startswith("crossref"):
            parts = (raw.get("issued") or {}).get("date-parts") or []
            return int(parts[0][0]) if parts and parts[0] else None
        if source == "europepmc":
            return int(raw["pubYear"]) if raw.get("pubYear") else None
        if source == "openalex":
            return (int(raw["publication_year"])
                    if raw.get("publication_year") else None)
    except (TypeError, ValueError, IndexError):
        return None
    return None


def rec_venue(raw, source):
    if source.startswith("crossref"):
        c = raw.get("container-title")
        if isinstance(c, list):
            c = c[0] if c else None
        return c
    if source == "europepmc":
        return raw.get("journalTitle")
    if source == "openalex":
        return (((raw.get("primary_location") or {}).get("source") or {})
                .get("display_name"))
    return None


def rec_authors(raw, source):
    out = []
    try:
        if source.startswith("crossref"):
            for a in raw.get("author") or []:
                name = " ".join(x for x in [a.get("given"), a.get("family")] if x)
                if name:
                    out.append(name)
        elif source == "europepmc":
            out = [x.strip() for x in (raw.get("authorString") or "").split(",")
                   if x.strip()]
        elif source == "openalex":
            for a in raw.get("authorships") or []:
                nm = (a.get("author") or {}).get("display_name")
                if nm:
                    out.append(nm)
    except AttributeError:
        pass
    return out


def rec_abstract(raw):
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


def rec_references(raw, source):
    """Normalized reference entries: {doi?, title?, openalex_id?, raw_excerpt}."""
    refs = []
    if source.startswith("crossref"):
        for ent in raw.get("reference") or []:
            if not isinstance(ent, dict):
                ent = {"unstructured": str(ent)}
            title = ent.get("article-title") or ent.get("series-title") or None
            unstruct = ent.get("unstructured") or ""
            doi = clean_doi(ent.get("DOI") or ent.get("doi"))
            if not doi and unstruct:
                m = DOI_IN_TEXT_RE.search(unstruct)
                if m:
                    doi = clean_doi(m.group(0))
            excerpt = (doi or title or unstruct or "")[:160]
            refs.append({"doi": doi, "title": title, "openalex_id": None,
                         "raw_excerpt": excerpt})
    elif source == "openalex":
        for w in raw.get("referenced_works") or []:
            oid = openalex_id(w)
            refs.append({"doi": None, "title": None, "openalex_id": oid,
                         "raw_excerpt": str(w)[:160]})
    # europepmc search-result records carry no reference list; documented limit.
    return refs


# -------------------------------------------- standalone reference files
def parse_standalone_refs(path):
    """Parse .bib/.ris/.txt/.md reference exports into reference entries."""
    text = open(path, encoding="utf-8", errors="replace").read()
    low = path.lower()
    refs = []
    if low.endswith(".bib"):
        for chunk in re.split(r"\n\s*(?=@)", text):
            m = DOI_IN_TEXT_RE.search(chunk)
            tm = re.search(r"title\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", chunk,
                           re.S | re.I)
            refs.append({"doi": clean_doi(m.group(0)) if m else None,
                         "title": tm.group(1).strip() if tm else None,
                         "openalex_id": None,
                         "raw_excerpt": chunk.strip().splitlines()[0][:160]
                         if chunk.strip() else ""})
    elif low.endswith(".ris"):
        for chunk in re.split(r"(?m)^ER\s*-.*$", text):
            m = re.search(r"(?m)^DO\s*-\s*(.+)$", chunk)
            tm = re.search(r"(?m)^TI\s*-\s*(.+)$", chunk)
            if m or tm:
                refs.append({"doi": clean_doi(m.group(1)) if m else None,
                             "title": tm.group(1).strip() if tm else None,
                             "openalex_id": None,
                             "raw_excerpt": (tm.group(1).strip()
                                             if tm else m.group(1).strip())[:160]})
    else:  # one reference per line (.txt / .md exports)
        for line in text.splitlines():
            line = line.strip().lstrip("-*0123456789.[] ").strip()
            if len(line) < 8 or line.startswith("#"):
                continue
            m = DOI_IN_TEXT_RE.search(line)
            refs.append({"doi": clean_doi(m.group(0)) if m else None,
                         "title": None if m else line[:200],
                         "openalex_id": None,
                         "raw_excerpt": line[:160]})
    return [r for r in refs if r["doi"] or r["title"]]


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--corpus", default=None,
                    help="extra dir of raw responses saved by the agent")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-hops", type=int, default=2)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    ev_dir = os.path.join(args.out, "evidence")
    os.makedirs(ev_dir, exist_ok=True)

    case = load_case(args.case)
    task_path = os.path.join(args.input, "task.md")
    task_md = (open(task_path, encoding="utf-8", errors="replace").read()
               if os.path.isfile(task_path) else "")
    question = extract_question(case, task_md)
    terms = tokenize(question)

    roots = [args.input]
    if args.corpus and os.path.isdir(args.corpus):
        roots.append(args.corpus)

    seed_specs, seed_origin = find_seed_specs(case, args.input)

    # ---- walk, hash, classify every file
    inventory, records, standalone = [], [], []
    SKIP_BASENAMES = {"case.json", "result.json", "task.md", "seeds.json",
                      "seed_papers.json", "seeds.txt", "readme.md"}
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                path = os.path.join(dirpath, fn)
                if not os.path.isfile(path) or os.path.islink(path):
                    continue
                rel = os.path.relpath(path, root)
                low = fn.lower()
                digest = sha12(path)
                entry = {"file": rel, "root": root, "sha256_12": digest,
                         "bytes": os.path.getsize(path)}
                inventory.append(entry)
                if fn in SKIP_BASENAMES:
                    entry["role"] = "case-material"
                    continue
                if low.endswith(".json"):
                    try:
                        payload = json.loads(open(path, encoding="utf-8",
                                                  errors="replace").read())
                    except (json.JSONDecodeError, OSError) as exc:
                        entry["role"] = "unparsed"
                        entry["detail"] = str(exc)[:200]
                        continue
                    source, raws = snapshot_shape(payload)
                    if source is None:
                        entry["role"] = "unparsed"
                        entry["detail"] = "no recognized snapshot shape"
                        continue
                    entry["role"] = "snapshot"
                    entry["source_type"] = source
                    entry["records"] = len(raws)
                    for i, r in enumerate(raws):
                        records.append({
                            "title": rec_title(r),
                            "authors": rec_authors(r, source),
                            "year": rec_year(r, source),
                            "venue": rec_venue(r, source),
                            "doi": rec_doi(r, source),
                            "abstract": rec_abstract(r),
                            "openalex_id": (openalex_id(r.get("id"))
                                            if source == "openalex" else None),
                            "references": rec_references(r, source),
                            "provenance": {"file": rel, "root": root,
                                           "json_index": i,
                                           "source_type": source,
                                           "sha256_12": digest},
                        })
                elif low.endswith((".bib", ".ris", ".txt", ".md")):
                    refs = parse_standalone_refs(path)
                    entry["role"] = "reference-file"
                    entry["references"] = len(refs)
                    if refs:
                        standalone.append({"file": rel, "root": root,
                                           "sha256_12": digest, "refs": refs})
                else:
                    entry["role"] = "other"

    n_snapshots = sum(1 for e in inventory if e.get("role") == "snapshot")

    # ---- dedup by DOI else normalized title; merge duplicate reference lists
    by_key = {}
    for rec in records:
        if rec["doi"]:
            key = "doi:" + rec["doi"]
        elif rec["title"]:
            key = "title:" + clean_title(rec["title"])
        else:
            key = "anon:%s#%d" % (rec["provenance"]["file"],
                                  rec["provenance"]["json_index"])
        if key in by_key:
            kept = by_key[key]
            kept.setdefault("also_in", []).append(rec["provenance"])
            seen_ex = {r["raw_excerpt"] for r in kept["references"]}
            for ref in rec["references"]:
                if ref["raw_excerpt"] not in seen_ex:
                    kept["references"].append(ref)
        else:
            by_key[key] = rec
    corpus = list(by_key.values())

    # ---- resolution indexes
    idx_doi = {r["doi"]: k for k, r in by_key.items() if r.get("doi")}
    idx_oa = {r["openalex_id"]: k for k, r in by_key.items()
              if r.get("openalex_id")}
    title_keys = [(clean_title(r["title"]), k)
                  for k, r in by_key.items() if r.get("title")]

    def resolve(ref):
        """-> (key_or_None, via, reason_or_None)"""
        if ref.get("doi") and ref["doi"] in idx_doi:
            return idx_doi[ref["doi"]], "doi", None
        if ref.get("openalex_id") and ref["openalex_id"] in idx_oa:
            return idx_oa[ref["openalex_id"]], "openalex-id", None
        if ref.get("title") and title_keys:
            want = clean_title(ref["title"])
            scored = []
            for norm, k in title_keys:
                ratio = difflib.SequenceMatcher(None, want, norm).ratio()
                if ratio >= TITLE_MATCH_THRESHOLD:
                    scored.append((ratio, k))
            if scored:
                scored.sort(key=lambda x: (-x[0], x[1]))
                best_ratio = scored[0][0]
                tied = {k for ratio, k in scored
                        if best_ratio - ratio <= AMBIGUITY_EPSILON}
                if len(tied) == 1:
                    return scored[0][1], "title-fuzzy", None
                return None, None, "ambiguous"
        if ref.get("doi"):
            return None, None, "doi-not-in-corpus"
        if ref.get("openalex_id"):
            return None, None, "openalex-id-not-in-corpus"
        if ref.get("title"):
            return None, None, "title-not-in-corpus"
        return None, None, "no-identifier"

    # ---- build the local citation graph + unresolved ledger
    edges, ledger, adj_out, adj_in = [], [], {}, {}
    edge_seen = set()

    def add_edge(src_key, ref):
        tgt, via, reason = resolve(ref)
        if tgt is None:
            ledger.append({"source": src_key, "reason": reason,
                           "doi": ref.get("doi"), "title": ref.get("title"),
                           "openalex_id": ref.get("openalex_id"),
                           "raw_excerpt": ref.get("raw_excerpt")})
            return
        if (src_key, tgt) in edge_seen or src_key == tgt:
            return
        edge_seen.add((src_key, tgt))
        edges.append({"from": src_key, "to": tgt, "via": via})
        adj_out.setdefault(src_key, set()).add(tgt)
        adj_in.setdefault(tgt, set()).add(src_key)

    for k, r in by_key.items():
        for ref in r["references"]:
            add_edge(k, ref)

    # Standalone reference files: treated as the reference list of the seed
    # set (documented in methodology). Edges hang off a file pseudo-node.
    for sf in standalone:
        pseudo = "file:" + sf["file"]
        for ref in sf["refs"]:
            tgt, via, reason = resolve(ref)
            if tgt is None:
                ledger.append({"source": pseudo, "reason": reason,
                               "doi": ref.get("doi"), "title": ref.get("title"),
                               "openalex_id": ref.get("openalex_id"),
                               "raw_excerpt": ref.get("raw_excerpt")})
                continue
            if (pseudo, tgt) not in edge_seen:
                edge_seen.add((pseudo, tgt))
                edges.append({"from": pseudo, "to": tgt,
                              "via": "standalone-file"})
                adj_in.setdefault(tgt, set()).add(pseudo)

    reason_counts = {}
    for item in ledger:
        reason_counts[item["reason"]] = reason_counts.get(item["reason"], 0) + 1

    # ---- seed matching
    def match_seed(spec):
        if spec.get("doi") and spec["doi"] in idx_doi:
            return idx_doi[spec["doi"]]
        if spec.get("title"):
            want = clean_title(spec["title"])
            best, best_key = 0.0, None
            for norm, k in title_keys:
                ratio = difflib.SequenceMatcher(None, want, norm).ratio()
                if ratio >= TITLE_MATCH_THRESHOLD and ratio > best:
                    best, best_key = ratio, k
            return best_key
        return None

    seed_keys, unmatched_seeds = [], []
    for spec in seed_specs:
        k = match_seed(spec)
        if k and k not in seed_keys:
            seed_keys.append(k)
        elif not k:
            unmatched_seeds.append(spec)

    # Derived seeds: top title/abstract-matched records, and we say so.
    if not seed_keys and not seed_specs and corpus:
        scored = []
        for r in corpus:
            tl = (r.get("title") or "").lower()
            ab = (r.get("abstract") or "").lower()
            s = sum(2.0 for t in terms if t in tl) + \
                sum(0.5 for t in terms if t in ab)
            if s > 0:
                scored.append((s, -(r.get("year") or 0), r.get("title") or "",
                               "doi:" + r["doi"] if r["doi"]
                               else "title:" + clean_title(r["title"])))
        scored.sort()
        seed_keys = [k for _s, _y, _t, k in scored[-3:][::-1]]
        if seed_keys:
            seed_origin = "derived-title-match"

    # ---- snowball expansion (backward = outgoing refs, forward = citers)
    hop_back, hop_fwd = {}, {}

    def bfs(starts, adjacency):
        dist = {}
        frontier = [s for s in starts]
        for s in starts:
            dist[s] = 0
        hop = 0
        while frontier and hop < args.max_hops:
            hop += 1
            nxt = []
            for node in frontier:
                for nb in sorted(adjacency.get(node, ())):
                    if nb.startswith("file:"):
                        continue
                    if nb not in dist:
                        dist[nb] = hop
                        nxt.append(nb)
            frontier = nxt
        return dist

    dist_back = bfs(seed_keys, adj_out)
    dist_fwd = bfs(seed_keys, adj_in)
    for k in seed_keys:
        dist_back.pop(k, None)
        dist_fwd.pop(k, None)
    hop_back = dist_back
    hop_fwd = dist_fwd

    # ---- deterministic graph scoring (see references/methodology.md)
    def relevance(rec):
        tl = (rec.get("title") or "").lower()
        ab = (rec.get("abstract") or "").lower()
        th = [t for t in terms if t in tl]
        ah = [t for t in terms if t in ab]
        return 2.0 * len(th) + 0.5 * len(ah), th, ah

    candidates = []
    pool = set(seed_keys) | set(hop_back) | set(hop_fwd)
    for k in pool:
        rec = by_key[k]
        connected_seeds = {s for s in seed_keys
                           if s in adj_out.get(k, ()) or s in adj_in.get(k, ())}
        rel_score, title_hits, abs_hits = relevance(rec)
        bd = {
            "seed_base": 10.0 if k in seed_keys else 0.0,
            "backward_reach": (round(4.0 / hop_back[k], 3)
                               if k in hop_back else 0.0),
            "forward_reach": (round(4.0 / hop_fwd[k], 3)
                              if k in hop_fwd else 0.0),
            "cocitation_bonus": (0.0 if k in seed_keys else
                                 2.0 * max(0, len(connected_seeds) - 1)),
            "relevance_bonus": round(rel_score, 3),
        }
        bd["total"] = round(sum(bd.values()), 3)
        hops = [h for h in (hop_back.get(k), hop_fwd.get(k)) if h]
        candidates.append({
            "key": k, "doi": rec.get("doi"), "title": rec.get("title"),
            "authors": rec.get("authors"), "year": rec.get("year"),
            "venue": rec.get("venue"),
            "is_seed": k in seed_keys,
            "hop": 0 if k in seed_keys else (min(hops) if hops else None),
            "direction": ("seed" if k in seed_keys else
                          "both" if k in hop_back and k in hop_fwd else
                          "backward" if k in hop_back else "forward"),
            "seeds_connected": sorted(connected_seeds),
            "matched_terms_title": title_hits,
            "matched_terms_abstract": abs_hits,
            "score_breakdown": bd,
            "provenance": rec["provenance"],
        })
    candidates.sort(key=lambda c: (-c["score_breakdown"]["total"],
                                   c["hop"] if c["hop"] is not None else 99,
                                   -(c["year"] or 0), c["title"] or ""))
    candidates = candidates[:args.top]

    seeds_no_refs = [k for k in seed_keys
                     if not [t for t in adj_out.get(k, ())] and
                     not [t for t in adj_in.get(k, ())
                          if not t.startswith("file:")]]
    n_nodes = len(corpus)
    density = (len([e for e in edges if not e["from"].startswith("file:")])
               / (n_nodes * (n_nodes - 1)) if n_nodes > 1 else 0.0)

    status = "success"
    if not seed_keys:
        status = "partial"
    elif not any(e["from"] in seed_keys or e["to"] in seed_keys
                 for e in edges):
        status = "partial"

    digest = {
        "ENGINE_STATUS": status,
        "question": question,
        "query_terms": terms,
        "snapshots_seen": n_snapshots,
        "reference_files_seen": len(standalone),
        "records_loaded": len(records),
        "unique_records": n_nodes,
        "seed_origin": seed_origin,
        "seeds_matched": [{"key": k, "doi": by_key[k].get("doi"),
                           "title": by_key[k].get("title")}
                          for k in seed_keys],
        "seeds_unmatched": unmatched_seeds,
        "references_extracted": sum(len(r["references"]) for r in corpus)
        + sum(len(sf["refs"]) for sf in standalone),
        "references_resolved": len(edges),
        "references_unresolved": len(ledger),
        "unresolved_by_reason": reason_counts,
        "graph_edges": len(edges),
        "graph_density": round(density, 4),
        "candidates": len(candidates),
        "seeds_without_resolvable_refs": seeds_no_refs,
        "max_hops": args.max_hops,
    }

    # ---- outputs
    nodes = []
    for k, r in sorted(by_key.items()):
        nodes.append({"key": k, "doi": r.get("doi"), "title": r.get("title"),
                      "year": r.get("year"), "venue": r.get("venue"),
                      "is_seed": k in seed_keys,
                      "hop_backward": hop_back.get(k),
                      "hop_forward": hop_fwd.get(k),
                      "provenance": r["provenance"]})
    for sf in standalone:
        nodes.append({"key": "file:" + sf["file"], "kind": "standalone_ref_file",
                      "provenance": {"file": sf["file"], "root": sf["root"],
                                     "sha256_12": sf["sha256_12"]}})
    with open(os.path.join(args.out, "graph.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_iso(), "question": question,
                   "seed_origin": seed_origin, "nodes": nodes, "edges": edges},
                  f, ensure_ascii=False, indent=1)

    with open(os.path.join(args.out, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump({"question": question, "seed_origin": seed_origin,
                   "ranked": candidates}, f, ensure_ascii=False, indent=1)

    cl = ["# Ranked candidates (refgraph-snowball)", "",
          "Question: %s" % (question or "(none extracted)"), "",
          "Seeds (%s): %s" % (seed_origin, ", ".join(
              by_key[k].get("doi") or by_key[k].get("title") or k
              for k in seed_keys) or "none"), "",
          "| # | total | hop | direction | year | title | DOI | source |",
          "|-|-|-|-|-|-|-|-|"]
    for i, c in enumerate(candidates, 1):
        p = c["provenance"]
        cl.append("| %d | %.2f | %s | %s | %s | %s | %s | %s#%s |" % (
            i, c["score_breakdown"]["total"],
            c["hop"] if c["hop"] is not None else "—",
            c["direction"], c.get("year") or "—",
            (c.get("title") or "—")[:80], c.get("doi") or "—",
            p["file"], p.get("json_index", "—")))
    if not candidates:
        cl.append("| — | — | — | — | — | no seed reachable in the local graph | | |")
    cl += ["", "## Score breakdowns (per candidate)", ""]
    for i, c in enumerate(candidates, 1):
        b = c["score_breakdown"]
        cl.append("- **#%d %s** — seed_base=%.1f backward=%.2f forward=%.2f "
                  "cocitation=%.1f relevance=%.2f → **total=%.2f**" % (
                      i, (c.get("title") or c["key"])[:60], b["seed_base"],
                      b["backward_reach"], b["forward_reach"],
                      b["cocitation_bonus"], b["relevance_bonus"], b["total"]))
    open(os.path.join(args.out, "candidates.md"), "w",
         encoding="utf-8").write("\n".join(cl) + "\n")

    ul = ["# Unresolved reference ledger (refgraph-snowball)", "",
          "Every reference extracted from local records or standalone reference "
          "files that could NOT be resolved to a local record. An unresolved "
          "reference is a coverage finding, not a failure.", "",
          "## Counts by reason", ""]
    for reason, n in sorted(reason_counts.items()):
        ul.append("- `%s`: %d" % (reason, n))
    if not reason_counts:
        ul.append("- none — every extracted reference resolved locally")
    ul += ["", "## Ledger", "",
           "| source | reason | doi | title | excerpt |", "|-|-|-|-|-|"]
    for item in ledger:
        ul.append("| %s | %s | %s | %s | %s |" % (
            item["source"], item["reason"], item.get("doi") or "—",
            (item.get("title") or "—")[:60],
            (item.get("raw_excerpt") or "—")[:80]))
    if not ledger:
        ul.append("| — | — | — | — | — |")
    open(os.path.join(args.out, "unresolved_references.md"), "w",
         encoding="utf-8").write("\n".join(ul) + "\n")

    gaps = []
    if not seed_keys:
        gaps.append("No seeds could be matched or derived — no snowball was "
                    "possible; deliver partial.")
    if unmatched_seeds:
        gaps.append("%d seed specification(s) matched no local record: %s"
                    % (len(unmatched_seeds), json.dumps(unmatched_seeds,
                                                        ensure_ascii=False)))
    for k in seeds_no_refs:
        gaps.append("Seed `%s` (%s) has zero locally resolvable references "
                    "and zero local citers." % (k, by_key[k].get("title")))
    if density == 0.0 and n_nodes > 1:
        gaps.append("Graph density is 0: no resolved citation edges at all — "
                    "the snapshots carry no usable reference lists.")
    if reason_counts:
        gaps.append("%d reference(s) unresolved (%s) — genuine coverage gaps "
                    "of the local corpus."
                    % (len(ledger), ", ".join("%s=%d" % kv
                                              for kv in sorted(
                                                      reason_counts.items()))))

    rl = ["# Search report (refgraph-snowball)", "",
          "```json", json.dumps(digest, ensure_ascii=False, indent=1), "```",
          "", "## Interpretation", "",
          "- Recall comes from GRAPH TRAVERSAL over the retained reference "
          "lists, not from query planning: backward = references of seeds that "
          "resolve locally; forward = local records whose reference lists cite "
          "a seed.",
          "- `score_breakdown` shows every component of each candidate's "
          "score; the formula is in references/methodology.md.",
          "- Unresolved references are ledgered in unresolved_references.md "
          "with reason codes — they are findings about corpus coverage.",
          "- Records not reachable within %d hop(s) remain in graph.json but "
          "are excluded from candidates." % args.max_hops,
          "", "## Honest gaps", ""]
    rl += ["- " + g for g in gaps] or ["- none identified"]
    open(os.path.join(args.out, "search_report.md"), "w",
         encoding="utf-8").write("\n".join(rl) + "\n")

    with open(os.path.join(ev_dir, "evidence_index.json"), "w",
              encoding="utf-8") as f:
        json.dump({"generated_at": now_iso(), "files": inventory}, f,
                  ensure_ascii=False, indent=1)

    print(json.dumps(digest, ensure_ascii=False))
    return 0 if records else 2


if __name__ == "__main__":
    sys.exit(main())
