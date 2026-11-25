#!/usr/bin/env python3
"""segment_docs.py — 简单语义分段：空行/分页分段 + 题注/标题独立成块，稳定 ID。"""
import argparse, hashlib, json, re

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

CAPTION = re.compile(r'^(Figure|Fig\.?|Table)\s*\d+', re.IGNORECASE)
HEADING = re.compile(r'^(?:\d+(\.\d+)*\s+)?(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|Conclusions|References?)\s*$')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text = open(a.source, encoding="utf-8", errors="replace").read()
    segs = []
    for chunk in re.split(r'\n\s*\n|\f', text):
        p = chunk.strip()
        if not p:
            continue
        lines = [l.strip() for l in p.split("\n") if l.strip()]
        if len(lines) == 1 and HEADING.match(lines[0]):
            kind = "heading"
        elif all(CAPTION.match(l) for l in lines):
            kind = "caption"
        else:
            kind = "paragraph"
        segs.append({"kind": kind, "text": p})
    out = []
    for i, s in enumerate(segs, start=1):
        out.append({"id": f"p{i:03d}", "kind": s["kind"], "text": s["text"],
                    "sha256": sha(s["text"])})
    json.dump({"segments": out}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{len(out)} segments -> {a.out}")

if __name__ == "__main__":
    main()
