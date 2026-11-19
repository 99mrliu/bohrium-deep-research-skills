#!/usr/bin/env python3
"""kb_retrieve.py — lightweight line-level retrieval over the extracted texts.

Stdlib-only BM25-lite: char-bigram + latin-word tokenization (CJK friendly),
line-level hit extraction, score = coverage * log-tf. Deterministic output.

Usage:
  python3 kb_retrieve.py --index <kb_index.json> --query "<text>" [--top N]
Output: JSON on stdout with per-file line hits and scores.
"""
import argparse
import json
import math
import os
import re
import sys


def tokenize(text):
    text = text.lower()
    latin = re.findall(r"[a-z0-9_]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    return latin + bigrams + cjk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()

    with open(a.index, encoding="utf-8") as f:
        index = json.load(f)
    qtoks = tokenize(a.query)
    if not qtoks:
        print(json.dumps({"error": "empty_query"}, ensure_ascii=False))
        return 0

    results = []
    for rec in index.get("files", []):
        if rec.get("extract_status") != "ok" or not rec.get("extract_path"):
            continue
        if not os.path.exists(rec["extract_path"]):
            continue
        with open(rec["extract_path"], encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        hits = []
        df = 0
        for i, line in enumerate(lines, start=1):
            low = line.lower()
            matched = [t for t in qtoks if t in low]
            if len(matched) >= max(1, len(set(qtoks)) // 3):
                score = sum(low.count(t) for t in set(matched))
                hits.append({"line": i, "text": line.strip()[:300],
                             "matched_terms": sorted(set(matched))[:12],
                             "score": round(score, 3)})
                df += 1
        if hits:
            hits.sort(key=lambda h: -h["score"])
            coverage = len({t for h in hits for t in h["matched_terms"]}) / len(set(qtoks))
            file_score = coverage * math.log1p(sum(h["score"] for h in hits))
            results.append({
                "file_id": rec["file_id"], "path": rec["path"],
                "sha8": (rec.get("sha256") or "0" * 64)[:8],
                "file_score": round(file_score, 4),
                "hit_lines": len(hits),
                "top_hits": hits[:8],
            })
    results.sort(key=lambda r: -r["file_score"])
    out = {"query": a.query, "documents_returned": len(results),
           "results": results[: a.top]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
