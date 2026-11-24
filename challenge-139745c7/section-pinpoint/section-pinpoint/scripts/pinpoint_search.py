#!/usr/bin/env python3
"""Answer case questions at section granularity over anchors.jsonl.

Scoring: heading-term hits weigh 3, anchor-sentence hits 2, body hits 1;
file-name hits 1. A question with zero hits is reported as no_match with
the searched terms and corpus coverage -- never falls back to whole files.

Usage: pinpoint_search.py CASE_JSON ANCHORS_JSONL OUT_JSON
"""
import json
import os
import re
import sys

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{1,}|[一-鿿]+")
STOP = set("的了和是在有与及或其对这那中上个一为以于哪些哪个什么哪份")


def tokens(text):
    """Latin/number tokens plus CJK bigrams (stdlib has no segmenter)."""
    out = []
    for t in TOKEN.findall(text or ""):
        t = t.lower()
        if re.match(r"^[a-z0-9]", t):
            if t not in STOP and len(t) > 1:
                out.append(t)
        else:
            run = "".join(c for c in t if c not in STOP)
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


def find_questions(case):
    for key in ("searches", "questions", "queries", "tasks"):
        v = case.get(key)
        if isinstance(v, list) and v:
            return [q if isinstance(q, dict) else {"id": "q%d" % i, "text": str(q)}
                    for i, q in enumerate(v)]
        if isinstance(v, str):
            return [{"id": "q0", "text": v}]
    return []


def main():
    case_p, anchors_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    case = json.load(open(case_p, encoding="utf-8"))
    anchors = [json.loads(l) for l in open(anchors_p, encoding="utf-8")
               if l.strip()]
    questions = find_questions(case)
    out = []
    for q in questions:
        qtext = q.get("text", "")
        qt = tokens(qtext)
        hits = []
        for a in anchors:
            score = 0
            matched = []
            fields = [(a.get("heading") or "", 3),
                      (a.get("anchor_sentence") or "", 2),
                      (a.get("text") or "", 1),
                      (a.get("file") or "", 1)]
            for t in qt:
                w = 0
                for text, weight in fields:
                    if t in text.lower():
                        w = max(w, weight)
                if w:
                    score += w
                    matched.append(t)
            if score:
                hits.append({"score": score, "matched_terms": sorted(set(matched)),
                             "locator": a["locator"], "file": a["file"],
                             "page_physical": a.get("page_physical"),
                             "page_printed": a.get("page_printed"),
                             "heading": a.get("heading"),
                             "anchor_sentence": a.get("anchor_sentence"),
                             "quote": a["text"][:120],
                             "char_start": a["char_start"],
                             "char_end": a["char_end"]})
        hits.sort(key=lambda h: -h["score"])
        top = hits[0]["score"] if hits else 0
        best = [h for h in hits if h["score"] == top][:5]
        entry = {"question_id": q.get("id"), "question": qtext,
                 "searched_terms": qt,
                 "corpus_anchors": len(anchors)}
        if best:
            entry["status"] = "located"
            entry["hits"] = best
        else:
            entry["status"] = "no_match"
            entry["hits"] = []
            entry["note"] = ("全部 %d 个锚点上词项 %s 均无命中；未放宽条件，"
                             "未返回整篇文件" % (len(anchors), qt))
        out.append(entry)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump({"case_id": case.get("case_id") or case.get("id"),
                   "results": out}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_questions": len(questions),
                      "n_located": sum(1 for e in out if e["status"] == "located")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
