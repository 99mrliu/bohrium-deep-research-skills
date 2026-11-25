#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prisma_flow.py — PRISMA 式流转计数。

层级与守恒不变量：
  identified == prefiltered_out + screened
  screened   == included + excluded_at_screening + needs_human_review
每一层都给出按排除类别的去向计数，任何数量对不上都会令 ok=false。

用法：
  python3 prisma_flow.py --case /path/to/case.json
输入：<output_dir>/prefilter_results.jsonl + screening_decisions.jsonl
输出：<output_dir>/prisma_flow.json
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


def build_flow(prefilter_rows, decisions):
    identified = len(prefilter_rows)
    pf_out = [r for r in prefilter_rows if not r["passed"]]
    screened_rows = [d for d in decisions if d["stage"] == "screening"]
    included = [d for d in screened_rows if d["decision"] == "included"]
    review = [d for d in screened_rows if d["decision"] == "needs_human_review"]
    excluded = [d for d in screened_rows if d["decision"] == "excluded"]

    flow = {
        "identified": identified,
        "prefiltered_out": len(pf_out),
        "prefiltered_out_by_category": dict(Counter(
            r["category"] or "unknown" for r in pf_out)),
        "screened": len(screened_rows),
        "included": len(included),
        "needs_human_review": len(review),
        "excluded_at_screening": len(excluded),
        "excluded_at_screening_by_category": dict(Counter(
            d["category"] or "unknown" for d in excluded)),
    }
    inv1 = flow["identified"] == flow["prefiltered_out"] + flow["screened"]
    inv2 = flow["screened"] == (flow["included"] + flow["needs_human_review"]
                                + flow["excluded_at_screening"])
    flow["invariants"] = {
        "identified == prefiltered_out + screened": inv1,
        "screened == included + needs_human_review + excluded_at_screening": inv2,
    }
    flow["ok"] = inv1 and inv2
    return flow


def run(case_path):
    case = common.load_case(case_path)
    out_dir = common.resolve_dir(case, "output_dir", "output")
    prefilter_rows = _load_jsonl(os.path.join(out_dir, "prefilter_results.jsonl"))
    decisions = _load_jsonl(os.path.join(out_dir, "screening_decisions.jsonl"))
    flow = build_flow(prefilter_rows, decisions)
    out_path = os.path.join(out_dir, "prisma_flow.json")
    common.write_json(out_path, flow)
    print("prisma_flow: %s ok=%s -> %s"
          % ({k: v for k, v in flow.items() if isinstance(v, int)},
             flow["ok"], out_path))
    if not flow["ok"]:
        common.die("PRISMA 流转计数不守恒！")
    return flow


def main(argv=None):
    ap = argparse.ArgumentParser(description="PRISMA 式流转计数")
    ap.add_argument("--case", required=True)
    args = ap.parse_args(argv)
    run(args.case)


if __name__ == "__main__":
    main()
