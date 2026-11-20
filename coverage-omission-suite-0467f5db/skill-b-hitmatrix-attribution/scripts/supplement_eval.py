#!/usr/bin/env python3
"""supplement_eval.py — 定向补检与补检前后复算。

按漏检归因的主导类别，每类设计一条定向补检查询：
  VOCAB_GAP          → 检索式取自漏检记录的实际未覆盖词汇（uncovered_tokens）
  FIELD_RESTRICTION  → 沿用致漏查询的检索式，字段放宽为 any
  TIME_WINDOW        → 沿用致漏查询的检索式，时间窗放宽（去除截断边界）
  SOURCE_ABSENT      → 切换至案例中存在的另一来源执行同一检索式
  RECORD_ANOMALY     → 不可补检，登记 not_applicable
  UNDETERMINED       → 不可补检，登记 not_applicable

补检查询在对应来源的本地索引/响应文件上以本地布尔模拟语义执行
（见 attribute_miss.py 的 simulate_query），命中记录写为新的补检响应文件，
随后将补检查询并入检索记录，重跑完整三级判定并复算覆盖率。

零新增命中必须如实报告为 marginal_gain=0，不得宣称遗漏已削减。

输入: work/case_normalized.json, work/coverage.json, work/miss_attribution.json
输出: work/adjudication_supplement.json, work/coverage_after.json,
      work/supplement_eval.json, out/supplement_eval.md

用法:
  python3 supplement_eval.py --work /app/work --out /app/output

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adjudicate import adjudicate, load_results_files  # noqa: E402
from attribute_miss import simulate_query, query_tokens, load_json  # noqa: E402
from hit_matrix import build_matrix, compute_coverage  # noqa: E402

SUPPLEMENTABLE = ("VOCAB_GAP", "FIELD_RESTRICTION", "TIME_WINDOW", "SOURCE_ABSENT")
MAX_VOCAB_TERMS = 6


def design_supplements(attributions, case):
    """按类别各设计一条补检查询。返回 (supplements, skipped)。"""
    by_cat = {}
    for a in attributions:
        by_cat.setdefault(a["primary_category"], []).append(a)
    queries = case.get("search_log", [])
    q_by_id = {q.get("query_id"): q for q in queries}
    # 可切换来源：检索记录中出现的来源 ∪ extra.sources 声明的本地索引来源
    extra = case.get("extra") or {}
    sources = sorted({q.get("source") for q in queries}
                     | {s.get("source") for s in (extra.get("sources") or [])
                        if s.get("source")})
    ref_by_id = {r["ref_id"]: r for r in case.get("reference_set", [])}
    supplements, skipped = [], []

    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        if cat not in SUPPLEMENTABLE:
            skipped.append({"category": cat, "count": len(items),
                            "reason": "not_applicable：该类别无法通过补检消除"})
            continue
        first = items[0]
        base_q = q_by_id.get(first.get("query_id")) or (queries[0] if queries else {})
        sup = {"query_id": "supp_%s" % cat.lower(),
               "category": cat,
               "executed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "target_ref_ids": [a["ref_id"] for a in items]}
        if cat == "VOCAB_GAP":
            terms = []
            for a in items:
                for t in (a.get("uncovered_tokens") or []):
                    if t not in terms:
                        terms.append(t)
            terms = terms[:MAX_VOCAB_TERMS]
            if not terms:  # 归因未给出词汇，退化为漏检标题词汇
                for a in items:
                    ref = ref_by_id.get(a["ref_id"]) or {}
                    for t in query_tokens(ref.get("title") or ""):
                        if t not in terms:
                            terms.append(t)
                terms = terms[:MAX_VOCAB_TERMS]
            sup.update({"source": base_q.get("source"),
                        "query_string": " ".join(terms),
                        "fields": ["any"], "date_window": None,
                        "rationale": "词汇取自漏检记录实际未覆盖词汇"})
        elif cat == "FIELD_RESTRICTION":
            sup.update({"source": base_q.get("source"),
                        "query_string": base_q.get("query_string"),
                        "fields": ["any"],
                        "date_window": base_q.get("date_window"),
                        "rationale": "沿用致漏查询 %s，字段放宽为 any"
                                     % base_q.get("query_id")})
        elif cat == "TIME_WINDOW":
            sup.update({"source": base_q.get("source"),
                        "query_string": base_q.get("query_string"),
                        "fields": base_q.get("fields") or ["any"],
                        "date_window": None,
                        "rationale": "沿用致漏查询 %s，去除时间窗截断"
                                     % base_q.get("query_id")})
        elif cat == "SOURCE_ABSENT":
            alt = [s for s in sources if s != base_q.get("source")]
            if not alt:
                skipped.append({"category": cat, "count": len(items),
                                "reason": "案例中无其他来源可切换"})
                continue
            # 检索式取自漏检记录自身标题词汇，而非沿用失效查询
            terms = []
            for a in items:
                ref = ref_by_id.get(a["ref_id"]) or {}
                for t in sorted(query_tokens(ref.get("title") or "")):
                    if t not in terms:
                        terms.append(t)
            sup.update({"source": alt[0],
                        "query_string": " ".join(terms[:MAX_VOCAB_TERMS]),
                        "fields": ["any"], "date_window": None,
                        "rationale": "切换来源 %s → %s，检索式取自漏检记录标题词汇"
                                     % (base_q.get("source"), alt[0])})
        supplements.append(sup)
    return supplements, skipped


def execute_supplements(supplements, case, work_dir):
    """在本地索引/响应文件上执行补检查询，返回 {query_id: results_file}。"""
    # 每个来源的可检语料：优先 extra.sources[].index_file，否则该来源全部 results_file 合并
    extra = case.get("extra") or {}
    corpus = {}
    for s in (extra.get("sources") or []):
        src, idx = s.get("source"), s.get("index_file")
        data = load_json(idx)
        if isinstance(data, dict):
            data = data.get("records") or data.get("results") or []
        if src and isinstance(data, list):
            corpus.setdefault(src, []).extend(data)
    for q in case.get("search_log", []):
        data = load_json(q.get("results_file"))
        if isinstance(data, dict):
            data = data.get("records") or data.get("results") or []
        if isinstance(data, list):
            corpus.setdefault(q.get("source"), []).extend(data)

    results_files = {}
    for sup in supplements:
        records = corpus.get(sup.get("source"), [])
        hits = [r for r in records
                if simulate_query(r, sup.get("query_string") or "",
                                  sup.get("fields"), sup.get("date_window"))]
        rf = os.path.join(work_dir, "supplement_results_%s.json"
                          % sup["query_id"])
        with open(rf, "w", encoding="utf-8") as f:
            json.dump({"query": sup, "corpus_size": len(records),
                       "results": hits}, f, ensure_ascii=False, indent=2)
        sup["results_file"] = rf
        sup["raw_hit_count"] = len(hits)
        results_files[sup["query_id"]] = rf
    return results_files


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="定向补检：按主导漏检类别各设计一条补检查询并复算前后覆盖率。")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out", default="/app/output", help="产物目录（默认 /app/output）")
    ap.add_argument("--decisions", default=None,
                    help="L3 裁决回灌文件（默认自动读取 work/decisions.json，若存在）")
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.work, "case_normalized.json"))
    coverage = load_json(os.path.join(args.work, "coverage.json"))
    attribution = load_json(os.path.join(args.work, "miss_attribution.json"))
    if case is None or coverage is None or attribution is None:
        print("ERROR: 缺少前置产物，请先运行 parse_case/adjudicate/hit_matrix/"
              "attribute_miss", file=sys.stderr)
        return 2

    usable = [r for r in case.get("reference_set", []) if r.get("usable", True)]
    queries = list(case.get("search_log", []))
    before = coverage["overall"]

    attributions = attribution.get("attributions", [])
    supplements, skipped = design_supplements(attributions, case)
    execute_supplements(supplements, case, args.work)

    # 并入检索记录，重跑完整三级判定
    aug_queries = queries + [
        {"query_id": s["query_id"], "source": s["source"],
         "executed_at": s["executed_at"], "query_string": s["query_string"],
         "fields": s["fields"], "date_window": s["date_window"],
         "results_file": s["results_file"]} for s in supplements]
    files = sorted({q["results_file"] for q in aug_queries if q.get("results_file")})
    results_by_file = load_results_files(args.work, files)
    for k, v in results_by_file.items():
        if v is None:
            results_by_file[k] = []
    decisions_path = args.decisions
    if decisions_path is None:
        cand = os.path.join(args.work, "decisions.json")
        decisions_path = cand if os.path.isfile(cand) else None
    decisions = load_json(decisions_path) if decisions_path else None
    cells_aug, queue_aug = adjudicate(usable, aug_queries, results_by_file,
                                      decisions or {})

    adj_path = os.path.join(args.work, "adjudication_supplement.json")
    with open(adj_path, "w", encoding="utf-8") as f:
        json.dump({"cells": cells_aug}, f, ensure_ascii=False, indent=2)

    ref_ids = [r["ref_id"] for r in usable]
    _, col_keys, matrix = build_matrix(cells_aug, ref_ids, aug_queries)
    after_cov = compute_coverage(matrix, col_keys, aug_queries)
    after = after_cov["overall"]

    new_hits = sorted(set(after_cov["hit_ref_ids"]) - set(coverage["hit_ref_ids"]))
    marginal_gain = len(new_hits)

    # 每条补检的边际贡献：其列集合带来的新增命中
    supp_cols = [ck for ck in col_keys if ck.startswith("supp_")]
    for s in supplements:
        skeys = [ck for ck in supp_cols if ck.split("|")[0] == s["query_id"]]
        gained = [rid for rid in coverage["missed_ref_ids"]
                  if any(matrix[rid][ck]["status"] == "hit" for ck in skeys)]
        s["new_hit_ref_ids"] = sorted(gained)
        s["marginal_gain"] = len(gained)
        s["zero_gain_reported_honestly"] = (len(gained) == 0)

    evaluation = {
        "before": before,
        "after": after,
        "recall_delta": round((after["recall"] or 0.0) - (before["recall"] or 0.0), 6),
        "new_hit_ref_ids": new_hits,
        "marginal_gain": marginal_gain,
        "marginal_gain_is_zero": marginal_gain == 0,
        "supplements": supplements,
        "skipped_categories": skipped,
        "pending_adjudication_after": len(queue_aug),
        "same_frozen_reference_set": True,
    }
    eval_path = os.path.join(args.work, "supplement_eval.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)
    cov_path = os.path.join(args.work, "coverage_after.json")
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(after_cov, f, ensure_ascii=False, indent=2)

    os.makedirs(args.out, exist_ok=True)
    md_path = os.path.join(args.out, "supplement_eval.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 定向补检评估\n\n")
        f.write("- 补检前覆盖率: %d/%d = %.4f, Wilson95=%s\n"
                % (before["hits"], before["total"], before["recall"] or 0.0,
                   before.get("wilson95")))
        f.write("- 补检后覆盖率: %d/%d = %.4f, Wilson95=%s\n"
                % (after["hits"], after["total"], after["recall"] or 0.0,
                   after.get("wilson95")))
        f.write("- 边际增益（新增命中）: %d 条 %s\n\n"
                % (marginal_gain, new_hits))
        if marginal_gain == 0:
            f.write("> 注意：本次补检零边际增益，遗漏未削减，如实报告。\n\n")
        f.write("| 补检查询 | 类别 | 来源 | 检索式 | 原始命中 | 新增参考命中 |\n"
                "| --- | --- | --- | --- | --- | --- |\n")
        for s in supplements:
            f.write("| %s | %s | %s | %s | %d | %d |\n"
                    % (s["query_id"], s["category"], s.get("source"),
                       (s.get("query_string") or "").replace("|", "\\|"),
                       s.get("raw_hit_count", 0), s["marginal_gain"]))
        for sk in skipped:
            f.write("| （跳过） | %s | - | %s | - | - |\n"
                    % (sk["category"], sk["reason"]))

    print("supplement_eval: 补检 %d 条（跳过 %d 类），覆盖率 %.4f → %.4f，"
          "边际增益 %d 条%s"
          % (len(supplements), len(skipped), before["recall"] or 0.0,
             after["recall"] or 0.0, marginal_gain,
             "（零增益，如实报告）" if marginal_gain == 0 else ""))
    print("输出: %s ; %s ; %s" % (eval_path, cov_path, md_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
