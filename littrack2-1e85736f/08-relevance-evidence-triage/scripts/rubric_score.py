#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rubric_score.py — 第二阶段：多维 rubric 透明打分 + 决策。

打分完全规则化：每个维度命中一个词表词即加（或减）固定分，逐条记录
score_entries（维度 / 命中词 / 分值 / 命中字段），可逐分复核，无任何黑箱。

决策规则（threshold=包含阈值, delta=边界带半宽）：
  |score - threshold| <= delta        -> needs_human_review（边界带，不强行二分）
  score > threshold + delta           -> included
  score < threshold - delta           -> excluded
排除类别：优先取被触发的负向维度的映射（category_map），否则 off_topic_low_score。
同标题重复：规范化标题相同的条目，保留 source_priority 优先者，其余记
duplicate_of_kept（这是筛选决策的去向标注，不是去重键设计，不在本 skill 范围内）。

摘要缺失：只按标题打分，title_only=true，诚实打标并进入遗漏说明。

用法：
  python3 rubric_score.py --case /path/to/case.json
输入：<output_dir>/prefilter_results.jsonl（prefilter.py 产物）
输出：<output_dir>/screening_decisions.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def _find(text_l, term):
    return term.lower() in text_l if text_l else False


def score_record(rec, rubric):
    """返回 dict：score, entries, title_only, positives, negatives。"""
    title_l = (rec.get("title") or "").lower()
    abstract = rec.get("abstract")
    abstract_l = abstract.lower() if abstract else ""
    title_only = not abstract
    entries = []
    for dim, spec in (rubric.get("dimensions") or {}).items():
        pts = spec.get("points", 0)
        matched = False
        for term in spec.get("terms", []):
            in_title = _find(title_l, term)
            in_abs = _find(abstract_l, term)
            if in_title or in_abs:
                where = "title" if in_title else "abstract"
                entries.append({"dimension": dim, "term": term,
                                "points": pts, "field": where})
                matched = True
                break  # 每个维度只记一次分
        if not matched:
            for weak in spec.get("weak_terms", []):
                in_title = _find(title_l, weak["term"])
                in_abs = _find(abstract_l, weak["term"])
                if in_title or in_abs:
                    where = "title" if in_title else "abstract"
                    entries.append({"dimension": dim, "term": weak["term"],
                                    "points": weak["points"], "field": where,
                                    "weak": True})
                    break
    score = sum(e["points"] for e in entries)
    positives = [e for e in entries if e["points"] > 0]
    negatives = [e for e in entries if e["points"] < 0]
    return {"score": score, "entries": entries, "title_only": title_only,
            "positives": positives, "negatives": negatives}


def decide(score, threshold, delta):
    if abs(score - threshold) <= delta:
        return "needs_human_review"
    return "included" if score > threshold else "excluded"


def assign_category(scored, rubric):
    """排除类别：负向维度映射优先，否则低分兜底。"""
    cmap = rubric.get("category_map") or {}
    for e in scored["negatives"]:
        if e["dimension"] in cmap:
            return cmap[e["dimension"]], e["term"]
    return "off_topic_low_score", None


def mark_duplicates(decisions, records_index, source_priority):
    """规范化标题相同的条目：保留来源优先者（同级取高分），其余标 duplicate_of_kept。"""
    groups = {}
    for d in decisions:
        rec = records_index[d["record_id"]]
        groups.setdefault(common.norm_title(rec["title"]), []).append(d)

    def rank(d):
        try:
            pri = source_priority.index(records_index[d["record_id"]]["source"])
        except ValueError:
            pri = len(source_priority)
        return (pri, -d["score"])

    n_dup = 0
    for key, group in groups.items():
        if not key or len(group) < 2:
            continue
        group.sort(key=rank)
        kept = group[0]
        for d in group[1:]:
            d["decision"] = "excluded"
            d["category"] = "duplicate_of_kept"
            d["category_evidence"] = "same normalized title as %s" % kept["record_id"]
            n_dup += 1
    return n_dup


def run(case_path):
    case = common.load_case(case_path)
    rubric = case.get("screening_rubric") or {}
    threshold = rubric.get("include_threshold", 6)
    delta = rubric.get("borderline_delta", 1)
    source_priority = (case.get("prefilter") or {}).get(
        "source_priority", ["crossref", "europepmc", "arxiv"])

    materials_dir = common.find_materials_dir(case)
    out_dir = common.resolve_dir(case, "output_dir", "output")
    records, index, _files = common.load_materials(materials_dir)
    pf_path = os.path.join(out_dir, "prefilter_results.jsonl")
    if not os.path.exists(pf_path):
        common.die("缺少 %s，请先运行 prefilter.py" % pf_path)
    prefilter = []
    with open(pf_path, "r", encoding="utf-8") as f:
        import json as _json
        for line in f:
            line = line.strip()
            if line:
                prefilter.append(_json.loads(line))

    decisions = []
    for row in prefilter:
        if not row["passed"]:
            decisions.append({  # 预筛排除，直接进入决策表（stage=prefilter）
                "record_id": row["record_id"], "source": row["source"],
                "title": row["title"], "stage": "prefilter",
                "score": None, "decision": "excluded",
                "category": row["category"], "category_evidence": row["failed_rule"],
                "flags": row.get("flags", []), "score_entries": [],
                "title_only": None, "rationale_note": "",
            })
            continue
        rec = index[row["record_id"]]
        scored = score_record(rec, rubric)
        decision = decide(scored["score"], threshold, delta)
        category, evidence = (None, None)
        if decision == "excluded":
            category, evidence = assign_category(scored, rubric)
        decisions.append({
            "record_id": rec["record_id"], "source": rec["source"],
            "title": rec["title"], "stage": "screening",
            "score": scored["score"], "threshold": threshold, "delta": delta,
            "decision": decision, "category": category,
            "category_evidence": evidence,
            "flags": row.get("flags", []),
            "title_only": scored["title_only"],
            "score_entries": scored["entries"],
            "rationale_note": "",
        })

    n_dup = mark_duplicates(
        [d for d in decisions if d["stage"] == "screening"],
        index, source_priority)

    out_path = os.path.join(out_dir, "screening_decisions.jsonl")
    common.write_jsonl(out_path, decisions)
    from collections import Counter
    cnt = Counter(d["decision"] for d in decisions)
    print("rubric_score: decisions=%s duplicates_marked=%d -> %s"
          % (dict(cnt), n_dup, out_path))
    return decisions


def main(argv=None):
    ap = argparse.ArgumentParser(description="多维 rubric 透明打分与决策")
    ap.add_argument("--case", required=True, help="case.json 路径")
    args = ap.parse_args(argv)
    run(args.case)


if __name__ == "__main__":
    main()
