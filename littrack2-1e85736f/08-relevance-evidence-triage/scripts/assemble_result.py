#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 按 case.json 的 output_contract 组装并强制校验 result.json。

规则：
- output_contract.required_fields 中的每个字段都必须出现；缺失字段补 null
  并将 status 置为 "partial"（诚实标注），绝不静默省略；
- included / needs_human_review 条目必须带证据装订（evidence 列表），
  若某条无证据则 status=partial 并在 limitations 说明；
- 绝不生成 output_contract 未声明的“看似官方”的字段名（允许多出 artifacts 等
  说明性字段，但必填项以 contract 为准）。

用法：
  python3 assemble_result.py --case /path/to/case.json
输出：<output_dir>/result.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def _load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json_or(path, default):
    return common.read_json(path) if os.path.exists(path) else default


def build_result(case, out_dir):
    decisions = _load_jsonl(os.path.join(out_dir, "screening_decisions.jsonl"))
    flow = _load_json_or(os.path.join(out_dir, "prisma_flow.json"), None)
    selected = _load_json_or(os.path.join(out_dir, "evidence_selected.json"),
                             {"bindings": []})
    bindings_by_rec = {}
    for b in selected.get("bindings", []):
        bindings_by_rec.setdefault(b["record_id"], []).append({
            "quote": b["quote"], "field": b["field"],
            "char_start": b["char_start"], "char_end": b["char_end"],
            "dimension": b["dimension"], "matched_term": b["matched_term"],
        })

    rubric = case.get("screening_rubric") or {}
    limitations, partial_reasons = [], []

    def entry(d, with_evidence):
        e = {
            "record_id": d["record_id"], "source": d["source"],
            "title": d["title"], "doi_or_id": d["record_id"],
            "score": d.get("score"),
            "decision": d["decision"],
            "title_only": d.get("title_only"),
            "score_entries": d.get("score_entries") or [],
            "rationale_note": d.get("rationale_note") or "",
        }
        if with_evidence:
            e["evidence"] = bindings_by_rec.get(d["record_id"], [])
            if not e["evidence"]:
                partial_reasons.append(
                    "%s 缺少证据装订" % d["record_id"])
        return e

    included = [entry(d, True) for d in decisions
                if d["decision"] == "included"]
    review = []
    for d in decisions:
        if d["decision"] != "needs_human_review":
            continue
        e = entry(d, True)
        e["band"] = {"threshold": rubric.get("include_threshold"),
                     "delta": rubric.get("borderline_delta"),
                     "note": "分数落在阈值±δ 边界带内，需人工复核，未强行二分"}
        review.append(e)
    excluded = [{
        "record_id": d["record_id"], "source": d["source"],
        "title": d["title"], "stage": d["stage"],
        "category": d.get("category"),
        "category_evidence": d.get("category_evidence"),
        "score": d.get("score"),
    } for d in decisions if d["decision"] == "excluded"]

    # 遗漏说明：预筛排除但未逐条抽审的类别 + 只能按标题判断的条目
    pf_cats = sorted({d["category"] for d in excluded
                      if d["stage"] == "prefilter" and d.get("category")})
    title_only = [d["record_id"] for d in decisions if d.get("title_only")]
    omission_notes = {
        "prefilter_excluded_not_audited": pf_cats,
        "prefilter_note": "以下类别的预筛排除条目未逐条人工抽审，可能存在误排: "
                          + (", ".join(pf_cats) if pf_cats else "无"),
        "title_only_records": title_only,
        "title_only_note": "以下条目摘要缺失，只能按标题判断，结论置信度低",
        "other": [],
    }

    if flow is None:
        partial_reasons.append("缺少 prisma_flow.json")
    elif not flow.get("ok"):
        partial_reasons.append("PRISMA 计数不守恒")
    if title_only:
        limitations.append("存在仅按标题判断的条目（摘要缺失）")
    if pf_cats:
        limitations.append("预筛排除类别未逐条抽审: " + ", ".join(pf_cats))
    if case.get("synthetic"):
        limitations.append("本结果为合成（synthetic）示例产物，不构成真实文献结论")

    result = {
        "case_id": case.get("case_id"),
        "status": "partial" if partial_reasons else "ok",
        "research_question": case.get("research_question"),
        "screening_window": case.get("window"),
        "prisma_flow": flow,
        "included": included,
        "needs_human_review": review,
        "excluded": excluded,
        "exclusions_by_category": dict(Counter(
            d["category"] for d in excluded if d.get("category"))),
        "evidence_policy": {
            "verbatim": True,
            "source_fields": ["title", "abstract"],
            "offsets": "char offsets into the field text as stored in snapshot",
            "selected_by": selected.get("selected_by", "agent"),
            "candidates_file": "evidence_candidates.json",
            "selected_file": "evidence_selected.json",
        },
        "omission_notes": omission_notes,
        "limitations": limitations + ["partial 原因: " + r for r in partial_reasons],
        "artifacts": {
            "prefilter_results": "prefilter_results.jsonl",
            "screening_decisions": "screening_decisions.jsonl",
            "evidence_candidates": "evidence_candidates.json",
            "evidence_selected": "evidence_selected.json",
            "prisma_flow": "prisma_flow.json",
        },
    }
    return result


def enforce_contract(result, contract):
    """强制校验：required_fields 缺失补 null 并置 partial。"""
    required = (contract or {}).get("required_fields") or []
    missing = [f for f in required if f not in result]
    for f in missing:
        result[f] = None
    if missing:
        result["status"] = "partial"
        result.setdefault("limitations", []).append(
            "output_contract 缺失字段已补 null: " + ", ".join(missing))
    return missing


def run(case_path):
    case = common.load_case(case_path)
    out_dir = common.resolve_dir(case, "output_dir", "output")
    result = build_result(case, out_dir)
    missing = enforce_contract(result, case.get("output_contract"))
    out_path = os.path.join(out_dir, "result.json")
    common.write_json(out_path, result)
    print("assemble_result: status=%s missing_fields=%s -> %s"
          % (result["status"], missing or "[]", out_path))
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装并强制校验 result.json")
    ap.add_argument("--case", required=True)
    args = ap.parse_args(argv)
    run(args.case)


if __name__ == "__main__":
    main()
