#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_engine.py -- 补检账本与边际收益治理（skill-d-supplement-ledger）。

重心：补检是一个需要记账与止损的决策过程，不是"再搜一遍"。
  1. 查询账本：每条查询（含初始与补检轮）记录命中数、为参考集新挽回的文献数、
     边际收益；同一查询换同义词重跑不产生新命中时，账本如实记零——禁止"补检空转"；
  2. 停止规则（references/stop_rules.md）：
     S1 连续一轮零新命中；S2 最近两轮平均边际收益 < 阈值；S3 预算耗尽。
     每条规则的判定都引用账本行号；
  3. 残余遗漏估计：以两个查询族（按来源或轮次划分）为两次"捕获"，
     Chapman 校正的 Lincoln–Petersen 估计参考集中仍遗漏的规模，附假设与局限；
  4. 闭环：覆盖测量 -> 漏检清单 -> 账本驱动的补检评估 -> result.json。

仅 Python 标准库，不联网。退出码 0/2/3。
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

VERSION = "1.0.0"
MARGINAL_YIELD_FLOOR = 0.5   # S2：近两轮平均每查询新挽回数低于此值则建议停止


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".")


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def tokens(t):
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by"}
    return [x for x in norm_title(t).split() if x not in stop]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def first_year(rec):
    for k in ("year", "published", "issued", "date"):
        v = rec.get(k)
        if v is None:
            continue
        m = re.search(r"(?:19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return None


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 材料

def collect(input_dir):
    refs, queries = [], []
    for root, _d, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            low = name.lower()
            if low in ("case.json", "task.md"):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(8192)
            except Exception:
                continue
            if re.search(r'"(queries|searches)"\s*:', head) and re.search(r'"(hits|results|records)"\s*:', head):
                data = load_json(p) or {}
                for q in data.get("queries") or data.get("searches") or []:
                    if isinstance(q, dict):
                        qq = dict(q)
                        qq["_file"] = p
                        queries.append(qq)
            elif low.endswith(".csv"):
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for i, row in enumerate(csv.DictReader(fh)):
                        r = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
                        if r:
                            refs.append({"record": r, "origin": "%s:row%d" % (p, i + 2)})
    return refs, queries


def match_ref(rec, hit):
    rd, hd = norm_doi(rec.get("doi")), norm_doi(hit.get("doi"))
    if rd and hd:
        return rd == hd
    if jaccard(tokens(rec.get("title")), tokens(hit.get("title"))) >= 0.8:
        ry, hy = rec.get("year"), first_year(hit)
        return not ry or not hy or ry == hy
    return False


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="补检账本：查询记账 -> 边际收益 -> 停止规则 -> 残余估计")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    case = load_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        contract = list(oc.get("required_fields") or oc.get("fields") or oc.keys())
    elif isinstance(oc, list):
        contract = [str(x) for x in oc]
    else:
        contract = []
    if not contract:
        contract = ["coverage", "query_ledger", "stop_decision", "residual_estimate", "miss_list", "coverage_report"]

    status, uncertainty, change_log = "complete", [], []
    refs_raw, queries = collect(args.input)

    # 参考集
    refset, seen = [], set()
    for c in refs_raw:
        r = c["record"]
        key = norm_doi(r.get("doi")) or norm_title(r.get("title"))[:80]
        if key and key in seen:
            change_log.append({"ts": now_iso(), "event": "dedup_merge", "merged": c["origin"]})
            continue
        if key:
            seen.add(key)
        refset.append({"ref_id": "R%03d" % (len(refset) + 1), "doi": r.get("doi"),
                       "title": r.get("title", ""), "year": first_year(r),
                       "container": r.get("container", ""), "origin": c["origin"]})
    if not refset:
        status = "partial"
        change_log.append({"ts": now_iso(), "event": "no_reference_records"})
    if not queries:
        status = "partial"
        uncertainty.append("no query material found; ledger and downstream stages degraded")

    # 查询排序：按轮次（round/phase）再按出现顺序；无轮次信息视为单一轮
    def round_of(q, idx):
        for k in ("round", "phase", "iteration"):
            if q.get(k) is not None:
                try:
                    return int(q[k])
                except Exception:
                    pass
        return 1
    queries = list(enumerate(queries))
    queries.sort(key=lambda t: (round_of(t[1], t[0]), t[0]))

    # 查询账本：逐查询计算"新挽回"（该查询首次命中的参考集记录）
    recovered_by = {}   # ref_id -> 首个挽回它的 query_id
    ledger = []
    for order, (orig_idx, q) in enumerate(queries):
        qid = q.get("query_id") or q.get("id") or "Q%d" % (order + 1)
        hits = [h for h in (q.get("hits") or q.get("results") or q.get("records") or []) if isinstance(h, dict)]
        matched_refs, new_refs = [], []
        for rec in refset:
            if any(match_ref(rec, h) for h in hits):
                matched_refs.append(rec["ref_id"])
                if rec["ref_id"] not in recovered_by:
                    new_refs.append(rec["ref_id"])
        for rid in new_refs:
            recovered_by[rid] = qid
        ledger.append({
            "row": len(ledger) + 1,
            "query_id": qid, "round": round_of(q, orig_idx),
            "query_string": q.get("query_string") or q.get("query") or "",
            "source": q.get("source") or q.get("database") or "",
            "hit_records": len(hits), "ref_matched": matched_refs,
            "new_recovered": new_refs, "marginal_yield": len(new_refs),
            "zero_gain": len(new_refs) == 0,
        })
    dump_json(os.path.join(args.work, "query_ledger.json"), ledger)

    # 覆盖与漏检
    per_record = []
    for rec in refset:
        rid = rec["ref_id"]
        if rid in recovered_by:
            per_record.append({"ref_id": rid, "doi": rec.get("doi"), "title": rec["title"][:140],
                               "status": "hit", "recovered_by_query": recovered_by[rid]})
        else:
            per_record.append({"ref_id": rid, "doi": rec.get("doi"), "title": rec["title"][:140],
                               "status": "miss"})
    hit_n = sum(1 for r in per_record if r["status"] == "hit")
    denom = len(per_record)
    coverage = {"denominator": denom, "hit": hit_n, "miss": denom - hit_n,
                "coverage_ratio": round(hit_n / denom, 4) if denom else None}
    miss_list = [r for r in per_record if r["status"] == "miss"]

    # 停止规则判定（引用账本行号）
    rounds = sorted({row["round"] for row in ledger}) or [1]
    by_round = {r: [row for row in ledger if row["round"] == r] for r in rounds}
    last_round = rounds[-1]
    s1_zero_round = all(row["marginal_yield"] == 0 for row in by_round[last_round]) and len(rounds) > 1
    recent = [row for r in rounds[-2:] for row in by_round[r]]
    avg_recent = (sum(row["marginal_yield"] for row in recent) / len(recent)) if recent else 0.0
    s2_low_yield = len(rounds) >= 2 and avg_recent < MARGINAL_YIELD_FLOOR
    stop_rules = [
        {"rule": "S1_zero_gain_round", "fired": bool(s1_zero_round),
         "evidence_rows": [row["row"] for row in by_round[last_round]],
         "statement": "latest round %d produced zero new recovered references" % last_round if s1_zero_round
                      else "latest round still produced new references"},
        {"rule": "S2_low_marginal_yield", "fired": bool(s2_low_yield),
         "evidence_rows": [row["row"] for row in recent],
         "statement": "mean marginal yield over last two rounds %.2f < %.2f" % (avg_recent, MARGINAL_YIELD_FLOOR)
                      if s2_low_yield else "marginal yield above floor (%.2f)" % avg_recent},
        {"rule": "S3_budget_exhausted", "fired": False,
         "evidence_rows": [],
         "statement": "no budget field in case materials; rule not evaluable — declared, not assumed"},
    ]
    stop_decision = {"stop_recommended": any(r["fired"] for r in stop_rules),
                     "fired_rules": [r["rule"] for r in stop_rules if r["fired"]],
                     "rules": stop_rules}
    dump_json(os.path.join(args.work, "stop_decision.json"), stop_decision)

    # 残余遗漏估计（Chapman 校正的 Lincoln–Petersen，两个查询族 = 两次捕获）
    sources = sorted({row["source"] for row in ledger if row["source"]})
    residual = {"method": "chapman-corrected lincoln-petersen over two query families"}
    if len(sources) >= 2:
        famA, famB = sources[0], sources[1]
        # 捕获集合按"该族任一查询命中过该参考记录"计算（与首次挽回记账无关）
        def family_capture(fam):
            cap = set()
            for row in ledger:
                if row["source"] == fam:
                    cap.update(row["ref_matched"])
            return cap
        setA, setB = family_capture(famA), family_capture(famB)
        n1, n2, m = len(setA), len(setB), len(setA & setB)
        n_est = ((n1 + 1) * (n2 + 1) / (m + 1)) - 1 if (m + 1) else None
        residual.update({
            "family_A": {"source": famA, "captured": n1},
            "family_B": {"source": famB, "captured": n2},
            "overlap": m,
            "estimated_total_recoverable": round(n_est, 2) if n_est is not None else None,
            "estimated_residual_omission": round(max(0.0, n_est - len(setA | setB)), 2) if n_est is not None else None,
            "assumptions": ["equal catchability within each family (likely violated by topic heterogeneity)",
                            "independence of the two families",
                            "closed population = frozen reference set"],
            "caveat": "estimate is a lower-bound heuristic when families share retrieval bias; "
                      "report alongside per-record miss list, never as a replacement",
        })
    else:
        residual.update({"estimated": False,
                         "note": "need queries from >=2 distinct sources for capture-recapture; "
                                 "only %d source(s) present" % len(sources)})
        uncertainty.append("residual omission not estimable: fewer than two query sources")
    dump_json(os.path.join(args.work, "residual_estimate.json"), residual)

    # 报告
    lines = ["# 补检账本与边际收益报告", "",
             "- case_id: `%s`" % case_id,
             "- 覆盖：分母 %d / 命中 %d / 漏检 %d（%.4f）" % (denom, hit_n, denom - hit_n, coverage["coverage_ratio"] or 0.0),
             "- 账本：%d 条查询，%d 轮；总新挽回 %d 条参考记录" % (len(ledger), len(rounds), len(recovered_by)),
             "- 停止建议：%s（触发：%s）" % ("建议停止" if stop_decision["stop_recommended"] else "可继续补检",
                                        ", ".join(stop_decision["fired_rules"]) or "无"),
             "", "## 查询账本", "",
             "| 行 | 查询 | 轮 | 来源 | 命中记录 | 新挽回 | 边际收益 |", "|---|---|---|---|---|---|---|"]
    for row in ledger:
        lines.append("| %d | %s | %d | %s | %d | %s | %d |" % (
            row["row"], row["query_id"], row["round"], row["source"],
            row["hit_records"], ",".join(row["new_recovered"]) or "-", row["marginal_yield"]))
    lines += ["", "## 停止规则判定", ""]
    for r in stop_rules:
        lines.append("- **%s** %s — %s（账本行：%s）" % (
            r["rule"], "触发" if r["fired"] else "未触发", r["statement"],
            ",".join(map(str, r["evidence_rows"])) or "-"))
    lines += ["", "## 残余遗漏估计", "", "```json", json.dumps(residual, ensure_ascii=False, indent=2), "```"]
    report_path = os.path.join(args.output, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    artifacts = {"coverage": coverage, "query_ledger": ledger, "stop_decision": stop_decision,
                 "residual_estimate": residual, "miss_list": miss_list, "coverage_report": report_path}
    result = {"case_id": case_id, "status": status,
              "sources": [{"path": os.path.join(r, n)} for r, _d, ns in os.walk(args.input) for n in ns
                          if os.path.isfile(os.path.join(r, n))],
              "uncertainty": uncertainty, "change_log": change_log,
              "skill": "supplement-ledger-economics", "skill_version": VERSION}
    for f in contract:
        result[f] = artifacts.get(f)
    dump_json(os.path.join(args.output, "result.json"), result)
    missing = [f for f in contract if result.get(f) is None]
    if missing:
        print("contract fields unresolved: %s" % missing, file=sys.stderr)
        return 3
    return 2 if status == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())
