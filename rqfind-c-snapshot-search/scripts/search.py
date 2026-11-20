#!/usr/bin/env python3
"""search.py — 在本地索引上执行布尔+加权检索, 输出逐条可解释的相关性依据。

用法:
  python3 search.py --work /app/work --query "perovskite passivation" \
      [--query-zh "钙钛矿 钝化"] [--year-from 2022] [--year-to 2025] \
      [--exclude-type review] [--top 10] [--out /app/output]

查询语法: 空格分隔, 默认 OR; 前缀 +: 必须命中; 前缀 -: 排除; 引号短语按整体匹配。
打分: sum(term 在 doc 的字段加权) * log(1 + N/df); 分面(年份/类型)为硬过滤。
输出: 每条候选含 score, matched_terms(按字段), facet_check, 原文定位(origin_file!row)。
"""
import argparse, json, math, os, re, unicodedata
from index import tokenize, FIELD_W  # 复用本分词,保持索引/查询一致

def load(work):
    index = json.load(open(os.path.join(work, "index.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(work, "docstats.json"), encoding="utf-8"))
    return index, stats

def parse_query(q):
    must, should, neg, phrases = [], [], [], []
    for tok in re.findall(r'"[^"]+"|[+\-]?\S+', q):
        if tok.startswith('"') and tok.endswith('"'):
            phrases.append(tok[1:-1].lower())
        elif tok.startswith("+"):
            must.append(tok[1:].lower())
        elif tok.startswith("-"):
            neg.append(tok[1:].lower())
        else:
            should.append(tok.lower())
    return must, should, neg, phrases

def search(work, query, query_zh, y_from, y_to, excl_types, top):
    index, stats = load(work)
    docs = stats["docs"]
    N = max(stats["n_docs"], 1)
    must, should, neg, phrases = parse_query(query)
    zh_terms = [t for t in re.split(r"\s+", query_zh or "") if t]
    def terms_of(w):
        return tokenize(w)
    must_t, should_t, neg_t = [], [], []
    for w in must:
        must_t += terms_of(w) or [w]
    for w in should:
        should_t += terms_of(w) or [w]
    for w in neg:
        neg_t += terms_of(w) or [w]
    for p in phrases:
        should_t += terms_of(p)
    cand = None
    if must_t:
        cand = set.intersection(*[set(index.get(t, {})) for t in must_t]) if all(t in index for t in must_t) else set()
    pool = set()
    for t in set(must_t + should_t + neg_t):
        pool |= set(index.get(t, {}))
    if zh_terms:
        pool |= set().union(*[set(index.get(t, {})) for t in zh_terms]) if any(t in index for t in zh_terms) else set()
    if cand is None:
        cand = pool
    results = []
    for rid in cand:
        doc = docs.get(rid)
        if not doc:
            continue
        if neg_t and any(t in index and rid in index[t] for t in neg_t):
            continue
        if y_from and doc.get("year") and doc["year"] < y_from:
            continue
        if y_to and doc.get("year") and doc["year"] > y_to:
            continue
        if excl_types and (doc.get("type") or "") in excl_types:
            continue
        if must_t and not all(t in index and rid in index[t] for t in must_t):
            continue
        score, matched = 0.0, {}
        for t in set(must_t + should_t):
            if t in index and rid in index[t]:
                wsum = sum(f[1] for f in index[t][rid])
                score += wsum * math.log(1 + N / max(stats["df"].get(t, 1), 1))
                for field, w in index[t][rid]:
                    matched.setdefault(t, {}).setdefault(field, 0)
                    matched[t][field] += w
        for t in zh_terms:
            if t in index and rid in index[t]:
                score += sum(f[1] for f in index[t][rid]) * 2.0
                matched.setdefault(t, {})["_zh"] = True
        if score <= 0:
            continue
        flags = doc.get("flags") or {}
        results.append({"rid": rid, "score": round(score, 3),
                        "title": doc.get("title", ""), "year": doc.get("year"),
                        "venue": doc.get("venue", ""), "doi": doc.get("doi", ""),
                        "type": doc.get("type", ""),
                        "matched_terms": {t: {f: round(v, 2) for f, v in fs.items()}
                                          for t, fs in sorted(matched.items())},
                        "facet_check": {"year_ok": True,
                                        "type_ok": (doc.get("type") or "") not in excl_types},
                        "flag_notes": [k for k in ("conflicting_opinion", "synthetic_duplicate") if flags.get(k)],
                        "origin": "%s!%s" % (doc.get("origin_file", ""), doc.get("origin_row", ""))})
    results.sort(key=lambda r: -r["score"])
    return results[:top], {"must": must, "should": should, "neg": neg,
                           "expanded_terms": {"must": must_t, "should": should_t},
                           "zh_terms": zh_terms, "n_pool": len(pool)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--query-zh", default="")
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--year-to", type=int, default=None)
    ap.add_argument("--exclude-type", default="")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--label", default="Q1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    results, meta = search(args.work, args.query, args.query_zh,
                           args.year_from, args.year_to,
                           [t.strip().lower() for t in args.exclude_type.split(",") if t.strip()],
                           args.top)
    payload = {"label": args.label, "query": args.query, "query_zh": args.query_zh,
               "facets": {"year_from": args.year_from, "year_to": args.year_to,
                          "exclude_type": args.exclude_type},
               "query_expansion": meta["expanded_terms"], "zh_terms": meta["zh_terms"],
               "pool_size": meta["n_pool"], "returned": len(results), "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "search_%s.json" % args.label)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(json.dumps({"ok": True, "label": args.label, "returned": len(results),
                          "path": path}, ensure_ascii=False))
    else:
        print(text)

if __name__ == "__main__":
    main()
