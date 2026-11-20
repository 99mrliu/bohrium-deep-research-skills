#!/usr/bin/env python3
"""Co-citation & bibliographic-coupling discovery of parallel works.

Stdlib only (Python 3.8+). Finds works that do NOT directly cite (or get cited by)
the seed, yet belong to the same methodological lineage, with per-candidate
association evidence that a reviewer can re-check.

Signals (all computed from the local evidence corpus, each with source locators):
  S1 co-citation        -- works cited TOGETHER WITH the seed by the same citing work
  S2 bibliographic coupling -- works whose reference lists OVERLAP the seed's references
  S3 author overlap     -- shared author surnames with the seed (secondary signal)
  S4 venue/task token   -- shared venue or salient title tokens (tie-breaker only)

Anti-noise design:
  * direct neighbors of the seed (its references and its citers) are EXCLUDED from
    candidates and reported separately -- the goal is parallel works;
  * raw counts are normalized (co-citation: Ochiai/cosine; coupling: Jaccard on
    reference sets) so that highly-cited hub papers do not dominate by size alone;
  * every candidate must carry at least one structural signal (S1 or S2); S3/S4
    alone never admit a candidate;
  * every contributing citing work / shared reference is listed with its locator.

Usage:
    python3 codiscover.py --case /input/case.json --out /app/output \
        [--workdir /app/work] [--top 40] [--min-support 1]

Exit code is always 0; status lives in result.json.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import time
from pathlib import Path

DEFAULT_ROOTS = ["/input", "./environment", "/app/work", "."]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "output"}
SKIP_FILES = {"result.json", "trace_graph.json", "run_log.json", "verify_report.json",
              "case.json"}
MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_FILES = 400
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "be", "been", "via", "using",
    "based", "study", "analysis", "review", "towards", "toward", "new", "its",
}

# ---------------------------------------------------------------- id / title utils


def norm_doi(v):
    if not v:
        return None
    v = str(v).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if v.startswith(p):
            v = v[len(p):]
    return v or None


def norm_arxiv(v):
    if not v:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", str(v).lower())
    if m:
        return m.group(1)
    m = re.search(r"([a-z\-]+/\d{7})(v\d+)?", str(v).lower())
    return m.group(1) if m else None


def norm_title(v):
    if not v:
        return ""
    v = re.sub(r"<[^>]+>", " ", str(v))
    v = re.sub(r"[^a-z0-9]+", " ", v.lower())
    return " ".join(v.split())


def salient_tokens(v):
    return {t for t in norm_title(v).split() if len(t) > 2 and t not in STOPWORDS}


def surnames(authors):
    out = set()
    for a in authors or []:
        if isinstance(a, dict):
            name = a.get("family") or a.get("name") or ""
        else:
            name = str(a)
        parts = name.split(",")[0].strip().split()
        if parts:
            out.add(parts[-1].lower())
    return out

# ---------------------------------------------------------------- records


def pointer_key(p):
    if p.get("doi"):
        return "doi:" + p["doi"]
    if p.get("arxiv"):
        return "arxiv:" + p["arxiv"]
    t = norm_title(p.get("title"))
    return "t:" + t[:90] if t else None


def parse_pointer(obj, locator):
    if isinstance(obj, str):
        s = obj.strip()
        d, a = norm_doi(s), norm_arxiv(s)
        if d:
            return {"doi": d, "locator": locator}
        if a:
            return {"arxiv": a, "locator": locator}
        return {"title": s, "locator": locator} if s else None
    if not isinstance(obj, dict):
        return None
    p = {"locator": locator}
    d = norm_doi(obj.get("DOI") or obj.get("doi"))
    a = norm_arxiv(obj.get("arxiv") or
                   (obj.get("externalIds") or {}).get("ArXiv")
                   if isinstance(obj.get("externalIds"), dict) else obj.get("arxiv"))
    if d:
        p["doi"] = d
    if a:
        p["arxiv"] = a
    t = obj.get("article-title") or obj.get("title") or obj.get("display_name") \
        or obj.get("unstructured")
    if isinstance(t, list):
        t = t[0] if t else None
    if t:
        p["title"] = str(t)
    return p if pointer_key(p) else None


def record_to_work(obj, locator):
    if not isinstance(obj, dict):
        return None
    title = obj.get("title") or obj.get("display_name")
    if isinstance(title, list):
        title = title[0] if title else None
    doi = norm_doi(obj.get("DOI") or obj.get("doi"))
    ids = obj.get("externalIds") if isinstance(obj.get("externalIds"), dict) else {}
    ax = norm_arxiv(obj.get("arxiv") or ids.get("ArXiv"))
    if not (title or doi or ax):
        return None
    year = None
    for k in ("year", "pubYear", "publication_year"):
        if obj.get(k):
            try:
                year = int(str(obj[k])[:4])
                break
            except ValueError:
                pass
    if year is None:
        for k in ("issued", "published", "created", "publication_date"):
            v = obj.get(k)
            if isinstance(v, dict) and "date-parts" in v:
                try:
                    year = int(v["date-parts"][0][0])
                    break
                except (TypeError, IndexError, ValueError):
                    pass
            elif isinstance(v, str):
                m = re.match(r"(\d{4})", v)
                if m:
                    year = int(m.group(1))
                    break
    authors = []
    raw_authors = obj.get("author") or obj.get("authors") or obj.get("authorString") \
        or obj.get("authorships")
    if isinstance(raw_authors, str):
        authors = [{"name": p.strip()} for p in raw_authors.split(",") if p.strip()][:25]
    elif isinstance(raw_authors, list):
        for a in raw_authors[:25]:
            if isinstance(a, dict):
                if "family" in a or "given" in a:
                    authors.append({"given": a.get("given"), "family": a.get("family")})
                elif "name" in a:
                    authors.append({"name": a["name"]})
                elif isinstance(a.get("author"), dict):
                    authors.append({"name": a["author"].get("display_name")})
            elif isinstance(a, str):
                authors.append({"name": a})
    venue = obj.get("container-title") or obj.get("venue") or obj.get("journalTitle")
    if isinstance(venue, list):
        venue = venue[0] if venue else None
    if isinstance(venue, dict):
        venue = venue.get("display_name")
    refs, cites = [], []
    for i, r in enumerate(obj.get("reference") or obj.get("references") or []):
        p = parse_pointer(r, dict(locator, pointer="%s/refs/%d" % (locator["pointer"], i)))
        if p:
            refs.append(p)
    rl = obj.get("referenceList")
    if isinstance(rl, dict):
        for i, r in enumerate(rl.get("reference") or []):
            p = parse_pointer(r, dict(locator, pointer="%s/referenceList/%d" % (locator["pointer"], i)))
            if p:
                refs.append(p)
    for i, c in enumerate(obj.get("citations") or []):
        p = parse_pointer(c, dict(locator, pointer="%s/citations/%d" % (locator["pointer"], i)))
        if p:
            cites.append(p)
    cl = obj.get("citationList")
    if isinstance(cl, dict):
        for i, c in enumerate(cl.get("citation") or []):
            p = parse_pointer(c, dict(locator, pointer="%s/citationList/%d" % (locator["pointer"], i)))
            if p:
                cites.append(p)
    cited_by = None
    for k in ("is-referenced-by-count", "citedByCount", "citationCount", "cited_by_count"):
        if isinstance(obj.get(k), int):
            cited_by = obj[k]
            break
    return {
        "doi": doi, "arxiv": ax, "title": str(title) if title else "",
        "year": year, "authors": authors, "venue": venue,
        "refs": refs, "cites": cites, "cited_by": cited_by,
        "locator": locator,
    }


def walk_json(obj, path, file_path, sink, depth=0):
    if depth > 12:
        return
    if isinstance(obj, dict):
        w = record_to_work(obj, {"file": file_path, "pointer": path or "$"})
        if w is not None and (w.get("title") or w.get("doi")):
            sink.append(w)
            return
        for k, v in obj.items():
            if k in ("reference", "references", "citations", "referenceList",
                     "citationList", "author", "authors", "authorships"):
                continue
            walk_json(v, "%s/%s" % (path, k), file_path, sink, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20000]):
            walk_json(v, "%s/%d" % (path, i), file_path, sink, depth + 1)


def discover_files(roots):
    seen, out = set(), []
    exts = (".json", ".jsonl", ".ndjson", ".csv", ".tsv")
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
                        for c in sorted(node.iterdir()):
                            stack.append((c, depth + 1))
                elif node.suffix.lower() in exts and node.name not in SKIP_FILES:
                    rp = str(node.resolve())
                    if rp in seen or node.stat().st_size > MAX_FILE_BYTES:
                        continue
                    seen.add(rp)
                    out.append(node)
            except (OSError, PermissionError):
                continue
    return out


def load_corpus(roots, log):
    raw, files, notes = [], [], []
    for path in discover_files(roots):
        fp = str(path)
        try:
            if path.suffix.lower() == ".json":
                walk_json(json.loads(path.read_text(encoding="utf-8", errors="replace")),
                          "$", fp, raw)
            elif path.suffix.lower() in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if line:
                            try:
                                walk_json(json.loads(line), "$/%d" % i, fp, raw)
                            except json.JSONDecodeError:
                                notes.append("bad JSONL %s:%d" % (fp, i + 1))
            else:
                with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                    sample = fh.read(4096)
                    fh.seek(0)
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if sample.strip() else csv.excel
                    for i, row in enumerate(csv.DictReader(fh, dialect=dialect)):
                        w = record_to_work({k: v for k, v in row.items() if v},
                                           {"file": fp, "pointer": "row/%d" % (i + 2)})
                        if w:
                            raw.append(w)
            files.append(fp)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            notes.append("skipped %s: %s" % (fp, exc))
    # dedupe records by canonical key, union refs/cites
    works = {}
    for w in raw:
        key = pointer_key(w) or ("t:" + norm_title(w["title"])[:90])
        if not key or key == "t:":
            continue
        cur = works.get(key)
        if cur is None:
            works[key] = w
            continue
        for f in ("title", "year", "venue", "cited_by", "doi", "arxiv"):
            if not cur.get(f) and w.get(f):
                cur[f] = w[f]
        if not cur["authors"] and w["authors"]:
            cur["authors"] = w["authors"]
        seen = {pointer_key(p) for p in cur["refs"]}
        for p in w["refs"]:
            if pointer_key(p) not in seen:
                cur["refs"].append(p)
                seen.add(pointer_key(p))
        seen = {pointer_key(p) for p in cur["cites"]}
        for p in w["cites"]:
            if pointer_key(p) not in seen:
                cur["cites"].append(p)
                seen.add(pointer_key(p))
    log.append("corpus: %d files, %d raw records, %d unique works"
               % (len(files), len(raw), len(works)))
    return works, files, notes

# ---------------------------------------------------------------- seed


def find_seed(works, case, log):
    text = json.dumps(case, ensure_ascii=False)
    dois = []
    for m in re.finditer(r"10\.\d{4,9}/[^\s\"',}\]]+", text):
        d = norm_doi(m.group(0))
        if d and d not in dois:
            dois.append(d)
    attempts = []
    by_doi = {w["doi"]: k for k, w in works.items() if w.get("doi")}
    by_arxiv = {w["arxiv"]: k for k, w in works.items() if w.get("arxiv")}
    by_title = {norm_title(w["title"]): k for k, w in works.items() if w.get("title")}
    for d in dois:
        attempts.append({"by": "doi", "value": d, "hit": d in by_doi})
        if d in by_doi:
            return works[by_doi[d]], attempts
    for m in re.finditer(r"\b\d{4}\.\d{4,5}(v\d+)?\b", text):
        a = norm_arxiv(m.group(0))
        attempts.append({"by": "arxiv", "value": a, "hit": a in by_arxiv})
        if a in by_arxiv:
            return works[by_arxiv[a]], attempts
    seed_obj = case.get("seed_paper") or case.get("seed") or {}
    titles = []
    if isinstance(seed_obj, dict) and isinstance(seed_obj.get("title"), str):
        titles.append(seed_obj["title"])
    for key in ("seed_title", "title", "paper_title"):
        if isinstance(case.get(key), str) and len(case[key]) > 12:
            titles.append(case[key])
    for t in titles:
        nt = norm_title(t)
        attempts.append({"by": "title", "value": t, "hit": nt in by_title})
        if nt in by_title:
            return works[by_title[nt]], attempts
    if titles:
        q = salient_tokens(titles[0])
        best, bs = None, 0.0
        for w in works.values():
            s = len(q & salient_tokens(w["title"])) / max(1, len(q | salient_tokens(w["title"])))
            if s > bs:
                best, bs = w, s
        attempts.append({"by": "title_fuzzy", "hit": bool(best and bs >= 0.75),
                         "score": round(bs, 3)})
        if best and bs >= 0.75:
            return best, attempts
    log.append("WARNING: seed not found in corpus")
    return None, attempts

# ---------------------------------------------------------------- signals


def discover(seed, works, args, log):
    seed_key = pointer_key(seed)
    seed_ref_keys = set()
    ref_of = {}          # ref_key -> locator in seed record
    for p in seed["refs"]:
        k = pointer_key(p)
        if k:
            seed_ref_keys.add(k)
            ref_of[k] = p["locator"]
    seed_citers = {}     # work_key -> evidence locator (works citing seed)
    for k, w in works.items():
        if k == seed_key:
            continue
        for p in w["refs"]:
            if pointer_key(p) == seed_key:
                seed_citers[k] = p["locator"]
    for p in seed["cites"]:
        k = pointer_key(p)
        if k and k in works and k != seed_key:
            seed_citers.setdefault(k, p["locator"])

    direct = set(seed_ref_keys) | set(seed_citers)
    seed_authors = surnames(seed["authors"])
    seed_tokens = salient_tokens(seed["title"])
    seed_venue = (seed.get("venue") or "").strip().lower()

    cand = {}
    for k, w in works.items():
        if k == seed_key or k in direct:
            continue
        w_ref_keys = {pointer_key(p): p for p in w["refs"]}
        w_ref_set = set(w_ref_keys)
        # S1 co-citation: which citers of the seed also cite w
        cocit = []
        for citer_key, via_loc in seed_citers.items():
            citer = works[citer_key]
            for p in citer["refs"]:
                if pointer_key(p) == k:
                    cocit.append({"citing_work": citer_key,
                                  "citer_cites_seed_at": via_loc,
                                  "citer_cites_candidate_at": p["locator"]})
                    break
        # S2 bibliographic coupling: shared references with the seed
        shared = [{"shared_reference": rk,
                   "seed_cites_at": ref_of.get(rk),
                   "candidate_cites_at": w_ref_keys[rk]["locator"]}
                  for rk in sorted(w_ref_set & seed_ref_keys)]
        if not cocit and not shared:
            continue  # structural signals are mandatory
        # S3 / S4 secondary
        shared_auth = sorted(seed_authors & surnames(w["authors"]))
        shared_tok = sorted(seed_tokens & salient_tokens(w["title"]))
        same_venue = bool(seed_venue and w.get("venue")
                          and seed_venue == str(w["venue"]).strip().lower())
        cand[k] = {"work": w, "cocitation": cocit, "coupling": shared,
                   "shared_authors": shared_auth, "shared_tokens": shared_tok,
                   "same_venue": same_venue}

    # scoring with normalization
    n_citers = max(1, len(seed_citers))
    n_seed_refs = max(1, len(seed_ref_keys))
    for k, c in cand.items():
        w = c["work"]
        w_cited_by = w.get("cited_by") if isinstance(w.get("cited_by"), int) else None
        # Ochiai for co-citation when candidate's own citation count is known,
        # otherwise conservative sqrt normalization by seed citer count only
        denom = math.sqrt(n_citers * w_cited_by) if w_cited_by else math.sqrt(n_citers)
        s1 = len(c["cocitation"]) / denom if denom else 0.0
        union = len(seed_ref_keys | {pointer_key(p) for p in w["refs"]})
        s2 = len(c["coupling"]) / max(1, union)
        s3 = 0.15 * len(c["shared_authors"])
        s4 = 0.05 * (len(c["shared_tokens"]) + (1 if c["same_venue"] else 0))
        c["score_parts"] = {"co_citation": round(s1, 4), "coupling": round(s2, 4),
                            "author": round(s3, 4), "venue_task": round(s4, 4)}
        c["score"] = round(s1 + s2 + s3 + s4, 4)
        c["support"] = len(c["cocitation"]) + len(c["coupling"])

    ranked = sorted(cand.items(), key=lambda kv: (-kv[1]["score"], -kv[1]["support"], kv[0]))
    ranked = [(k, c) for k, c in ranked if c["support"] >= args.min_support][:args.top]
    log.append("discovery: %d direct neighbors excluded, %d structural candidates, "
               "%d delivered after thresholds"
               % (len(direct), len(cand), len(ranked)))
    return ranked, direct, seed_citers

# ---------------------------------------------------------------- result


def brief(w):
    return {"doi": w.get("doi"), "arxiv": w.get("arxiv"), "title": w.get("title"),
            "year": w.get("year"),
            "authors": [(a.get("family") or a.get("name")) for a in w.get("authors", [])][:8],
            "venue": w.get("venue"), "cited_by": w.get("cited_by"),
            "locator": w.get("locator")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", default=None)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--min-support", type=int, default=1)
    args = ap.parse_args()

    started = time.time()
    out_dir, work_dir = Path(args.out), Path(args.workdir)
    for d in (out_dir, work_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    log = ["codiscover started " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]

    try:
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = {"case_id": "unknown_case", "skill": "cocitation-parallel-discovery",
                  "status": "failed", "candidates": [], "evidence_records": log + ["FATAL: %s" % exc],
                  "uncertainty": ["case file unreadable"], "sources": [], "change_records": []}
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({"status": "failed"}))
        return 0
    case_id = case.get("case_id") or case.get("id") or "unknown_case"

    roots = list(DEFAULT_ROOTS)
    case_dir = str(Path(args.case).resolve().parent)
    if case_dir not in roots:
        roots.insert(0, case_dir)
    if args.roots:
        roots += [r.strip() for r in args.roots.split(",") if r.strip()]

    works, files, notes = load_corpus(roots, log)
    seed, attempts = find_seed(works, case, log)

    uncertainty = list(notes[:8])
    candidates, direct_info = [], {}
    if seed is None:
        status = "partial"
        uncertainty.append("seed not found in local corpus; no candidates generated")
    else:
        ranked, direct, seed_citers = discover(seed, works, args, log)
        status = "ok" if ranked else "partial"
        if not ranked:
            uncertainty.append("no parallel works met the structural-signal threshold; "
                               "this is a true empty result, not a failure")
        for k, c in ranked:
            w = c["work"]
            candidates.append({
                "rank": len(candidates) + 1,
                **brief(w),
                "score": c["score"], "score_parts": c["score_parts"],
                "support": c["support"],
                "association_evidence": {
                    "co_citation": c["cocitation"],
                    "bibliographic_coupling": c["coupling"],
                    "shared_authors": c["shared_authors"],
                    "shared_title_tokens": c["shared_tokens"],
                    "same_venue": c["same_venue"],
                },
                "excluded_direct_relation": True,
            })
        direct_info = {
            "n_seed_references": len([k for k in direct if k in {pointer_key(p) for p in seed["refs"]}]),
            "n_seed_citers": len(seed_citers),
            "note": "direct neighbors are excluded from candidates by design "
                    "(parallel works only); they remain available via snowball tracing",
        }

    result = {
        "case_id": case_id,
        "skill": "cocitation-parallel-discovery",
        "status": status,
        "seed": brief(seed) if seed else None,
        "seed_resolution_attempts": attempts,
        "parameters": {"top": args.top, "min_support": args.min_support},
        "candidates": candidates,
        "direct_neighbors": direct_info,
        "stats": {"corpus_works": len(works), "corpus_files": len(files),
                  "n_candidates": len(candidates)},
        "sources": [{"file": f} for f in files],
        "evidence_records": log,
        "uncertainty": uncertainty,
        "change_records": [],
    }
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for field in contract:
            if field not in result:
                result[field] = None
        result["output_contract_fields"] = sorted(contract.keys())

    log.append("finished in %.1fs, status=%s, %d candidates"
               % (time.time() - started, status, len(candidates)))
    try:
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        md = ["# 关联文献发现证据表（自动生成）", "",
              "| 排名 | 文献 | 得分 | 共被引次数 | 耦合共享参考文献数 | 共享作者 |",
              "|-|-|-|-|-|-|"]
        for c in candidates:
            md.append("| %d | %s (%s) | %.3f | %d | %d | %s |" % (
                c["rank"], (c["title"] or c.get("doi") or "?")[:60].replace("|", "\\|"),
                c.get("year") or "?", c["score"], len(c["association_evidence"]["co_citation"]),
                len(c["association_evidence"]["bibliographic_coupling"]),
                ", ".join(c["association_evidence"]["shared_authors"]) or "-"))
        (out_dir / "evidence_table.md").write_text("\n".join(md), encoding="utf-8")
    except OSError as exc:
        log.append("WARNING: write failed: %s" % exc)
        (work_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (work_dir / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps({"status": status, "candidates": len(candidates),
                      "corpus_works": len(works), "seed": bool(seed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
