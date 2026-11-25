#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prefilter.py — 第一阶段：确定性规则预筛（不做任何语义判断）。

规则顺序（命中即排除，记录失败规则与排除类别）：
1. language         语言不在白名单（语言缺失 unknown 时放行但打标，诚实降级）
2. non_research_type 文献类型在排除清单（editorial/news/correction/review 等）
3. out_of_window    发表日期在窗口外（日期缺失时放行但打标 date_unknown）
4. blocked_term     标题命中明显无关词表

用法：
  python3 prefilter.py --case /path/to/case.json
输出：<output_dir>/prefilter_results.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def prefilter_record(rec, cfg):
    """返回 (passed, failed_rule, category, flags)。"""
    flags = []
    langs = [x.lower() for x in cfg.get("allowed_languages", ["en"])]
    lang = (rec.get("language") or "unknown").lower()
    if lang in ("unknown", ""):
        flags.append("language_unknown")   # 诚实放行，进入遗漏说明
    elif lang not in langs:
        return False, "language", "language", flags

    excluded_types = [x.lower() for x in cfg.get("excluded_doc_types", [])]
    if (rec.get("doc_type") or "").lower() in excluded_types:
        return False, "doc_type", "non_research_type", flags

    window = cfg.get("window") or {}
    inwin = common.date_in_window(rec.get("pub_date"),
                                  window.get("start"), window.get("end"))
    if inwin is None:
        flags.append("date_unknown")
    elif not inwin:
        return False, "window", "out_of_window", flags

    title_l = (rec.get("title") or "").lower()
    for term in cfg.get("blocklist_title_terms", []):
        if term.lower() in title_l:
            return False, "blocklist", "blocked_term", flags

    return True, None, None, flags


def run(case_path):
    case = common.load_case(case_path)
    cfg = dict(case.get("prefilter") or {})
    cfg.setdefault("window", case.get("window") or {})
    materials_dir = common.find_materials_dir(case)
    out_dir = common.resolve_dir(case, "output_dir", "output")
    records, _index, files = common.load_materials(materials_dir)

    rows = []
    for rec in records:
        passed, rule, category, flags = prefilter_record(rec, cfg)
        rows.append({
            "record_id": rec["record_id"],
            "source": rec["source"],
            "title": rec["title"],
            "stage": "prefilter",
            "passed": passed,
            "failed_rule": rule,
            "category": category,
            "flags": flags,
            "snapshot_file": rec["snapshot_file"],
        })
    out_path = os.path.join(out_dir, "prefilter_results.jsonl")
    common.write_jsonl(out_path, rows)
    n_pass = sum(1 for r in rows if r["passed"])
    print("prefilter: identified=%d passed=%d removed=%d (files=%s) -> %s"
          % (len(rows), n_pass, len(rows) - n_pass, ",".join(files), out_path))
    return rows, records


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性规则预筛")
    ap.add_argument("--case", required=True, help="case.json 路径")
    args = ap.parse_args(argv)
    run(args.case)


if __name__ == "__main__":
    main()
