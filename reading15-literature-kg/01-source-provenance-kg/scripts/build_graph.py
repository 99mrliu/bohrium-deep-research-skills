#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_graph.py — 由验证通过的候选抽取结果构建确定性图谱。

输入：normalized_corpus.json + candidate_extraction.json（须先过 verify_evidence）。
输出：
- graph.json：单一 JSON 对象（nodes/edges/merges/nonmerges/conflicts/unreported/stats）
- graph.jsonl：每行一个对象（{"row":"node"|"edge"|...}），便于流式处理

构建规则（全部机械、确定）：
- merge member 节点保留在图中但标记 merged_into，默认查询仍可见其溯源价值；
- 节点按 node_id 排序，边按 (subject, edge_id) 排序；
- 每个节点/边附 source_ids（证据源集合）冗余字段，便于按源过滤；
- 统计信息只来自计数，不包含任何臆造分数。
"""

from __future__ import annotations

import argparse
import sys

import kgcommon as k


def build(corpus, extraction):
    nodes = []
    member_into = {}
    for m in extraction.get("merges", []) or []:
        for member in m.get("members", []) or []:
            member_into[member] = m.get("node")

    for node in extraction.get("nodes", []) or []:
        n = dict(node)
        n["source_ids"] = k.evidence_source_ids(node.get("evidence"))
        if n["node_id"] in member_into:
            n["merged_into"] = member_into[n["node_id"]]
        nodes.append(n)
    nodes.sort(key=lambda n: n["node_id"])

    edges = []
    for edge in extraction.get("edges", []) or []:
        e = dict(edge)
        e["source_ids"] = k.evidence_source_ids(edge.get("evidence"))
        edges.append(e)
    edges.sort(key=lambda e: (e["subject"], e["edge_id"]))

    by_kind = {}
    for n in nodes:
        by_kind[n.get("kind", "?")] = by_kind.get(n.get("kind", "?"), 0) + 1

    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "merge_count": len(extraction.get("merges", []) or []),
        "nonmerge_count": len(extraction.get("nonmerges", []) or []),
        "conflict_count": len(extraction.get("conflicts", []) or []),
        "unreported_count": len(extraction.get("unreported", []) or []),
        "node_count_by_kind": dict(sorted(by_kind.items())),
        "source_ids": [s["source_id"] for s in corpus.get("sources", [])],
    }

    graph = {
        "format": k.FORMAT_GRAPH,
        "case_id": extraction.get("case_id"),
        "primary_paper": extraction.get("primary_paper"),
        "nodes": nodes,
        "edges": edges,
        "merges": extraction.get("merges", []) or [],
        "nonmerges": extraction.get("nonmerges", []) or [],
        "conflicts": extraction.get("conflicts", []) or [],
        "unreported": extraction.get("unreported", []) or [],
        "stats": stats,
    }
    return graph


def graph_to_jsonl(graph):
    lines = []
    import json
    def row(kind, obj):
        o = {"row": kind}
        o.update(obj)
        return json.dumps(o, ensure_ascii=False, sort_keys=True)
    for n in graph["nodes"]:
        lines.append(row("node", n))
    for e in graph["edges"]:
        lines.append(row("edge", e))
    for key in ("merges", "nonmerges", "conflicts", "unreported"):
        for item in graph[key]:
            lines.append(row(key[:-1] if key.endswith("s") else key, item))
    lines.append(row("stats", graph["stats"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="构建确定性溯源图谱")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--extraction", required=True)
    ap.add_argument("--out", required=True, help="graph.json 输出路径")
    ap.add_argument("--jsonl", default=None, help="graph.jsonl 输出路径（可选）")
    args = ap.parse_args(argv)

    corpus = k.read_json(args.corpus)
    extraction = k.read_json(args.extraction)
    graph = build(corpus, extraction)
    k.write_json(args.out, graph)
    if args.jsonl:
        k.write_text(args.jsonl, graph_to_jsonl(graph))
    s = graph["stats"]
    print(f"[build_graph] nodes={s['node_count']} edges={s['edge_count']} "
          f"merges={s['merge_count']} nonmerges={s['nonmerge_count']} "
          f"conflicts={s['conflict_count']} unreported={s['unreported_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
