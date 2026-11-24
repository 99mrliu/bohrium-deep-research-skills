#!/usr/bin/env python3
"""Query a retrieval-gate index with explicit no-hit and low-recall handling.

Scoring (documented in references/retrieval_protocol.md):
  query text is tokenized exactly like at index time (lowercase latin words +
  CJK bigrams). For each query term, each document scores the sum of its term
  frequencies across all indexed fields that contain the term (text, tags, type,
  file):  score(doc) = SUM_terms SUM_fields tf(term, doc, field).
  Ranking is by (-score, doc_id) so output is fully deterministic.

Filters (facets): --tag exact membership in doc tags; --type exact match on doc
type; --file exact match on any file the doc is located in; --since/--until
inclusive YYYY-MM-DD bounds on the doc date (docs without a date are excluded
when a date filter is active).

Explicit behaviors:
  * zero hits -> a structured no-hit report is printed, including facet-
    elimination diagnosis (each active facet is retried individually; a facet
    whose removal alone restores hits is named as the eliminator) plus
    suggestions (relax filters, check spelling variants).
  * max score < LOW_SCORE_THRESHOLD (2.0) -> the whole result is marked
    low_confidence: true and each weak hit carries low_confidence: true.
  * with --log FILE, every query is appended to that JSONL file as
    {seq, args, hits, low_confidence}; seq is the previous line count + 1.
    No wall-clock is recorded, so the log is deterministic and replayable.

Exit codes: 0 ok (a no-hit answer is a normal answer), 2 usage/input error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_index import tokenize  # noqa: E402

LOW_SCORE_THRESHOLD = 2.0


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def load_index(path):
    if not os.path.isfile(path):
        die(f"index not found: {path}")
    try:
        with open(path, encoding="utf-8") as fh:
            idx = json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"{path}: invalid JSON: {exc}")
    if "docs" not in idx or "index" not in idx:
        die(f"{path}: not a retrieval-gate index (missing docs/index)")
    return idx


def search(idx, q=None, tag=None, type_=None, file=None, since=None, until=None):
    """Return [(doc_id, score), ...] sorted by (-score, doc_id)."""
    docs = idx["docs"]
    inverted = idx["index"]
    terms = tokenize(q) if q else []
    scores = {}
    if terms:
        for t in terms:
            for doc_id, fields in inverted.get(t, {}).items():
                scores[doc_id] = scores.get(doc_id, 0) + sum(fields.values())
    else:
        scores = {d: 0 for d in docs}

    def keep(doc_id):
        d = docs.get(doc_id)
        if d is None:
            return False  # posting without a document (corrupt/tampered index)
        if tag and tag not in (d.get("tags") or []):
            return False
        if type_ and d.get("type") != type_:
            return False
        if file and file not in (d.get("files") or []):
            return False
        date = d.get("date")
        if since and (not date or date < since):
            return False
        if until and (not date or date > until):
            return False
        return True

    return sorted(((d, s) for d, s in scores.items() if keep(d)),
                  key=lambda x: (-x[1], x[0]))


def diagnose(idx, q, tag, type_, file, since, until):
    """Facet-elimination diagnosis for a zero-hit query."""
    active = []
    if tag:
        active.append("tag")
    if type_:
        active.append("type")
    if file:
        active.append("file")
    if since or until:
        active.append("date_range")

    report = {"eliminating_facets": [], "combination_eliminated": False,
              "text_terms_matched_nothing": False, "suggestions": []}
    for facet in active:
        kw = dict(q=q, tag=tag, type_=type_, file=file, since=since, until=until)
        if facet == "date_range":
            kw["since"] = kw["until"] = None
        else:
            kw[facet] = None
        if search(idx, **kw):
            report["eliminating_facets"].append(facet)
    if active and not report["eliminating_facets"] and search(idx, q=q):
        report["combination_eliminated"] = True
    if q and not search(idx, q=q):
        report["text_terms_matched_nothing"] = True

    if report["eliminating_facets"]:
        report["suggestions"].append(
            "relax or remove facet(s) " + ", ".join(report["eliminating_facets"]) +
            " — each one single-handedly eliminated every hit")
    if report["combination_eliminated"]:
        report["suggestions"].append(
            "no single facet is solely responsible; the filter combination "
            "eliminated all hits — relax more than one filter")
    if report["text_terms_matched_nothing"]:
        report["suggestions"].append(
            "no document contains the query terms — check spelling variants, "
            "synonyms, or broader terms (remember CJK text is matched by bigrams)")
    if not q:
        report["suggestions"].append(
            "only filters were given; relax the filters or add query text")
    report["suggestions"].append(
        "inspect what the index actually holds with a broad query, a known tag, "
        "or a bare --file filter")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Query a retrieval-gate inverted index (theme/tag/entity/"
                    "source/time retrieval) with no-hit and low-recall handling.")
    ap.add_argument("--index", required=True, help="index.json from build_index.py")
    ap.add_argument("--q", help="query text (latin words and/or CJK; bigram-matched)")
    ap.add_argument("--tag", help="require exact tag membership")
    ap.add_argument("--type", dest="type_", help="require exact doc type")
    ap.add_argument("--file", help="require doc located in this file (exact relpath)")
    ap.add_argument("--since", help="inclusive lower date bound YYYY-MM-DD")
    ap.add_argument("--until", help="inclusive upper date bound YYYY-MM-DD")
    ap.add_argument("--log", help="append the query to this JSONL log (seq-numbered)")
    args = ap.parse_args(argv)

    idx = load_index(args.index)
    results = search(idx, q=args.q, tag=args.tag, type_=args.type_,
                     file=args.file, since=args.since, until=args.until)
    max_score = results[0][1] if results else 0
    low_confidence = bool(args.q) and bool(results) and max_score < LOW_SCORE_THRESHOLD

    hits = []
    for rank, (doc_id, score) in enumerate(results, 1):
        d = idx["docs"][doc_id]
        hits.append({
            "rank": rank, "kind": d.get("kind"), "id": doc_id,
            "file": d.get("file"), "page": d.get("page"),
            "type": d.get("type"), "tags": d.get("tags"), "date": d.get("date"),
            "score": score,
            "low_confidence": bool(args.q) and score < LOW_SCORE_THRESHOLD,
            "snippet": " ".join((d.get("text") or "").split())[:100],
        })

    no_hit = None
    if not results:
        no_hit = diagnose(idx, args.q, args.tag, args.type_, args.file,
                          args.since, args.until)

    out = {
        "query": {"q": args.q, "tag": args.tag, "type": args.type_,
                  "file": args.file, "since": args.since, "until": args.until},
        "hit_count": len(hits),
        "max_score": max_score,
        "low_confidence": low_confidence,
        "results": hits,
        "no_hit": no_hit,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.log:
        seq = 0
        if os.path.isfile(args.log):
            with open(args.log, encoding="utf-8") as fh:
                seq = sum(1 for line in fh if line.strip())
        record = {"seq": seq + 1,
                  "args": out["query"],
                  "hits": len(hits),
                  "low_confidence": low_confidence}
        with open(args.log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
