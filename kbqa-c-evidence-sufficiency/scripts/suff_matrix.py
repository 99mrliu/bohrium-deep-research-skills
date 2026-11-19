#!/usr/bin/env python3
"""suff_matrix.py — question-by-source coverage matrix with suggested grades.

Inputs: <out>/artifacts/suff_index.json, <work>/questions.json:
  {"questions": [{"id": "Q1", "text": "..."}]}
(questions.json may be produced by the model from case.json; if absent, the
script tries case.json questions/search_tasks fields directly.)

Per question x doc: token coverage, best excerpt lines, hit count, score.
Per question: suggested grade per the rubric thresholds:
  * mention of an inaccessible file's name in the question -> INACCESSIBLE
  * zero usable hits                          -> UNSUPPORTED
  * best coverage >= 0.5 with verified quote  -> SUPPORTED (pre-conflict)
  * otherwise                                 -> PARTIAL
Conflict override happens in suff_conflict.py; suff_verdict.py re-derives the
final grade from matrix + conflicts + quote verification.

Output: <out>/artifacts/coverage_matrix.json. Exit code always 0.
"""
import argparse
import json
import os
import re
import sys

STOP = set("的了吗呢吧啊哦嘛么和与及或在是有无不为这那之一其该各于对向被把让从到以及如果因为所以根据其中对于通过进行相关这些那些什么哪个怎么如何是否")


def tokenize(text):
    latin = re.findall(r"[a-z0-9_]+", text.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    toks = latin + bigrams + cjk
    return [t for t in toks if t not in STOP and len(t.strip()) > 0]


def load_questions(work, input_dir):
    qpath = os.path.join(work, "questions.json")
    if os.path.exists(qpath):
        return json.load(open(qpath, encoding="utf-8")).get("questions", [])
    for cand in (os.path.join(input_dir, "case.json"), "/input/case.json"):
        if os.path.exists(cand):
            case = json.load(open(cand, encoding="utf-8"))
            qs = case.get("questions") or case.get("search_tasks") or []
            out = []
            for i, q in enumerate(qs, start=1):
                if isinstance(q, str):
                    out.append({"id": "Q%d" % i, "text": q})
                elif isinstance(q, dict):
                    out.append({"id": q.get("id") or "Q%d" % i,
                                "text": q.get("text") or q.get("query") or ""})
            return out
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    art = os.path.join(a.out, "artifacts")
    index = json.load(open(os.path.join(art, "suff_index.json"), encoding="utf-8"))
    questions = load_questions(a.work, index.get("input_dir", "/input"))
    inaccessible = index.get("inaccessible", [])
    inacc_names = {d["name"].lower() for d in inaccessible}

    matrix = {"questions": [], "grade_rules":
              "INACCESSIBLE: question names an inaccessible file; "
              "UNSUPPORTED: zero usable hits; "
              "SUPPORTED: best coverage>=0.5 with verbatim quote; "
              "PARTIAL: otherwise"}
    for q in questions:
        qid, qtext = q.get("id"), q.get("text") or ""
        toks = tokenize(qtext)
        stem = set(toks)
        rows = []
        for doc in index["docs"]:
            if doc["extract_status"] != "ok" or not doc.get("extract_path"):
                continue
            try:
                with open(doc["extract_path"], encoding="utf-8",
                          errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            low_lines = [l.lower() for l in lines]
            hit_lines = []
            covered = set()
            for i, low in enumerate(low_lines):
                m = [t for t in stem if t in low]
                if m:
                    hit_lines.append({"line": i + 1, "text": lines[i].strip()[:240],
                                      "matched": sorted(m)[:10]})
                    covered.update(m)
            if not hit_lines:
                continue
            coverage = len(covered) / max(1, len(stem))
            score = coverage * (1.0 + 0.1 * len(hit_lines))
            hit_lines.sort(key=lambda h: -len(h["matched"]))
            rows.append({
                "doc_id": doc["doc_id"], "path": doc["path"],
                "sha8": (doc.get("sha256") or "")[:8],
                "coverage": round(coverage, 3),
                "score": round(score, 3),
                "hit_count": len(hit_lines),
                "best_excerpt": hit_lines[:5],
            })
        rows.sort(key=lambda r: -r["score"])
        mentions_inacc = any(nm in qtext.lower() for nm in inacc_names)
        best_cov = rows[0]["coverage"] if rows else 0.0
        if mentions_inacc and best_cov < 0.5:
            suggested = "INACCESSIBLE"
        elif not rows:
            suggested = "UNSUPPORTED"
        elif best_cov >= 0.5:
            suggested = "SUPPORTED"
        else:
            suggested = "PARTIAL"
        matrix["questions"].append({
            "question_id": qid, "question": qtext,
            "tokens": sorted(stem)[:30],
            "sources": rows,
            "source_count": len(rows),
            "best_coverage": best_cov,
            "inaccessible_mentioned": mentions_inacc,
            "suggested_grade": suggested,
        })

    with open(os.path.join(art, "coverage_matrix.json"), "w",
              encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=1)
    print("matrix questions=%d grades=%s" % (
        len(matrix["questions"]),
        {g: sum(1 for x in matrix["questions"] if x["suggested_grade"] == g)
         for g in ("SUPPORTED", "PARTIAL", "UNSUPPORTED", "INACCESSIBLE")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
