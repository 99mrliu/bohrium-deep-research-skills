#!/usr/bin/env python3
"""rankcheck.py — 排序审计: 已知关键文献是否进 top-k; 空结果时给出诚实判定。

用法:
  python3 rankcheck.py --work /app/work --out /app/output \
      [--search-dir /app/output] [--keys "P1:doi1,P2:title fragment"]
      [--input-dir /input] [--top 5]

规则:
  - 若输入中存在署名清单(含 papers/refs 的 JSON), 自动用它做审计键;
  - 对每个 search_*.json, 计算清单文献在结果中的命中率@top;
  - 某检索返回 0 条时 verdict=snapshot_empty(如实说明快照无法回答该查询),
    不补造文献。
"""
import argparse, json, os, re, unicodedata

def norm_title(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"[^a-z0-9一-鿿]+", " ", t)

def find_refs(input_dir):
    if not input_dir or not os.path.isdir(input_dir):
        return None, None
    for root, _, names in os.walk(input_dir):
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            try:
                d = json.load(open(os.path.join(root, name), encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, dict):
                for k in ("papers", "refs", "references"):
                    if isinstance(d.get(k), list) and d[k] and isinstance(d[k][0], dict):
                        return os.path.join(root, name), d[k]
    return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--search-dir", default=None)
    ap.add_argument("--keys", default="")
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    sdir = args.search_dir or args.out
    searches = sorted(f for f in os.listdir(sdir)
                      if f.startswith("search_") and f.endswith(".json")) if os.path.isdir(sdir) else []
    stats = json.load(open(os.path.join(args.work, "docstats.json"), encoding="utf-8"))
    docs = stats["docs"]
    refs_path, refs = None, None
    if args.keys:
        refs = []
        for item in args.keys.split(","):
            rid, _, val = item.partition(":")
            refs.append({"ref_id": rid, "doi": val if val.startswith("10.") else "",
                         "title": "" if val.startswith("10.") else val})
        refs_path = "--keys"
    elif args.input_dir:
        refs_path, refs = find_refs(args.input_dir)
    # rid 反查键: doi -> rid, norm title -> rid
    doi_idx = {v.get("doi", "").lower(): k for k, v in docs.items() if v.get("doi")}
    title_idx = {norm_title(v.get("title", "")): k for k, v in docs.items()}
    report = {"searches": [], "audit": None, "verdicts": []}
    for sf in searches:
        s = json.load(open(os.path.join(sdir, sf), encoding="utf-8"))
        got = s.get("results", [])
        verdict = None
        if not got:
            verdict = {"label": s.get("label"),
                       "verdict": "snapshot_empty",
                       "note": "该查询在快照中 0 命中;如实说明快照无法覆盖,不补造文献"}
            report["verdicts"].append(verdict)
        top_rids = [r["rid"] for r in got[:args.top]]
        entry = {"file": sf, "label": s.get("label"), "returned": len(got),
                 "top_rids": top_rids, "verdict": (verdict or {}).get("verdict", "ok")}
        if refs:
            hits = []
            for p in refs:
                pdoi = (p.get("doi") or "").lower()
                ptitle = norm_title(p.get("title", ""))
                target = doi_idx.get(pdoi) if pdoi else None
                if target is None and ptitle:
                    target = title_idx.get(ptitle)
                if target is None:
                    # 标题片段匹配
                    for k, v in docs.items():
                        if ptitle and ptitle in norm_title(v.get("title", "")):
                            target = k
                            break
                hits.append({"ref": p.get("ref_id") or (p.get("title", "")[:40]),
                             "in_top": target in top_rids, "rid": target})
            entry["attributed_hits@top"] = hits
            entry["hit_rate@top"] = round(sum(1 for h in hits if h["in_top"]) / max(len(hits), 1), 3)
        report["searches"].append(entry)
    json.dump(report, open(os.path.join(args.out, "rank_audit.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "searches": len(report["searches"]),
                      "empty_verdicts": len(report["verdicts"])}, ensure_ascii=False))

if __name__ == "__main__":
    main()
