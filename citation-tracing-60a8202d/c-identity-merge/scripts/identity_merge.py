#!/usr/bin/env python3
"""Cross-database identity resolution, version merging and dedup audit.

Stdlib only (Python 3.8+). Ingests scholarly records from ALL local sources
WITHOUT pre-dedup, then decides which records describe the same work, merging
preprint / conference / journal / supplement versions into clusters and keeping
a per-cluster merge-evidence ledger that a reviewer can re-check.

Decision tiers (deterministic, rule-based; see rules/dedup_keys.md):
  AUTO_MERGE   -- same normalized DOI, or same arXiv id, or
                  identical title fingerprint + year diff <= 1 + author overlap,
                  or title Jaccard >= 0.90 + first-author same + year diff <= 2
  REVIEW       -- strong title similarity (>= 0.80) but conflicting hard ids
                  (both have DOIs that differ), or same title fingerprint with
                  disjoint authors (same-name-different-work suspicion)
  KEEP_SEPARATE-- everything else; explicit pair notes only for near-misses

Version classification per record: preprint / conference / journal /
supplement / dataset / unknown, from Crossref type, venue fields and id shape.
Canonical record per cluster: journal > conference > preprint > others, then
the most complete record; all member identifiers are unioned, never discarded.

Outputs: clean deduplicated work list, cluster ledger with merge evidence,
review queue, conflict list, and result.json mirroring output_contract.
Nothing is fabricated: merged-away records remain listed under their cluster
with original locators.

Usage:
    python3 identity_merge.py --case /input/case.json --out /app/output \
        [--workdir /app/work] [--review-threshold 0.80]
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

DEFAULT_ROOTS = ["/input", "./environment", "/app/work", "."]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "output"}
SKIP_FILES = {"result.json", "run_log.json", "verify_report.json",
              "merge_ledger.json", "case.json"}
MAX_FILE_BYTES = 60 * 1024 * 1024
MAX_FILES = 400
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "by",
    "from", "at", "as", "is", "are", "was", "were", "via", "using", "based",
}

# ------------------------------------------------------------------ normalization


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


def main_title_fp(v):
    """Fingerprint of the part before a subtitle separator."""
    t = norm_title(v)
    return t


def title_tokens(v):
    return {t for t in norm_title(v).split() if t and t not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def surname_list(authors):
    out = []
    for a in authors or []:
        if isinstance(a, dict):
            name = a.get("family") or a.get("name") or ""
        else:
            name = str(a)
        parts = name.split(",")[0].strip().split()
        if parts:
            out.append(parts[-1].lower())
    return out

# ------------------------------------------------------------------ ingestion


def record_from(obj, locator):
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
    year = None
    for k in ("year", "pubYear", "publication_year"):
        if obj.get(k):
            try:
                year = int(str(obj[k])[:4])
                break
            except ValueError:
                pass
    if year is None:
        for k in ("issued", "published", "created", "publication_date",
                  "firstPublicationDate"):
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
    raw = obj.get("author") or obj.get("authors") or obj.get("authorString") \
        or obj.get("authorships")
    if isinstance(raw, str):
        authors = [{"name": p.strip()} for p in raw.split(",") if p.strip()][:25]
    elif isinstance(raw, list):
        for a in raw[:25]:
            if isinstance(a, dict):
                if "family" in a or "given" in a:
                    authors.append({"given": a.get("given"), "family": a.get("family")})
                elif "name" in a:
                    authors.append({"name": a["name"]})
                elif isinstance(a.get("author"), dict):
                    authors.append({"name": a["author"].get("display_name")})
            elif isinstance(a, str):
                authors.append({"name": a})
    venue = obj.get("container-title") or obj.get("venue") or obj.get("journalTitle") \
        or obj.get("bookTitle") or obj.get("publisher")
    if isinstance(venue, list):
        venue = venue[0] if venue else None
    if isinstance(venue, dict):
        venue = venue.get("display_name")
    ext_ids = {}
    for k in ("pmid", "pmcid", "paperId", "id", "mag", "openalex"):
        if obj.get(k) and not isinstance(obj.get(k), (dict, list)):
            ext_ids[k] = str(obj[k])
    for k, v in ids.items():
        ext_ids[str(k).lower()] = str(v)
    return {
        "doi": doi, "arxiv": ax, "title": str(title) if title else "",
        "year": year, "authors": authors, "venue": venue,
        "type": obj.get("type") or obj.get("pubType") or obj.get("type_crossref"),
        "source": obj.get("source") or obj.get("src"),
        "ext_ids": ext_ids,
        "volume": obj.get("volume"), "issue": obj.get("issue"),
        "pages": obj.get("page") or obj.get("pages"),
        "locator": locator,
    }


def classify_version(rec):
    t = (rec.get("type") or "").lower()
    venue = (rec.get("venue") or "").lower()
    if rec.get("arxiv") and not rec.get("doi"):
        return "preprint"
    if any(x in t for x in ("posted", "preprint")) or "arxiv" in venue or "biorxiv" in venue \
            or "ssrn" in venue or "chemrxiv" in venue:
        return "preprint"
    if any(x in t for x in ("proceedings", "conference", "paper-conference")):
        return "conference"
    if any(x in t for x in ("journal", "article-journal")):
        return "journal"
    if "supplement" in t or "supplementary" in (rec.get("title") or "").lower()[:80]:
        return "supplement"
    if "dataset" in t or "data" == t:
        return "dataset"
    if "book" in t or "chapter" in t:
        return "book"
    return "unknown"


def walk_json(obj, path, file_path, sink, depth=0):
    if depth > 12:
        return
    if isinstance(obj, dict):
        rec = record_from(obj, {"file": file_path, "pointer": path or "$"})
        if rec is not None and (rec["title"] or rec["doi"]):
            sink.append(rec)
            return
        for k, v in obj.items():
            if k in ("author", "authors", "authorships"):
                continue
            walk_json(v, "%s/%s" % (path, k), file_path, sink, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:30000]):
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


def ingest(roots, log):
    records, files, notes = [], [], []
    for path in discover_files(roots):
        fp = str(path)
        try:
            if path.suffix.lower() == ".json":
                walk_json(json.loads(path.read_text(encoding="utf-8", errors="replace")),
                          "$", fp, records)
            elif path.suffix.lower() in (".jsonl", ".ndjson"):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            walk_json(json.loads(line), "$/%d" % i, fp, records)
                        except json.JSONDecodeError:
                            notes.append("bad JSONL %s:%d" % (fp, i + 1))
            else:
                with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                    sample = fh.read(4096)
                    fh.seek(0)
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if sample.strip() else csv.excel
                    for i, row in enumerate(csv.DictReader(fh, dialect=dialect)):
                        rec = record_from({k: v for k, v in row.items() if v},
                                          {"file": fp, "pointer": "row/%d" % (i + 2)})
                        if rec:
                            records.append(rec)
            files.append(fp)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            notes.append("skipped %s: %s" % (fp, exc))
    for idx, rec in enumerate(records):
        rec["rid"] = "r%06d" % idx
        rec["version"] = classify_version(rec)
    log.append("ingested %d records from %d files (no pre-dedup)"
               % (len(records), len(files)))
    return records, files, notes

# ------------------------------------------------------------------ matching


def build_blocks(records):
    blocks = {}
    def put(k, rid):
        if k:
            blocks.setdefault(k, set()).add(rid)
    for rec in records:
        rid = rec["rid"]
        if rec["doi"]:
            put("doi:" + rec["doi"], rid)
        if rec["arxiv"]:
            put("arxiv:" + rec["arxiv"], rid)
        fp = norm_title(rec["title"])
        if fp:
            put("tfp:" + fp[:80], rid)
            toks = sorted(title_tokens(rec["title"]))
            if len(toks) >= 2:
                put("tok:%s|%s" % (toks[0], toks[-1]), rid)
        sns = surname_list(rec["authors"])
        if sns and rec["year"]:
            put("ay:%s|%s" % (sns[0], rec["year"]), rid)
    return blocks


def pair_decision(a, b, review_threshold):
    """Return (tier, score, evidence). tier in AUTO_MERGE / REVIEW / KEEP_SEPARATE."""
    ev = {}
    if a["doi"] and b["doi"]:
        if a["doi"] == b["doi"]:
            return "AUTO_MERGE", 1.0, {"key": "doi_equal", "doi": a["doi"]}
        ev["doi_conflict"] = [a["doi"], b["doi"]]
    if a["arxiv"] and b["arxiv"] and a["arxiv"] == b["arxiv"]:
        return "AUTO_MERGE", 1.0, {"key": "arxiv_equal", "arxiv": a["arxiv"]}
    ta, tb = title_tokens(a["title"]), title_tokens(b["title"])
    sim = jaccard(ta, tb)
    fa = norm_title(a["title"]) == norm_title(b["title"]) and bool(norm_title(a["title"]))
    sa, sb = set(surname_list(a["authors"])), set(surname_list(b["authors"]))
    auth_overlap = len(sa & sb)
    first_same = bool(sa and sb and surname_list(a["authors"])[0] == surname_list(b["authors"])[0])
    yd = abs((a["year"] or 0) - (b["year"] or 0)) if (a["year"] and b["year"]) else None
    ev.update(title_jaccard=round(sim, 3), exact_title_fp=fa,
              author_overlap=auth_overlap, first_author_same=first_same,
              year_diff=yd)
    if fa and (yd is None or yd <= 1) and (auth_overlap >= 1 or not sa or not sb):
        return "AUTO_MERGE", 0.97, dict(ev, key="title_fp+year+author")
    if sim >= 0.90 and first_same and (yd is None or yd <= 2):
        return "AUTO_MERGE", 0.93, dict(ev, key="title_sim+first_author")
    if ev.get("doi_conflict") and sim >= review_threshold:
        return "REVIEW", sim, dict(ev, key="title_similar_but_doi_conflict",
                                   reason="同题不同 DOI：可能为同文不同注册或同名不同文，需人工裁定")
    if fa and sa and sb and auth_overlap == 0 and (yd or 0) <= 2:
        return "REVIEW", sim, dict(ev, key="same_title_disjoint_authors",
                                   reason="标题指纹一致但作者集合不相交：疑似同名不同文")
    if sim >= review_threshold and (first_same or auth_overlap >= 2):
        return "REVIEW", sim, dict(ev, key="near_match",
                                   reason="高标题相似但未达自动合并条件")
    return "KEEP_SEPARATE", sim, ev


def merge_records(records):
    """Union-find over AUTO_MERGE pairs; collect REVIEW pairs."""
    parent = {r["rid"]: r["rid"] for r in records}
    by_rid = {r["rid"]: r for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    blocks = build_blocks(records)
    review_pairs, auto_evidence, review_seen = [], {}, set()
    pairs_checked = 0
    for key, rids in blocks.items():
        rids = sorted(rids)
        if len(rids) > 200:
            continue  # pathological block (e.g., missing-title bucket)
        for i in range(len(rids)):
            for j in range(i + 1, len(rids)):
                a, b = by_rid[rids[i]], by_rid[rids[j]]
                pairs_checked += 1
                tier, score, ev = pair_decision(a, b, 0.80)
                if tier == "AUTO_MERGE":
                    union(a["rid"], b["rid"])
                    auto_evidence.setdefault(find(a["rid"]), []).append(
                        {"pair": [a["rid"], b["rid"]], "score": score, "evidence": ev})
                elif tier == "REVIEW":
                    pk = tuple(sorted((a["rid"], b["rid"])))
                    if pk in review_seen:
                        continue
                    review_seen.add(pk)
                    review_pairs.append({"pair": [a["rid"], b["rid"]],
                                         "a": brief(a), "b": brief(b),
                                         "score": round(score, 3), "evidence": ev})
    clusters = {}
    for r in records:
        clusters.setdefault(find(r["rid"]), []).append(r)
    return clusters, review_pairs, auto_evidence, pairs_checked


VERSION_RANK = {"journal": 5, "conference": 4, "book": 3, "preprint": 2,
                "dataset": 1, "supplement": 1, "unknown": 0}


def brief(rec):
    return {"rid": rec["rid"], "doi": rec["doi"], "arxiv": rec["arxiv"],
            "title": rec["title"], "year": rec["year"],
            "authors": surname_list(rec["authors"])[:8],
            "venue": rec["venue"], "version": rec.get("version"),
            "ext_ids": rec.get("ext_ids"), "locator": rec["locator"]}


def completeness(rec):
    return sum(1 for f in ("doi", "arxiv", "title", "year", "venue", "volume", "pages")
               if rec.get(f)) + min(len(rec.get("authors") or []), 3)


def build_cluster_output(clusters, auto_evidence):
    clean, ledger = [], []
    conflicts = []
    for root, members in clusters.items():
        members = sorted(members, key=lambda r: (-VERSION_RANK.get(r["version"], 0),
                                                 -completeness(r), r["rid"]))
        canonical = members[0]
        merged = {
            "cluster_id": root,
            "canonical": brief(canonical),
            "version": canonical["version"],
            "all_doi": sorted({m["doi"] for m in members if m["doi"]}),
            "all_arxiv": sorted({m["arxiv"] for m in members if m["arxiv"]}),
            "all_ext_ids": {k: v for m in members for k, v in (m.get("ext_ids") or {}).items()},
            "versions_present": sorted({m["version"] for m in members}),
            "members": [brief(m) for m in members],
        }
        # conflict detection inside merged cluster
        cf = []
        years = {m["year"] for m in members if m["year"]}
        if len(years) > 1:
            cf.append({"field": "year", "values": sorted(years),
                       "note": "版本年份差异（预印本/正式版常见），canonical 取 %s"
                               % canonical["year"]})
        titles = {norm_title(m["title"]) for m in members if m["title"]}
        if len(titles) > 1:
            cf.append({"field": "title", "n_distinct": len(titles),
                       "note": "标题存在大小写/副标题/措辞差异，已按指纹合并"})
        merged["field_conflicts"] = cf
        if cf:
            conflicts.append({"cluster_id": root, "conflicts": cf})
        clean.append(merged)
        ledger.append({
            "cluster_id": root,
            "n_members": len(members),
            "decision": "AUTO_MERGE" if len(members) > 1 else "SINGLETON",
            "merge_evidence": auto_evidence.get(root, []),
            "canonical_choice": {
                "rid": canonical["rid"],
                "rule": "version rank (journal>conference>preprint) then completeness",
                "version": canonical["version"],
            },
            "members_retained": [{"rid": m["rid"], "locator": m["locator"]}
                                 for m in members],
        })
    clean.sort(key=lambda c: c["cluster_id"])
    return clean, ledger, conflicts

# ------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--roots", default=None)
    ap.add_argument("--review-threshold", type=float, default=0.80)
    args = ap.parse_args()

    started = time.time()
    out_dir, work_dir = Path(args.out), Path(args.workdir)
    for d in (out_dir, work_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    log = ["identity_merge started " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]

    try:
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = {"case_id": "unknown_case", "skill": "crossdb-identity-merge",
                  "status": "failed", "clean_works": [], "evidence_records": log + ["FATAL: %s" % exc],
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

    records, files, notes = ingest(roots, log)
    clusters, review_pairs, auto_evidence, pairs_checked = merge_records(records)
    clean, ledger, conflicts = build_cluster_output(clusters, auto_evidence)

    n_multi = sum(1 for c in clean if len(c["members"]) > 1)
    uncertainty = list(notes[:8])
    if review_pairs:
        uncertainty.append("%d 对待人工裁定的疑似重复（review_queue），未自动合并"
                           % len(review_pairs))
    if not records:
        uncertainty.append("本地未发现可解析的文献记录；交付空清单")

    status = "ok" if records else "partial"
    result = {
        "case_id": case_id,
        "skill": "crossdb-identity-merge",
        "status": status,
        "parameters": {"review_threshold": args.review_threshold},
        "clean_works": clean,
        "review_queue": review_pairs,
        "conflicts": conflicts,
        "stats": {
            "records_ingested": len(records),
            "clusters": len(clean),
            "multi_record_clusters": n_multi,
            "duplicates_removed": len(records) - len(clean),
            "review_pairs": len(review_pairs),
            "pairs_checked": pairs_checked,
            "corpus_files": len(files),
        },
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

    log.append("finished in %.1fs: %d records -> %d clusters (%d merged, %d review pairs)"
               % (time.time() - started, len(records), len(clean), n_multi, len(review_pairs)))
    try:
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        (out_dir / "merge_ledger.json").write_text(json.dumps(
            {"ledger": ledger}, ensure_ascii=False, indent=2), encoding="utf-8")
        md = ["# 去重与身份合并证据表（自动生成）", "",
              "| 簇 | 成员数 | 版本集合 | canonical | 全部 DOI | 合并依据数 |",
              "|-|-|-|-|-|-|"]
        led_by_id = {l["cluster_id"]: l for l in ledger}
        for c in clean:
            l = led_by_id[c["cluster_id"]]
            md.append("| %s | %d | %s | %s | %s | %d |" % (
                c["cluster_id"], len(c["members"]), "/".join(c["versions_present"]),
                (c["canonical"]["title"] or c["canonical"]["doi"] or "?")[:50].replace("|", "\\|"),
                "; ".join(c["all_doi"])[:60] or "-",
                len(l["merge_evidence"])))
        (out_dir / "merge_table.md").write_text("\n".join(md), encoding="utf-8")
    except OSError as exc:
        log.append("WARNING: write failed: %s" % exc)
        (work_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (work_dir / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps({"status": status, "records": len(records), "clusters": len(clean),
                      "merged": n_multi, "review": len(review_pairs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
