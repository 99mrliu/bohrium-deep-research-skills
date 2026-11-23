#!/usr/bin/env python3
"""retrieve_windows.py -- rank candidate evidence windows for a question.

Scoring is deliberately simple and auditable: term frequency of the query
terms (plus their lowercase forms) inside each chunk, ties broken by page.
Query terms come from --terms (pipe-separated alternatives, e.g.
"false positive|FPR|error rate"); with --auto the content words of the
question text are used.

Output: ranked list {anchor, page, score, matched_terms, excerpt} -- the
excerpt is a ±120 char window around the first match, for quick reading.
Retrieval recall is the agent's responsibility: if nothing relevant ranks
high, reformulate terms (synonyms, abbreviations, number formats) and rerun;
the searched-term list must be recorded in the verdict file.
"""
import argparse
import json
import re


def content_words(text):
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|\d+(?:\.\d+)?", text or "")
    stop = {"the", "and", "for", "with", "what", "which", "how", "does", "did",
            "are", "was", "were", "that", "this", "from", "into", "their"}
    return [w for w in words if w.lower() not in stop]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--question", default="")
    ap.add_argument("--terms", default="")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()
    with open(args.chunks, encoding="utf-8") as fh:
        chunks = json.load(fh).get("chunks", [])

    terms = [t.strip() for t in args.terms.split("|") if t.strip()]
    if args.auto or not terms:
        terms = sorted(set(terms) | set(content_words(args.question)))
    ranked = []
    for ch in chunks:
        text = ch["text"]
        score, matched = 0, []
        for t in terms:
            n = text.count(t) + text.lower().count(t.lower()) if t else 0
            if n:
                score += n
                matched.append(t)
        if score:
            first = min((text.find(m) for m in matched if text.find(m) >= 0),
                        default=0)
            lo = max(0, first - 120)
            ranked.append({"anchor": ch["anchor"], "page": ch["page"],
                           "score": score, "matched_terms": matched,
                           "excerpt": text[lo:first + 200]})
    ranked.sort(key=lambda r: (-r["score"], r["page"], r["anchor"]))
    print(json.dumps({"terms": terms, "hits": ranked[:args.limit]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
