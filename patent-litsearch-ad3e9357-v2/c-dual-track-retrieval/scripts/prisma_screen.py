#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prisma_screen.py — PRISMA 风格筛选：screen（应用人工决策）与 report（重算计数）。

仅依赖 python3 标准库。退出码：0 成功；2 决策缺失/非法；3 自报计数与重算不一致。

纪律：
  * 筛选单位 = corpus_search 去重后的 record（doc_id 即 dedup_key）；
    decisions.json 每条为 {doc_id, decision: include|exclude, reason}；
    任何 record 缺 decision → 退出码 2 并逐一列出；exclude 必须给 reason。
  * prisma.json 的全部计数由脚本依据 decisions + hits 重新计算，绝不采信调用方数字。
  * report 支持 --claim counts.json（自报计数）；与重算结果不一致 → 退出码 3。
  * 产出遗漏说明模板：未覆盖概念块、零命中词项、按理由汇总的排除分布。
"""
import argparse
import json
import sys

CLAIM_KEYS = ["raw_hits", "duplicates_removed", "records_screened",
              "included", "excluded"]


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def recompute(hits_data, decisions_map):
    """依据 hits + decisions 重算 PRISMA 各阶段计数（唯一可信来源）。"""
    records = hits_data.get("records", [])
    raw_hits = len(hits_data.get("hits", []))
    included, excluded = [], []
    for rec in records:
        d = decisions_map[rec["doc_id"]]
        entry = {"doc_id": rec["doc_id"], "track": rec["track"],
                 "members": rec["members"], "decision": d["decision"],
                 "reason": d.get("reason", "")}
        if d["decision"] == "include":
            included.append(entry)
        else:
            excluded.append(entry)
    by_reason = {}
    for e in excluded:
        by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    patent_raw = sum(1 for h in hits_data.get("hits", []) if h["track"] == "patent")
    npl_raw = raw_hits - patent_raw
    return {
        "identification": {
            "patent_hits": patent_raw,
            "npl_hits": npl_raw,
            "raw_hits": raw_hits,
            "duplicates_removed": raw_hits - len(records),
            "records_after_dedup": len(records),
        },
        "screening": {
            "records_screened": len(records),
            "excluded": len(excluded),
            "excluded_by_reason": by_reason,
            "query_excluded": len(hits_data.get("excluded_docs", [])),
            "no_match_scanned": len(hits_data.get("no_match_docs", [])),
        },
        "included": {"total": len(included), "records": included},
    }


def build_omissions_note(hits_data, counts):
    meta = hits_data.get("meta", {})
    lines = [
        "遗漏说明（模板，请结合案例实际改写后填入 result.omissions_note）：",
        "1. 召回范围：扫描 %d 个文件；原始命中 %d 条，去重后 %d 条进入筛选。"
        % (meta.get("files_scanned", 0), counts["identification"]["raw_hits"],
           counts["identification"]["records_after_dedup"]),
        "2. 未覆盖概念块：%s。"
        % ("、".join(meta.get("uncovered_blocks", [])) or "无（所有块至少命中一篇）"),
        "3. 零命中词项：%s。"
        % ("、".join(meta.get("zero_hit_terms", [])) or "无"),
        "4. 查询层排除（命中排除词）%d 篇；扫描但未覆盖全部概念块 %d 篇。"
        % (counts["screening"]["query_excluded"],
           counts["screening"]["no_match_scanned"]),
        "5. 筛选层排除 %d 条，按理由分布：%s。"
        % (counts["screening"]["excluded"],
           "；".join("%s×%d" % (r, n)
                     for r, n in counts["screening"]["excluded_by_reason"].items())
           or "无"),
        "6. 残余风险：字面词组匹配可能遗漏未列入词表的同义表述；"
        "如需扩充召回，请在 spec 中增补 variant 词项后重跑并记录变更。",
    ]
    return "\n".join(lines)


def cmd_screen(args):
    hits_data = _load(args.hits)
    raw_decisions = _load(args.decisions)
    if not isinstance(raw_decisions, list):
        print("FAIL: decisions.json 必须是数组", file=sys.stderr)
        return 2
    decisions_map, problems = {}, []
    for i, d in enumerate(raw_decisions):
        if not isinstance(d, dict) or not d.get("doc_id"):
            problems.append("decisions[%d] 缺少 doc_id" % i)
            continue
        if d.get("decision") not in ("include", "exclude"):
            problems.append("%s: decision 须为 include|exclude" % d["doc_id"])
            continue
        if d["decision"] == "exclude" and not str(d.get("reason", "")).strip():
            problems.append("%s: exclude 必须给出 reason" % d["doc_id"])
            continue
        decisions_map[d["doc_id"]] = d
    records = hits_data.get("records", [])
    missing = [r["doc_id"] for r in records if r["doc_id"] not in decisions_map]
    orphan = [k for k in decisions_map
              if k not in {r["doc_id"] for r in records}]
    if missing or problems:
        for m in missing:
            print("MISSING decision: %s" % m, file=sys.stderr)
        for p in problems:
            print("INVALID: %s" % p, file=sys.stderr)
        print("screen 中止：%d 条记录缺决策，%d 条决策非法"
              % (len(missing), len(problems)), file=sys.stderr)
        return 2
    for o in orphan:
        print("WARN: 决策 %s 不对应任何去重后记录，已忽略" % o, file=sys.stderr)

    counts = recompute(hits_data, decisions_map)
    screened_records = []
    for rec in records:
        d = decisions_map[rec["doc_id"]]
        screened_records.append({
            "doc_id": rec["doc_id"], "track": rec["track"],
            "members": rec["members"],
            "decision": d["decision"], "reason": d.get("reason", ""),
            "matched_terms": rec["matched_terms"],
            "locators": rec["locators"],
        })
    out = {
        "meta": hits_data.get("meta", {}),
        "records": screened_records,
        "no_match_docs": hits_data.get("no_match_docs", []),
        "excluded_docs": hits_data.get("excluded_docs", []),
        "counts": counts,
        "omissions_note_template": build_omissions_note(hits_data, counts),
    }
    _dump(args.out, out)
    print("screen: %d 条记录（include %d / exclude %d）→ %s"
          % (len(records), counts["included"]["total"],
             counts["screening"]["excluded"], args.out))
    return 0


def cmd_report(args):
    screened = _load(args.screened)
    decisions_map = {r["doc_id"]: {"decision": r["decision"],
                                   "reason": r.get("reason", "")}
                     for r in screened.get("records", [])}
    # 以 screened.json 内的记录重建 hits 视图并全部重算
    hits_view = {
        "meta": screened.get("meta", {}),
        "hits": [{"doc_id": m, "track": r["track"]}
                 for r in screened.get("records", []) for m in r["members"]],
        "records": screened.get("records", []),
        "no_match_docs": screened.get("no_match_docs", []),
        "excluded_docs": screened.get("excluded_docs", []),
    }
    counts = recompute(hits_view, decisions_map)
    prisma = {
        "prisma": counts,
        "omissions_note_template": screened.get("omissions_note_template")
        or build_omissions_note(hits_view, counts),
        "counts_provenance": "全部计数由 prisma_screen.py 依据 decisions+records 重算，"
                             "未采信任何调用方数字。",
    }
    if args.claim:
        claim = _load(args.claim)
        flat = {
            "raw_hits": counts["identification"]["raw_hits"],
            "duplicates_removed": counts["identification"]["duplicates_removed"],
            "records_screened": counts["screening"]["records_screened"],
            "included": counts["included"]["total"],
            "excluded": counts["screening"]["excluded"],
        }
        mismatches = []
        for k in CLAIM_KEYS:
            if k in claim and claim[k] != flat[k]:
                mismatches.append("%s: 自报 %r ≠ 重算 %r" % (k, claim[k], flat[k]))
        if mismatches:
            for m in mismatches:
                print("MISMATCH: %s" % m, file=sys.stderr)
            print("report 中止：自报计数与脚本重算不一致（exit 3）", file=sys.stderr)
            return 3
        prisma["claim_check"] = "通过：自报计数与重算一致"
    _dump(args.out, prisma)
    idf = counts["identification"]
    scr = counts["screening"]
    print("report: identification(raw=%d, dup_removed=%d) screening(screened=%d, "
          "excluded=%d) included=%d → %s"
          % (idf["raw_hits"], idf["duplicates_removed"], scr["records_screened"],
             scr["excluded"], counts["included"]["total"], args.out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PRISMA 风格筛选与计数重算")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("screen")
    ps.add_argument("--hits", required=True)
    ps.add_argument("--decisions", required=True)
    ps.add_argument("--out", required=True)
    pr = sub.add_parser("report")
    pr.add_argument("--screened", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--claim", default=None)
    args = ap.parse_args(argv)
    return cmd_screen(args) if args.cmd == "screen" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
