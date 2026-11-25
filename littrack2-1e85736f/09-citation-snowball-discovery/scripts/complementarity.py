#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""complementarity.py — 图谱渠道互补增益度量 + graph_only 漏检原因诊断。

度量定义见 references/complementarity-metrics.md：
  graph_unique_gain = |graph_only| / (|both| + |graph_only| + |keyword_only|)
分母为 0 时返回 None（诚实地不给数字）。

诊断：对每条 graph_only 候选，检查其标题/摘要（均取自材料原文）是否包含各查询词
（casefold 子串匹配），给出漏检原因与 evidence locator（指向图谱节点记录 /
快照条目），绝不臆测材料中不存在的文本。
"""
import json
import sys

GAIN_DEFINITION = "graph_unique_gain = |graph_only| / (|both| + |graph_only| + |keyword_only|)，分母为去重后窗口内新候选总数"


def _has(text, term):
    return isinstance(text, str) and isinstance(term, str) and term.casefold() in text.casefold()


def diagnose(graph_only_items, query_terms):
    out = []
    for item in graph_only_items:
        title, abstract = item.get("title"), item.get("abstract")
        missing_title = [t for t in query_terms if not _has(title, t)]
        missing_abs = [t for t in query_terms if not _has(abstract, t)]
        reasons = []
        if title is None and abstract is None:
            reasons.append("图谱节点记录不含标题/摘要文本，无法用查询词命中（材料本身无文本可检）")
        else:
            if title is not None and len(missing_title) == len(query_terms):
                reasons.append("标题不含任何查询词: %s" % ", ".join(repr(t) for t in query_terms))
            if abstract is not None and len(missing_abs) == len(query_terms):
                reasons.append("摘要不含任何查询词: %s" % ", ".join(repr(t) for t in query_terms))
            if abstract is None:
                reasons.append("摘要字段缺失（材料未提供），关键词渠道无从命中摘要")
            if not reasons:
                reasons.append("标题/摘要命中部分查询词但仍未被关键词渠道收录，原因超出材料可解释范围")
        out.append({
            "id": item.get("id"),
            "title": title,
            "reasons": reasons,
            "evidence": {
                "graph_node_locator": (item.get("locators") or {}).get("graph"),
                "note": "证据为图谱节点记录中的 title/abstract 原文，locator 指向该记录",
            },
        })
    return out


def metrics(merged):
    b, g, k = (len(merged.get("both", [])), len(merged.get("graph_only", [])),
               len(merged.get("keyword_only", [])))
    total = b + g + k
    return {
        "counts": {"both": b, "graph_only": g, "keyword_only": k, "total_new_unique": total},
        "graph_unique_gain": (g / total) if total else None,
        "graph_unique_gain_definition": GAIN_DEFINITION,
        "graph_channel_yield": {
            "graph_new_candidates": b + g,
            "note": "图谱渠道窗口内新候选数 = both + graph_only；context 与 dangling 不计入",
        },
    }


def main(argv):
    if len(argv) != 3:
        print("用法: complementarity.py <merged.json(channel_merge 输出)> <query_terms,逗号分隔>",
              file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        merged = json.load(f)
    terms = [t for t in argv[2].split(",") if t]
    m = metrics(merged)
    m["diagnosis"] = diagnose(merged.get("graph_only", []), terms)
    json.dump(m, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
