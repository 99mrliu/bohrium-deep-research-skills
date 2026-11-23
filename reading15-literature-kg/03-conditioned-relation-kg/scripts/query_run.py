#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性查询执行器：对 graph.jsonl 执行查询规格，输出结果子图与证据。

查询类型（query DSL，见 references/query-dsl.md）：
  compare         {dataset, metric, condition?} → 该条件下的全部比较型边
  measurements    {node, dataset?, metric?} → 该节点的全部测量边（含冲突标记）
  direct_relation {subject, object} → 两点间是否存在直接边；
                  若不存在但存在共现记录，明确回答“共现≠直接关系”
  neighbors       {node} → 一跳邻居子图
所有结果确定性产出：同输入必同输出。每个结果子图带 evidence 逐字短引。
用法：
  python3 query_run.py --graph graph.jsonl --queries queries_spec.json \
      --out queries.json
"""
import argparse
import json
import sys

from relation_common import load_json, dump_json

COMPARATIVE = {"outperforms", "compares_with"}


def load_graph(path):
    nodes, edges, cooc = {}, [], []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") == "node":
                nodes[rec["node_id"]] = rec
            elif rec.get("kind") == "edge":
                edges.append(rec)
    return nodes, edges


def subgraph(edge_list, nodes, extra_nodes=None):
    nids = set()
    for e in edge_list:
        nids.add(e.get("subject"))
        nids.add(e.get("object"))
    for nid in (extra_nodes or []):
        nids.add(nid)
    return {
        "nodes": [nodes[i] for i in sorted(nids) if i in nodes],
        "edges": edge_list,
        "evidence": [{"edge_id": e.get("edge_id"),
                      "source_id": ev.get("source_id"),
                      "paragraph_id": ev.get("paragraph_id"),
                      "quote": ev.get("quote")}
                     for e in edge_list for ev in e.get("evidence", [])],
    }


def cond_match(edge, params):
    cond = edge.get("conditions") or {}
    for k in ("dataset", "metric", "condition"):
        if params.get(k) and cond.get(k) != params[k]:
            return False
    return True


def run_query(spec, nodes, edges, cooc):
    qt = spec.get("type")
    params = spec.get("params", {})
    if qt == "compare":
        hits = [e for e in edges
                if e.get("relation") in COMPARATIVE and cond_match(e, params)]
        conflicted = sorted({e["edge_id"] for e in hits if e.get("in_conflict")})
        return {"status": "executed", "n_results": len(hits),
                "no_global_winner": True,
                "note": "结果仅在查询给定的条件作用域内成立",
                "conflict_flags": conflicted,
                "subgraph": subgraph(hits, nodes)}
    if qt == "measurements":
        node = params.get("node")
        hits = [e for e in edges
                if e.get("subject") == node and e.get("measurement")
                and cond_match(e, params)]
        return {"status": "executed", "n_results": len(hits),
                "conflict_flags": sorted({e["edge_id"] for e in hits
                                          if e.get("in_conflict")}),
                "subgraph": subgraph(hits, nodes)}
    if qt == "direct_relation":
        s, o = params.get("subject"), params.get("object")
        hits = [e for e in edges
                if {e.get("subject"), e.get("object")} == {s, o}]
        if hits:
            return {"status": "executed", "answer": "direct_relation_exists",
                    "n_results": len(hits), "subgraph": subgraph(hits, nodes)}
        cooc_hits = [c for c in cooc
                     if {s, o} <= set(c.get("nodes", []))]
        return {"status": "executed", "answer": "no_direct_relation",
                "n_results": 0,
                "cooccurrence_notes": cooc_hits,
                "note": "跨篇/同篇共现不是直接关系；不做无证据连边",
                "subgraph": subgraph([], nodes, extra_nodes=[s, o])}
    if qt == "neighbors":
        node = params.get("node")
        hits = [e for e in edges
                if node in (e.get("subject"), e.get("object"))]
        return {"status": "executed", "n_results": len(hits),
                "subgraph": subgraph(hits, nodes)}
    return {"status": "rejected", "reason": "unknown_query_type: %s" % qt}


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性图谱查询执行器")
    ap.add_argument("--graph", required=True, help="graph.jsonl 路径")
    ap.add_argument("--queries", required=True, help="查询规格 JSON")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    nodes, edges = load_graph(args.graph)
    spec_doc = load_json(args.queries)
    cooc = []
    graph_json = args.graph.replace("graph.jsonl", "graph.json")
    try:
        cooc = load_json(graph_json).get("cooccurrence_notes", [])
    except Exception:
        pass

    results = []
    for spec in spec_doc.get("queries", []):
        res = run_query(spec, nodes, edges, cooc)
        res["query_id"] = spec.get("query_id")
        res["question"] = spec.get("question")
        res["type"] = spec.get("type")
        results.append(res)
    n_exec = sum(1 for r in results if r.get("status") == "executed")
    dump_json({"executor": "query_run.py (deterministic, stdlib)",
               "n_queries": len(results), "n_executed": n_exec,
               "results": results}, args.out)
    print("queries: executed=%d/%d -> %s" % (n_exec, len(results), args.out))
    return 0 if n_exec >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
