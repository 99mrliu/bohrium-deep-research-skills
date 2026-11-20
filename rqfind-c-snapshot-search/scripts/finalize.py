#!/usr/bin/env python3
"""finalize.py — 汇总检索产物,按 case.json 的 output_contract 生成 result.json。

用法: python3 finalize.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output
"""
import argparse, json, os, time

def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default

def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        if isinstance(c.get("fields"), list):
            return [str(x) for x in c["fields"]]
        return sorted(c.keys())
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    case = load(args.case, {})
    report = load(os.path.join(args.work, "index_report.json"))
    audit = load(os.path.join(args.out, "rank_audit.json"), {})
    searches = []
    for name in sorted(os.listdir(args.out)):
        if name.startswith("search_") and name.endswith(".json"):
            s = load(os.path.join(args.out, name), {})
            if s:
                searches.append(s)
    uncertainty = []
    if report is None:
        uncertainty.append("index_report.json 缺失:索引未建立")
    if not searches:
        uncertainty.append("未找到任何 search_*.json:未执行检索或未保存结果")
    for v in audit.get("verdicts", []):
        uncertainty.append("检索 %s 快照 0 命中(snapshot_empty)" % v.get("label"))
    empty_terms = [s for s in searches if s.get("returned", 0) == 0]
    status = "blocked" if (report is None and not searches) else \
             ("partial" if (uncertainty or empty_terms) else "complete")
    cands = []
    seen = set()
    for s in searches:
        for r in s.get("results", []):
            key = r["rid"]
            if key in seen:
                continue
            seen.add(key)
            cands.append({**r, "from_query": s.get("label")})
    cands.sort(key=lambda r: -r["score"])
    base = {
        "case_id": case.get("case_id"),
        "summary": "在输入快照上建立本地倒排索引(文档 %s, 词表 %s),执行 %d 组检索,"
                   "合并去重后候选 %d 条(按得分排序);%d 组检索 0 命中已如实标记 snapshot_empty。"
                   % ((report or {}).get("records_indexed", "?"),
                      load(os.path.join(args.work, "docstats.json"), {}).get("vocab", "?"),
                      len(searches), len(cands), len(empty_terms)),
        "candidates": cands,
        "searches": [{"label": s.get("label"), "query": s.get("query"),
                      "query_zh": s.get("query_zh"), "facets": s.get("facets"),
                      "returned": s.get("returned"), "top": s.get("results", [])[:3]}
                     for s in searches],
        "rank_audit": audit.get("searches", []),
        "evidence_log": {"index": "index.json + docstats.json (postings 可复算)",
                         "searches": "search_*.json (逐条 matched_terms 与 origin 定位)",
                         "audit": "rank_audit.json"},
        "sources": [{"kind": "file", "path": p} for p in (report or {}).get("files_scanned", [])],
        "status": status,
        "uncertainty": uncertainty,
        "method": "rqfind-c-snapshot-search: index→expand→search→rankcheck→finalize",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    result = dict(base)
    for f in contract_fields(case):
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物,留空" % f)
    result["uncertainty"] = uncertainty
    json.dump(result, open(os.path.join(args.out, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "status": status, "candidates": len(cands),
                      "contract_fields": len(contract_fields(case))}, ensure_ascii=False))

if __name__ == "__main__":
    main()
