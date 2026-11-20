#!/usr/bin/env python3
"""screen.py — 全记录逐条筛查台账。每条记录给出 include/exclude/uncertain 处置与依据。

用法:
  python3 screen.py --work /app/work --criteria /app/work/criteria.json \
      [--overrides /app/work/overrides.json] --out /app/output

criteria.json(由 Agent 依据 task.md/research_question 编写,示例见 resources/criteria_template.md):
{
  "year_from": 2022, "year_to": 2025,
  "include_terms": ["perovskite", "passivation", "ammonium"],
  "min_term_hits": 1,
  "exclude_terms": ["photocatalysis"],
  "exclude_types": ["review", "perspective", "editorial"],
  "require_device_data": false,
  "subquestion_map": {"SQ-1 界面钝化": ["interface", "interfacial"],
                      "SQ-2 晶界钝化": ["grain boundary", "grain-boundary"]}
}

overrides.json(可选;Agent 对规则无法判定的记录逐条写判断,必须给依据):
  [{"rid":"s09-001","disposition":"include","reason":"...","sq":"SQ-1"}]

规则(全部可复算):
  1. year 缺失 -> 不因此排除,记 reason: year_unknown
  2. year 出窗 -> exclude(year_out_of_range)
  3. type 命中 exclude_types -> exclude(type_excluded)
  4. exclude_terms 命中 title/abstract/keywords -> exclude(term_excluded)
  5. include_terms 命中数 < min_term_hits -> exclude(no_inclusion_term)
  6. 否则 include,并给出命中词清单与命中文本片段;命中了 subquestion_map
     的条目则标注 sq_hits(可多 SQ)
输出: output/ledger.jsonl(逐条台账), output/screening_summary.json(PRISMA 式计数),
      output/candidates.json(include 集合,按命中分排序)
"""
import argparse, json, os, re

def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def hay(r):
    return " ".join([r.get("title", ""), r.get("abstract", ""), r.get("keywords", "")]).lower()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--criteria", required=True)
    ap.add_argument("--overrides", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    crit = json.load(open(args.criteria, encoding="utf-8"))
    recs = load_jsonl(os.path.join(args.work, "deduped_records.jsonl"))
    inc_terms = [t.lower() for t in crit.get("include_terms", [])]
    exc_terms = [t.lower() for t in crit.get("exclude_terms", [])]
    exc_types = [t.lower() for t in crit.get("exclude_types", [])]
    min_hits = crit.get("min_term_hits", 1)
    y_from, y_to = crit.get("year_from"), crit.get("year_to")
    sq_map = crit.get("subquestion_map", {})
    overrides = {}
    if args.overrides and os.path.exists(args.overrides):
        for o in json.load(open(args.overrides, encoding="utf-8")):
            overrides[o["rid"]] = o
    ledger, cands = [], []
    counts = {"screened": 0, "included": 0, "excluded": 0, "uncertain": 0,
              "exclude_reasons": {}, "overrides_applied": 0}
    for r in recs:
        counts["screened"] += 1
        h = hay(r)
        reasons, hits, dispo = [], [], None
        # 1-2 年份
        if r.get("year") is None:
            reasons.append("year_unknown")
        elif (y_from and r["year"] < y_from) or (y_to and r["year"] > y_to):
            dispo = "exclude"; reasons.append("year_out_of_range:%s" % r["year"])
        # 3 类型
        rtype = (r.get("type") or "").lower()
        if dispo is None and rtype and rtype in exc_types:
            dispo = "exclude"; reasons.append("type_excluded:%s" % rtype)
        # 4 排除词
        exc_hit = [t for t in exc_terms if t in h]
        if dispo is None and exc_hit:
            dispo = "exclude"; reasons.append("term_excluded:%s" % ",".join(exc_hit))
        # 5-6 纳入词
        hits = [t for t in inc_terms if t in h]
        if dispo is None:
            if len(hits) >= min_hits:
                dispo = "include"
            elif hits:
                dispo = "uncertain"; reasons.append("below_min_hits:%d<%d" % (len(hits), min_hits))
            else:
                dispo = "exclude"; reasons.append("no_inclusion_term")
        sq_hits = [sq for sq, terms in sq_map.items()
                   if any(t.lower() in h for t in terms)]
        # 冲突/重复夹具标记:不改变处置,但进入台账供复核
        flags = r.get("flags") or {}
        flag_note = [k for k in ("conflicting_opinion", "synthetic_duplicate") if flags.get(k)]
        entry = {"rid": r["rid"], "disposition": dispo, "reason_codes": reasons,
                 "term_hits": hits, "sq_hits": sq_hits, "flag_notes": flag_note,
                 "title": r.get("title", ""), "year": r.get("year"), "venue": r.get("venue", ""),
                 "doi": r.get("doi", ""), "type": r.get("type", ""),
                 "origin_file": r.get("origin_file", ""), "origin_row": r.get("origin_row"),
                 "evidence_snippet": (r.get("abstract", "") or r.get("title", ""))[:220]}
        if r["rid"] in overrides:
            ov = overrides[r["rid"]]
            entry["disposition_before_override"] = dispo
            entry["disposition"] = ov["disposition"]
            entry["override_reason"] = ov.get("reason", "")
            if ov.get("sq"):
                entry["sq_hits"] = list({*entry["sq_hits"], ov["sq"]})
            counts["overrides_applied"] += 1
        ledger.append(entry)
        if entry["disposition"] == "include":
            cands.append(entry)
        else:
            for rc in reasons:
                key = rc.split(":")[0]
                counts["exclude_reasons"][key] = counts["exclude_reasons"].get(key, 0) + 1
    counts["included"] = sum(1 for e in ledger if e["disposition"] == "include")
    counts["excluded"] = sum(1 for e in ledger if e["disposition"] == "exclude")
    counts["uncertain"] = sum(1 for e in ledger if e["disposition"] == "uncertain")
    cands.sort(key=lambda e: -len(e["term_hits"]))
    with open(os.path.join(args.out, "ledger.jsonl"), "w", encoding="utf-8") as f:
        for e in ledger:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=2)
    summary = {"criteria": crit, "counts": counts,
               "prisma": {"records_identified": None,  # 由 ingest 总数填
                          "duplicates_removed": None,
                          "records_screened": counts["screened"],
                          "records_excluded": counts["excluded"],
                          "records_included": counts["included"],
                          "records_uncertain": counts["uncertain"]}}
    with open(os.path.join(args.out, "screening_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, **counts}, ensure_ascii=False))

if __name__ == "__main__":
    main()
