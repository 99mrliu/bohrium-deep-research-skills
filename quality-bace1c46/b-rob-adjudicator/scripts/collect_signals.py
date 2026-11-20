#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_signals.py -- candidate-sentence recall for signaling questions.

For each document, scans pages/<doc_id>.jsonl with the keyword windows of
every selected signaling question (domain_specs.py) and recalls candidate
sentences with page anchors and pre-assigned channel tags (P = affirmative
evidence hunt, N = omission/contradiction hunt). The model only judges the
recalled candidates; it never roams the full text.

Output: signals/<doc_id>.json
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu
import domain_specs as ds

SCRIPT_VERSION = "collect_signals/1.0"
MAX_CANDIDATES_PER_QUESTION = 8
WINDOW_CHARS = 180  # context window around each keyword hit

# Extra generic channel-N (omission-hunt) markers scanned everywhere.
N_GENERIC = ["not reported", "not specified", "unclear", "not described",
             "not disclosed", "missing", "unavailable", "not stated",
             "no information", "未报告", "未说明", "未披露", "缺失", "不详"]


def split_sentences(text):
    """Lightweight sentence splitter that keeps offsets."""
    parts = re.split(r"(?<=[.!?。！？;；])\s+|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def paragraph_index(pages, page_no, char_pos):
    """Approximate the paragraph index on a page for an anchor."""
    text = pages[page_no - 1].get("text", "")
    prefix = text[:char_pos]
    return prefix.count("\n\n") + 1


def recall(pages, keywords, channel, max_hits=MAX_CANDIDATES_PER_QUESTION):
    """Recall candidate snippets with anchors for the given keywords."""
    out = []
    seen = set()
    for pno, prow in enumerate(pages, start=1):
        text = prow.get("text", "")
        low = text.lower()
        for kw in keywords:
            start = 0
            kwl = kw.lower()
            while len(out) < max_hits:
                idx = low.find(kwl, start)
                if idx < 0:
                    break
                start = idx + max(1, len(kwl))
                lo = max(0, idx - WINDOW_CHARS)
                hi = min(len(text), idx + len(kw) + WINDOW_CHARS)
                snippet = text[lo:hi].strip()
                key = cu.normalize(snippet)[:120]
                if key in seen:
                    continue
                seen.add(key)
                para = paragraph_index(pages, pno, lo)
                out.append({
                    "channel": channel,
                    "locator": "p%d.\u00b6%d" % (pno, para),
                    "page": pno,
                    "hit_keyword": kw,
                    "snippet": re.sub(r"\s+", " ", snippet),
                })
            if len(out) >= max_hits:
                break
        if len(out) >= max_hits:
            break
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Recall candidate sentences per signaling question")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    plan = cu.read_json(os.path.join(args.workdir, "domain_plan.json"),
                        default={"documents": []})
    sig_dir = os.path.join(args.workdir, "signals")
    os.makedirs(sig_dir, exist_ok=True)

    summary = []
    for entry in plan.get("documents", []):
        doc_id = entry.get("doc_id")
        if entry.get("grade") == "failed":
            continue
        pages = cu.load_pages(args.workdir, doc_id)
        doc_domains = ds.domains_for_type(entry.get("type", "other"))
        payload = {"doc_id": doc_id, "type": entry.get("type"),
                   "grade": entry.get("grade"),
                   "version": SCRIPT_VERSION, "domains": []}
        for d in doc_domains:
            drec = {"id": d["id"], "name": d["name"], "core": d["core"],
                    "questions": []}
            for q in d["questions"]:
                p_hits = recall(pages, q["p_keywords"], "P")
                n_hits = recall(pages,
                                q["n_keywords"] + N_GENERIC, "N")
                drec["questions"].append({
                    "id": q["id"], "text": q["text"],
                    "positive_looks_like": q["positive"],
                    "negative_looks_like": q["negative"],
                    "insufficient_when": q["insufficient_when"],
                    "candidates_p": p_hits,
                    "candidates_n": n_hits,
                })
            payload["domains"].append(drec)
        out_path = os.path.join(sig_dir, doc_id + ".json")
        cu.write_json(out_path, payload)
        n_cand = sum(len(q["candidates_p"]) + len(q["candidates_n"])
                     for d in payload["domains"] for q in d["questions"])
        summary.append({"doc_id": doc_id, "candidates": n_cand})
    print({"signals": summary})


if __name__ == "__main__":
    main()
