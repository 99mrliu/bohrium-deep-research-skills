#!/usr/bin/env python3
"""Deduplication, metadata merge and verification over the federated pool.

Reads /app/work/pool.json (from federated_search.py), clusters duplicate
records (exact DOI match; fuzzy normalized-title match >= 0.92 via difflib),
merges each cluster into one canonical record keeping per-field provenance,
records metadata conflicts (same field, different non-empty values across
sources), and verifies a bounded sample of DOIs against Crossref.

Usage:
  python3 dedup_verify.py --work /app/work --out /app/output \
      [--case /input/case.json] [--verify-n 15] [--no-verify]

Every output record carries: canonical metadata, ids, provenance[] (all
source sightings), field_sources (which source supplied each field) and
verification status. Nothing is deleted: merged-away copies remain visible
inside provenance and in dedup_report.md.
"""
import argparse
import difflib
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "litsearch-federated-provenance/1.0 (dedup/verify)"}
QUESTION_KEYS = ["research_question", "question", "task", "topic", "query",
                 "title", "description", "research_topic", "objective"]
STOPWORDS = set("""a an the and or of for in on with by to from at as is are was were be been
we our their its this that these those using use based study studies results analysis method
methods approach approaches via between over under into new novel review effect effects
research paper experimental investigation literature find recent relevant search papers especially related current state art 研究 方法 基于 的 与 和 在 对 及 其 综述""".split())


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def cluster(records, threshold=0.92):
    """Union-find over DOI equality and fuzzy title similarity."""
    n = len(records)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_doi = {}
    for i, r in enumerate(records):
        d = (r.get("ids") or {}).get("doi") or r.get("doi")
        if d:
            if d in by_doi:
                union(i, by_doi[d])
            else:
                by_doi[d] = i
    norm = [norm_title(r.get("title")) for r in records]
    by_first = {}
    for i, t in enumerate(norm):
        if t:
            by_first.setdefault(t[:25], []).append(i)
    for _prefix, idxs in by_first.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if find(i) == find(j):
                    continue
                di = (records[i].get("ids") or {}).get("doi") or records[i].get("doi")
                dj = (records[j].get("ids") or {}).get("doi") or records[j].get("doi")
                if di and dj and di != dj:
                    # Two different DOIs are two different publications even when
                    # titles match (e.g. paper vs. supporting-information DOI).
                    continue
                if norm[i] and norm[j] and difflib.SequenceMatcher(
                        None, norm[i], norm[j]).ratio() >= threshold:
                    union(i, j)
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    return list(clusters.values())


