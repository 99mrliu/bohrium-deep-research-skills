#!/usr/bin/env python3
"""qa_retrieve.py — 问答生产线检索步：BM25-lite 行级命中 + 检索日志（含阴性结果）。

对 kb_index.json 的行号化抽取文本做确定性检索。每次查询（含未命中）都追加到
work/retrieval_log.jsonl —— "搜过什么、命中几行、在哪"全程留痕；零命中查询
同样记录，这是"库中无依据"结论的可复核证据，禁止只报命中不报空。

退出码恒 0。
"""
import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter

SPLIT = re.compile(r"[\s，。；：、（）()\[\]【】\-_/\\.,;:!?\"'<>|#*+=~`@$%^&]+")


def tokenize(text):
    toks = [t for t in SPLIT.split(text.lower()) if t]
    # CJK 单字 bigram，提升中文短词命中
    cjk = re.findall(r"[一-鿿]+", text)
    for seg in cjk:
        if len(seg) == 1:
            toks.append(seg)
        else:
            toks.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return toks


def load_lines(work, entry):
    if not entry.get("extracted"):
        return []
    p = os.path.join(work, entry["extracted"])
    try:
        with open(p, encoding="utf-8") as f:
            raw = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in raw:
        m = re.match(r"^L(\d+): (.*)$", line)
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--query", required=True)
    ap.add_argument("--question-id", default="adhoc")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    with open(os.path.join(a.work, "kb_index.json"), encoding="utf-8") as f:
        index = json.load(f)

    docs = []  # (file_id, sha8, line_no, text, tokens)
    for e in index["files"]:
        if e["text_status"] != "ok":
            continue
        for ln, txt in load_lines(a.work, e):
            docs.append((e["file_id"], (e["sha256"] or "")[:8], ln, txt, tokenize(txt)))
    df = Counter()
    for *_, toks in docs:
        for t in set(toks):
            df[t] += 1
    N = max(len(docs), 1)
    qtoks = tokenize(a.query)
    avgdl = sum(len(d[4]) for d in docs) / N if N else 1
    scored = []
    for fid, sha8, ln, txt, toks in docs:
        if not toks:
            continue
        tf = Counter(toks)
        score = 0.0
        for t in qtoks:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * (tf[t] * 2.2) / (tf[t] + 1.2 * (0.25 + 0.75 * len(toks) / max(avgdl, 1)))
        if score > 0:
            scored.append({"file_id": fid, "sha8": sha8, "line": ln,
                           "text": txt, "score": round(score, 3)})
    scored.sort(key=lambda h: (-h["score"], h["file_id"], h["line"]))
    hits = scored[: a.top]

    # 为每个命中附上下文窗口（前后各 1 行），便于直接截取逐字引文
    by_file = {}
    for e in index["files"]:
        if e["text_status"] == "ok":
            by_file[e["file_id"]] = dict(load_lines(a.work, e))
    for h in hits:
        lines = by_file.get(h["file_id"], {})
        h["context"] = [{"line": k, "text": lines[k]} for k in
                        (h["line"] - 1, h["line"], h["line"] + 1) if k in lines]

    log_entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "question_id": a.question_id, "query": a.query,
                 "n_hits": len(hits), "negative": len(hits) == 0,
                 "top": [{"file_id": h["file_id"], "line": h["line"], "score": h["score"]}
                         for h in hits]}
    with open(os.path.join(a.work, "retrieval_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(json.dumps({"question_id": a.question_id, "query": a.query,
                      "n_hits": len(hits), "hits": hits}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
