#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_bind.py — 证据装订：从题录 title/abstract 原文中切出支撑片段。

铁律：
- quote 永远由脚本用 char offsets 从原文切出（text[start:end]），逐字一致，
  绝不改写、绝不补全、绝不编造；
- 模型（或示例中的确定性替身）只能在 candidates 中“选择”，不能自造文本；
- verify_binding() 可随时复核：重新加载快照，检查 text[start:end] == quote。

每条候选片段：
{record_id, field("title"|"abstract"), char_start, char_end, quote,
 dimension, matched_term}

流程：对 included / needs_human_review 的条目，按其 score_entries 中的正向命中
逐维度生成候选片段（先查 title 再查 abstract），写入 evidence_candidates.json；
auto_select 是“模型选择”的确定性替身（示例用），真实运行时由 Agent 阅读
candidates 后挑选最贴切者写入 evidence_selected.json。

用法：
  python3 evidence_bind.py --case /path/to/case.json [--auto-select]
输出：<output_dir>/evidence_candidates.json
      <output_dir>/evidence_selected.json（--auto-select 时）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

# 选择优先级：研究对象 > 干预/方法 > 结局 > 研究设计
DIMENSION_PRIORITY = ["population", "intervention", "outcome", "study_design"]


def _candidate(rec, field, term, dimension):
    text = rec.get(field)
    if not text:
        return None
    idx = text.lower().find(term.lower())
    if idx < 0:
        return None
    start, end = common.sentence_span(text, idx, idx + len(term))
    quote = text[start:end]
    assert quote == text[start:end]  # 切出即逐字
    return {"record_id": rec["record_id"], "field": field,
            "char_start": start, "char_end": end, "quote": quote,
            "dimension": dimension, "matched_term": term,
            "snapshot_file": rec["snapshot_file"]}


def candidates_for_record(rec, score_entries, max_per_dimension=1):
    cands = []
    seen_dims = {}
    for e in score_entries:
        if e["points"] <= 0:
            continue  # 只为正向命中装订证据；负向命中记录在决策表即可
        dim = e["dimension"]
        if seen_dims.get(dim, 0) >= max_per_dimension:
            continue
        cand = None
        # 先 title 后 abstract（与打分时记录的 field 一致优先）
        order = [e["field"]] + [f for f in ("title", "abstract") if f != e["field"]]
        for field in order:
            cand = _candidate(rec, field, e["term"], dim)
            if cand:
                break
        if cand:
            cands.append(cand)
            seen_dims[dim] = seen_dims.get(dim, 0) + 1
    return cands


def auto_select(candidates, max_quotes=3):
    """确定性替身（仅 minimal 示例）：按维度优先级各取第一条。
    真实运行时此步由 Agent 完成：阅读 candidates，挑最贴切者。"""
    def pri(c):
        try:
            return DIMENSION_PRIORITY.index(c["dimension"])
        except ValueError:
            return len(DIMENSION_PRIORITY)
    by_dim = {}
    for c in sorted(candidates, key=pri):
        by_dim.setdefault(c["dimension"], c)
    picked = [by_dim[d] for d in DIMENSION_PRIORITY if d in by_dim]
    for c in sorted(candidates, key=pri):
        if len(picked) >= max_quotes:
            break
        if c not in picked:
            picked.append(c)
    return picked[:max_quotes]


def verify_binding(index, binding):
    """复核：quote 必须等于原文 text[start:end]。"""
    rec = index.get(binding["record_id"])
    if rec is None:
        return False
    text = rec.get(binding["field"])
    if text is None:
        return False
    return text[binding["char_start"]:binding["char_end"]] == binding["quote"]


def _load_decisions(out_dir):
    rows = []
    path = os.path.join(out_dir, "screening_decisions.jsonl")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run(case_path, do_auto_select=False):
    case = common.load_case(case_path)
    materials_dir = common.find_materials_dir(case)
    out_dir = common.resolve_dir(case, "output_dir", "output")
    records, index, _files = common.load_materials(materials_dir)
    decisions = _load_decisions(out_dir)

    all_cands, all_selected = [], []
    for d in decisions:
        if d["decision"] not in ("included", "needs_human_review"):
            continue
        rec = index[d["record_id"]]
        cands = candidates_for_record(rec, d.get("score_entries") or [])
        all_cands.extend(cands)
        sel = auto_select(cands)
        for s in sel:
            s = dict(s)
            s["selected_by"] = "auto_select_deterministic_stand-in" \
                if do_auto_select else "agent"
            s["decision"] = d["decision"]
            all_selected.append(s)

    cand_path = os.path.join(out_dir, "evidence_candidates.json")
    common.write_json(cand_path, {
        "policy": "quotes are verbatim substrings cut by char offsets; "
                  "agent may only SELECT from candidates, never paraphrase",
        "candidates": all_cands,
    })
    print("evidence_bind: candidates=%d -> %s" % (len(all_cands), cand_path))

    if do_auto_select:
        bad = [s for s in all_selected if not verify_binding(index, s)]
        sel_path = os.path.join(out_dir, "evidence_selected.json")
        common.write_json(sel_path, {
            "selected_by": "auto_select_deterministic_stand-in",
            "note": "真实运行时由 Agent 从 evidence_candidates.json 中选择并写明理由",
            "bindings": all_selected,
        })
        print("evidence_bind: selected=%d verbatim_failures=%d -> %s"
              % (len(all_selected), len(bad), sel_path))
        if bad:
            common.die("存在非逐字证据片段！")
    return all_cands, all_selected


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据装订（verbatim quote + offsets）")
    ap.add_argument("--case", required=True)
    ap.add_argument("--auto-select", action="store_true",
                    help="用确定性替身自动选择（仅 minimal 示例）")
    args = ap.parse_args(argv)
    run(args.case, do_auto_select=args.auto_select)


if __name__ == "__main__":
    main()