def dedupe_conflicts(conflicts):
    seen, out = set(), []
    for c in conflicts:
        key = (c["field"], str(c["kept"]), str(c["other"]), c["record"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


FIELD_PRIORITY = {"local-snapshot": 0, "crossref": 1, "openalex": 2,
                  "europepmc": 3, "arxiv": 4}


def merge_cluster(recs):
    """Merge cluster records into one canonical record; track conflicts."""
    recs = sorted(recs, key=lambda r: FIELD_PRIORITY.get(
        (r.get("provenance") or [{}])[0].get("source", ""), 9))
    canon, field_sources, conflicts = {}, {}, []
    fields = ["title", "authors", "year", "venue", "doi", "abstract",
              "cited_by", "type", "url"]
    for f in fields:
        best, best_src = None, None
        for r in recs:
            v = r.get(f)
            empty = v in (None, "", [], 0) if f != "cited_by" else v is None
            if empty:
                continue
            src = (r.get("provenance") or [{}])[0].get("source", "?")
            if best is None:
                best, best_src = v, src
            elif f in ("year", "venue", "title", "doi") and v != best:
                conflicts.append({"field": f, "kept": best, "kept_from": best_src,
                                  "other": v,
                                  "other_from": src,
                                  "record": (best if f == "title" else
                                             recs[0].get("title", ""))[:80]})
        canon[f] = best
        if best_src:
            field_sources[f] = best_src
    canon["cited_by"] = max((r.get("cited_by") or 0) for r in recs)
    canon["ids"] = {}
    for r in recs:
        for k, v in (r.get("ids") or {}).items():
            if v:
                canon["ids"].setdefault(k, v)
    prov = []
    for r in recs:
        prov.extend(r.get("provenance") or [])
    canon["provenance"] = prov
    canon["field_sources"] = field_sources
    canon["merged_from"] = len(recs)
    return canon, conflicts


def verify_doi(doi, timeout=15.0):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        msg = data.get("message", {})
        return {"status": "verified",
                "title": (msg.get("title") or [""])[0][:120],
                "year": ((msg.get("published") or {}).get("date-parts")
                         or [[None]])[0][0]}
    except Exception as e:  # noqa: BLE001
        return {"status": "unreachable", "error": "%s: %s" % (type(e).__name__, e)}


def relevance(rec, qterms):
    text = ((rec.get("title") or "") + " " + (rec.get("abstract") or "")).lower()
    if not qterms:
        return 0.0
    hit = sum(1 for t in qterms if t in text)
    cit = math.log1p(rec.get("cited_by") or 0) / math.log1p(5000)
    return round(0.8 * hit / len(qterms) + 0.2 * min(cit, 1.0), 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--verify-n", type=int, default=15)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--title-threshold", type=float, default=0.92)
    args = ap.parse_args()

    work, out = Path(args.work), Path(args.out)
    pool = json.loads((work / "pool.json").read_text(encoding="utf-8"))

    clusters = cluster(pool, args.title_threshold)
    merged, conflicts = [], []
    for idxs in clusters:
        canon, conf = merge_cluster([pool[i] for i in idxs])
        merged.append(canon)
        conflicts.extend(conf)
    conflicts = dedupe_conflicts(conflicts)

    # question terms for a simple, documented relevance order
    qtext = ""
    if Path(args.case).exists():
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8",
                                                        errors="replace"))
        except Exception:  # noqa: BLE001
            case = {}
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
        qtext = " ".join(texts)
    if Path(args.task).exists():
        qtext += " " + Path(args.task).read_text(encoding="utf-8",
                                                 errors="replace")[:2000]
    qterms = sorted({w.lower() for w in re.findall(
        r"[a-z][a-z\-]{3,}|[一-鿿]{2,}", qtext.lower())
        if w.lower() not in STOPWORDS})[:12]

    for r in merged:
        r["relevance_score"] = relevance(r, qterms)
    merged.sort(key=lambda x: (-x["merged_from"], -x["relevance_score"]))

    # verification of a bounded DOI sample
    verified = []
    if not args.no_verify:
        done = set()
        for r in merged:
            doi = (r.get("ids") or {}).get("doi")
            if not doi or doi in done:
                continue
            done.add(doi)
            if len(verified) >= args.verify_n:
                break
            res = verify_doi(doi)
            res["doi"] = doi
            if res["status"] == "verified" and r.get("title"):
                sim = difflib.SequenceMatcher(
                    None, norm_title(res.get("title")),
                    norm_title(r["title"])).ratio()
                res["title_match"] = round(sim, 3)
                if sim < 0.8:
                    res["status"] = "metadata-mismatch"
            verified.append(res)
            time.sleep(0.3)
    vmap = {v["doi"]: v for v in verified}
    for r in merged:
        doi = (r.get("ids") or {}).get("doi")
        r["verification"] = vmap.get(doi, {"status": "not-checked"}) if doi \
            else {"status": "no-doi"}

    (out / "final_records.json").write_text(json.dumps(
        merged, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "provenance.jsonl", "w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps({"title": r.get("title"), "ids": r.get("ids"),
                                "merged_from": r["merged_from"],
                                "field_sources": r.get("field_sources"),
                                "verification": r.get("verification"),
                                "provenance": r.get("provenance")},
                               ensure_ascii=False) + "\n")
    with open(out / "candidates.md", "w", encoding="utf-8") as f:
        f.write("# Canonical literature records (deduplicated, provenance-tracked)\n\n")
        f.write("%d raw hits -> %d canonical records. Order: multi-source records "
                "first, then relevance. Full detail: final_records.json, "
                "provenance.jsonl, dedup_report.md.\n\n" % (len(pool), len(merged)))
        for i, r in enumerate(merged[:40], 1):
            srcs = sorted({p.get("source", "?") for p in r.get("provenance", [])})
            ver = r.get("verification", {}).get("status", "?")
            f.write("## %d. %s\n- score %.3f | %s | %s | DOI: %s | sources: %s "
                    "| merged: %d | verification: %s\n- authors: %s\n- abstract: %s\n\n"
                    % (i, r.get("title") or "(no title)", r["relevance_score"],
                       r.get("year") or "?", (r.get("venue") or "?")[:80],
                       (r.get("ids") or {}).get("doi") or "none",
                       ", ".join(srcs), r["merged_from"], ver,
                       "; ".join((r.get("authors") or [])[:5]) or "?",
                       (r.get("abstract") or "(none)")[:350]))
    n_multi = sum(1 for r in merged if r["merged_from"] > 1)
    with open(out / "dedup_report.md", "w", encoding="utf-8") as f:
        f.write("# Deduplication & verification report\n\n")
        per_src = {}
        for r in pool:
            s = (r.get("provenance") or [{}])[0].get("source", "?")
            per_src[s] = per_src.get(s, 0) + 1
        f.write("## Input per source\n\n")
        for s, c in sorted(per_src.items()):
            f.write("- %s: %d raw hits\n" % (s, c))
        f.write("\n## Result\n\n- raw hits: %d\n- canonical records: %d\n"
                "- records found in >1 source: %d\n- duplicate sightings merged away: %d\n"
                % (len(pool), len(merged), n_multi, len(pool) - len(merged)))
        f.write("\n## Metadata conflicts (%d)\n\n" % len(conflicts))
        for c in conflicts[:30]:
            f.write("- field `%s`: kept %r (from %s) vs %r (from %s) — %s\n"
                    % (c["field"], str(c["kept"])[:60], c["kept_from"],
                       str(c["other"])[:60], c["other_from"], c["record"]))
        if not conflicts:
            f.write("- none\n")
        f.write("\n## DOI verification sample (%d checked)\n\n" % len(verified))
        for v in verified:
            f.write("- %s: %s%s\n" % (v["doi"], v["status"],
                    (" (title_match %.2f)" % v["title_match"]) if "title_match" in v
                    else (" — " + v.get("error", "")) if v["status"] == "unreachable"
                    else ""))
    n_ver = sum(1 for v in verified if v["status"] == "verified")
    n_mis = sum(1 for v in verified if v["status"] == "metadata-mismatch")
    print(json.dumps({"DEDUP_STATUS": "success",
                      "raw_hits": len(pool), "canonical": len(merged),
                      "multi_source_records": n_multi,
                      "conflicts": len(conflicts),
                      "doi_verified": n_ver, "doi_mismatch": n_mis,
                      "doi_unreachable": sum(1 for v in verified
                                             if v["status"] == "unreachable")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
