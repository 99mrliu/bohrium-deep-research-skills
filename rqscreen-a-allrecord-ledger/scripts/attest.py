#!/usr/bin/env python3
"""attest.py — 把候选/全记录与"真实署名文献清单"逐篇核验(归属审计)。

用法:
  python3 attest.py --work /app/work --out /app/output [--refs /input/reference_papers.json]
  若不指定 --refs,脚本自动在输入目录中寻找含 papers/refs/references 列表的 JSON 文件;
  找不到则如实输出 no_reference_list,绝不凭空构造清单。

每篇清单文献给出:
  status: matched | ambiguous | missing
  match:  rid, method(doi_exact/title_fuzzy), title_sim, 元数据一致性核对
          (year/venue/authors 是否与清单一致;不一致逐项列出)
  conflicting_records: 台账中 flags 标注与该篇冲突的记录(如有)

输出: output/attribution.json
"""
import argparse, json, os, re, unicodedata

def norm_title(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = re.sub(r"[^a-z0-9一-鿿 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def tokens(t):
    return set(w for w in norm_title(t).split() if len(w) >= 3)

def jaccard(a, b):
    return len(a & b) / len(a | b) if (a and b) else 0.0

def find_refs(input_dir):
    for root, _, names in os.walk(input_dir):
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            try:
                d = json.load(open(os.path.join(root, name), encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, dict):
                for k in ("papers", "refs", "references", "attributed_papers"):
                    if isinstance(d.get(k), list) and d[k] and isinstance(d[k][0], dict):
                        return os.path.join(root, name), d[k]
    return None, None

def norm_venue(v):
    return re.sub(r"[^a-z0-9]+", "", (v or "").lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--refs", default=None)
    ap.add_argument("--input-dir", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    refs_path = args.refs
    refs = None
    if refs_path:
        d = json.load(open(refs_path, encoding="utf-8"))
        refs = d.get("papers") or d.get("refs") or (d if isinstance(d, list) else None)
    elif args.input_dir:
        refs_path, refs = find_refs(args.input_dir)
    result = {"reference_list_source": refs_path, "total": 0,
              "matched": 0, "ambiguous": 0, "missing": 0, "papers": []}
    if not refs:
        result["status"] = "no_reference_list"
        result["note"] = "未在输入中找到署名文献清单,跳过归属核验。"
        json.dump(result, open(os.path.join(args.out, "attribution.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(json.dumps({"ok": True, "status": "no_reference_list"}, ensure_ascii=False))
        return
    recs = [json.loads(l) for l in open(os.path.join(args.work, "deduped_records.jsonl"), encoding="utf-8")]
    result["total"] = len(refs)
    for p in refs:
        pdoi = (p.get("doi") or "").strip().lower()
        ptoks = tokens(p.get("title", ""))
        best, bscore, method = None, 0.0, None
        for r in recs:
            if pdoi and (r.get("doi") or "").strip().lower() == pdoi:
                best, bscore, method = r, 1.0, "doi_exact"
                break
            sc = jaccard(ptoks, tokens(r.get("title", "")))
            if sc > bscore:
                best, bscore, method = r, sc, "title_fuzzy"
        entry = {"ref_id": p.get("ref_id") or p.get("id"), "title": p.get("title", "")}
        if best is None or bscore < 0.6:
            entry["status"] = "missing"
            result["missing"] += 1
        else:
            near = [r for r in recs if r is not best and
                    jaccard(ptoks, tokens(r.get("title", ""))) >= 0.6]
            meta_diff = []
            if p.get("year") and best.get("year") and int(p["year"]) != int(best["year"]):
                meta_diff.append("year: refs=%s record=%s" % (p["year"], best["year"]))
            if p.get("venue") and best.get("venue") and \
               norm_venue(p["venue"]) != norm_venue(best["venue"]):
                meta_diff.append("venue: refs=%s record=%s" % (p.get("venue"), best.get("venue")))
            pauth = (p.get("authors") or "").split(";")[0].split(",")[0].strip().lower()
            rauth = (best.get("authors") or "").lower()
            if pauth and pauth not in rauth:
                meta_diff.append("first_author: refs=%s record=%s" % (p.get("authors", "")[:40], best.get("authors", "")[:40]))
            conflicts = [r["rid"] for r in recs
                         if (r.get("flags") or {}).get("conflicting_opinion")
                         and (r.get("flags", {}).get("conflicts_with") in (best["rid"], None)
                              and jaccard(ptoks, tokens(r.get("title", ""))) > 0.2)]
            entry.update({
                "status": "ambiguous" if near else "matched",
                "match": {"rid": best["rid"], "method": method, "title_sim": round(bscore, 3),
                          "record_title": best.get("title", "")[:120],
                          "metadata_diff": meta_diff},
                "ambiguous_with": [r["rid"] for r in near],
                "conflicting_records": conflicts,
                "conflicting_records_note": "输入夹具中标注的冲突意见记录,仅原样登记,不作裁决" if conflicts else None})
            result["matched" if not near else "ambiguous"] += 1
        result["papers"].append(entry)
    json.dump(result, open(os.path.join(args.out, "attribution.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "total": result["total"], "matched": result["matched"],
                      "ambiguous": result["ambiguous"], "missing": result["missing"]},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
