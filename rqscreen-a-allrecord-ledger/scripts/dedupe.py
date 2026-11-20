#!/usr/bin/env python3
"""dedupe.py — 对 records.jsonl 做精确+模糊去重,识别合成重复导出。

用法:
  python3 dedupe.py --work /app/work [--title-sim 0.85]

判定链(按序,先命中先归并):
  1. 非空 DOI 相同           -> duplicate(method=doi_exact)
  2. 归一化标题完全相同      -> duplicate(method=title_exact)
  3. 标题 token Jaccard>=阈值 -> duplicate(method=title_fuzzy, 记录相似度)
另: 记录自带 flags.synthetic_duplicate / duplicate_of / is_duplicate 标记时
在 outputs 中保留标记并注明其来源(输入夹具标记,非本脚本推断)。

输出:
  work/deduped_records.jsonl  保留的规范记录(canonical=true)
  work/duplicates.jsonl       每对被移除副本一行: kept_rid, dropped_rid, method, score
"""
import argparse, json, os, re, sys, unicodedata

def norm_title(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = re.sub(r"[^a-z0-9一-鿿 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def tokens(t):
    return set(w for w in norm_title(t).split() if len(w) >= 3)

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--title-sim", type=float, default=0.85)
    args = ap.parse_args()
    recs = [json.loads(l) for l in open(os.path.join(args.work, "records.jsonl"), encoding="utf-8")]
    kept, dups = [], []
    doi_idx, title_idx = {}, {}
    for r in recs:
        doi = (r.get("doi") or "").strip().lower()
        nt = norm_title(r.get("title", ""))
        dropped = None
        if doi and doi in doi_idx:
            dropped = (doi_idx[doi], "doi_exact", 1.0)
        elif nt and nt in title_idx:
            dropped = (title_idx[nt], "title_exact", 1.0)
        else:
            toks = tokens(r.get("title", ""))
            best, bscore = None, 0.0
            for k in kept:
                sc = jaccard(toks, k["_toks"])
                if sc >= args.title_sim and sc > bscore:
                    best, bscore = k, sc
            if best is not None:
                dropped = (best, "title_fuzzy", round(bscore, 3))
        if dropped:
            keep, method, score = dropped
            dups.append({"kept_rid": keep["rid"], "dropped_rid": r["rid"],
                         "method": method, "score": score,
                         "dropped_title": r.get("title", "")[:120],
                         "synthetic_flag": bool(r.get("flags", {}).get("synthetic_duplicate") or
                                                r.get("flags", {}).get("duplicate_of")),
                         "declared_duplicate_of": (r.get("flags") or {}).get("duplicate_of")})
        else:
            r["canonical"] = True
            r["_toks"] = tokens(r.get("title", ""))
            kept.append(r)
            if doi:
                doi_idx[doi] = r
            if nt:
                title_idx[nt] = r
    for k in kept:
        k.pop("_toks", None)
    with open(os.path.join(args.work, "deduped_records.jsonl"), "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(args.work, "duplicates.jsonl"), "w", encoding="utf-8") as f:
        for d in dups:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, "in": len(recs), "kept": len(kept),
                      "duplicates_removed": len(dups),
                      "synthetic_flagged": sum(1 for d in dups if d["synthetic_flag"])},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
