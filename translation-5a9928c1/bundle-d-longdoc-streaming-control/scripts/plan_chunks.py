#!/usr/bin/env python3
"""plan_chunks.py — 语义切块：段落原子，永不切断段落。

用法: plan_chunks.py --source source.md --budget-tokens 1200 --out plan.json
单元: 空行/分页分段的语义块（标题/题注/公式独立单元，不切）。
块: 顺序打包单元，累计估计词元 ≤ budget；单单元超预算时独占一块并警告。
"""
import argparse, hashlib, json, re, sys

CAPTION = re.compile(r'^(Figure|Fig\.?|Table)\s*\d+', re.IGNORECASE)
HEADING = re.compile(r'^(?:\d+(\.\d+)*\s+)?(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|Conclusions|References?)\s*$')

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def est_tokens(text):
    return max(1, -(-len(text) // 4))

def units_of(text):
    units = []
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
        units.append({"kind": kind, "text": p})
    return units

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--budget-tokens", type=int, default=1200)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text = open(a.source, encoding="utf-8", errors="replace").read()
    units = units_of(text)
    chunks, cur, cur_tok = [], [], 0
    oversized = 0
    for i, u in enumerate(units, start=1):
        t = est_tokens(u["text"])
        uid = f"u{i:04d}"
        if cur and cur_tok + t > a.budget_tokens:
            chunks.append(cur); cur, cur_tok = [], 0
        cur.append({"unit_id": uid, "kind": u["kind"], "text": u["text"],
                    "sha256": sha(u["text"]), "est_tokens": t})
        cur_tok += t
        if t > a.budget_tokens:
            oversized += 1
    if cur:
        chunks.append(cur)
    plan = {"source_sha256": sha(text), "budget_tokens": a.budget_tokens,
            "n_units": len(units), "n_chunks": len(chunks),
            "oversized_single_unit_chunks": oversized,
            "chunks": [{"id": f"c{i:03d}", "units": c,
                        "est_tokens": sum(u["est_tokens"] for u in c),
                        "source_text": "\n\n".join(u["text"] for u in c)}
                       for i, c in enumerate(chunks, start=1)]}
    json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"plan: {len(units)} units -> {len(chunks)} chunks (budget={a.budget_tokens}, "
          f"oversized={oversized}) -> {a.out}")
    sys.exit(0 if not oversized else 1)

if __name__ == "__main__":
    main()
