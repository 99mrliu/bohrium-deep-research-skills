#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图谱组装：节点 + lint 后关系 → graph.json / graph.jsonl / merge_report.json。

- 跨篇合并/不合并决定来自 merge_decisions.json（Agent 显式给出依据），
  此处只执行并记录，不自动猜测合并。
- 共现记录（cooccurrence_notes）进入图谱元信息，明确“共现≠直接关系”。
用法：
  python3 graph_build.py --nodes nodes.json --relations relations_linted.json \
      --merges merge_decisions.json --outdir <dir>
"""
import argparse
import sys

from relation_common import load_json, dump_json


def main(argv=None):
    ap = argparse.ArgumentParser(description="条件化关系图谱组装")
    ap.add_argument("--nodes", required=True)
    ap.add_argument("--relations", required=True)
    ap.add_argument("--merges", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)

    nodes_doc = load_json(args.nodes)
    rel_doc = load_json(args.relations)
    merge_doc = load_json(args.merges)

    nodes = nodes_doc.get("nodes", [])
    edges = rel_doc.get("edges", [])
    merges = merge_doc.get("merges", [])
    non_merges = merge_doc.get("non_merges", [])
    cooc = rel_doc.get("cooccurrence_notes", [])

    graph = {
        "schema": "conditioned-relation-kg/1.0",
        "labels": ["SYNTHETIC"] if nodes_doc.get("synthetic") else [],
        "nodes": nodes,
        "edges": edges,
        "merge_report": {
            "policy": "合并需显式依据；同名不同对象不得合并；不强迫每个别名合并",
            "merges": merges,
            "non_merges": non_merges,
        },
        "cooccurrence_notes": cooc,
    }
    dump_json(graph, args.outdir.rstrip("/") + "/graph.json")

    with open(args.outdir.rstrip("/") + "/graph.jsonl", "w", encoding="utf-8") as fh:
        import json as _json
        for n in nodes:
            rec = {"kind": "node"}
            rec.update(n)
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        for e in edges:
            rec = {"kind": "edge"}
            rec.update(e)
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")

    dump_json(graph["merge_report"], args.outdir.rstrip("/") + "/merge_report.json")
    print("graph: nodes=%d edges=%d merges=%d non_merges=%d -> %s"
          % (len(nodes), len(edges), len(merges), len(non_merges), args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
