#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_engine.py — 确定性图谱查询引擎（仅标准库）。

支持的算子（JSON 查询 DSL，详见 references/query-dsl.md）：
  node_lookup      按名称/别名查节点（含证据）
  neighborhood     邻域查询：depth / relation / direction / types 过滤
  shortest_path    两节点间最短路径（BFS，支持 relation/direction/max_depth）
  cross_source     某节点的证据是否来自 >=2 个不同 source_id（跨篇证据）
  merge_decisions  列出合并/不合并决策及依据

诚实性约定：
  * 未知算子 → status="error", error="unknown_operator"，绝不静默返回空；
  * 节点不存在/路径不可达/无跨源证据 → status="empty"，并给出 reason；
  * 每个结果都带 explain（关系匹配方式、过滤条件、命中数），可人工复算；
  * 结果不含时间戳，result_hash 由内容唯一决定（确定性）。
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_loader import GraphLoadError, load_graph  # noqa: E402

OPERATORS = ("node_lookup", "neighborhood", "shortest_path", "cross_source", "merge_decisions")


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def result_hash(payload):
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()


def _node_view(g, nid, with_evidence=True):
    n = g.nodes[nid]
    v = {"id": nid, "type": n["type"], "name": n["name"],
         "aliases": n.get("aliases", [])}
    if with_evidence:
        v["evidence"] = n.get("evidence", [])
    return v


def _edge_view(g, eid, with_evidence=True):
    e = g.edges[eid]
    v = {"id": eid, "src": e["src"], "dst": e["dst"], "relation": e["relation"]}
    if e.get("conditions"):
        v["conditions"] = e["conditions"]
    if with_evidence:
        v["evidence"] = e.get("evidence", [])
    return v


def _relation_explain(relations):
    if not relations:
        return "未限定关系：所有关系类型均匹配。"
    return ("关系过滤：边的 relation 经去空白、小写化后与列表 %s 做精确匹配（OR 语义）。"
            % json.dumps(relations, ensure_ascii=False))


def _resolve_node(g, params, key="node"):
    """解析节点参数：优先 id（存在校验），否则按名称/别名查。返回 (nid, note)。"""
    val = params.get(key)
    if not isinstance(val, str) or not val.strip():
        return None, "参数 %s 缺失或不是非空字符串" % key
    val = val.strip()
    if val in g.nodes:
        return val, "按节点 id 直接命中"
    nid = g.find_node(val)
    if nid:
        return nid, "按名称/别名 %r 解析到 %s" % (val, nid)
    return None, "图中不存在 id 或名称/别名为 %r 的节点" % val


def op_node_lookup(g, params):
    name = params.get("name")
    explain = {"match_rule": "name 与 aliases 去空白、小写化后精确匹配；不做模糊/语义扩展。"}
    nid = g.find_node(name) if isinstance(name, str) else None
    if not nid:
        return {"status": "empty", "reason": "未找到名称/别名为 %r 的节点（空结果，如实报告）" % (name,),
                "matches": [], "explain": explain}
    explain["hit"] = "%r → %s" % (name, nid)
    return {"status": "ok", "matches": [_node_view(g, nid)], "explain": explain}


def op_neighborhood(g, params):
    nid, note = _resolve_node(g, params)
    explain = {"node_resolution": note, "relation_rule": _relation_explain(params.get("relation")),
               "direction": params.get("direction", "out"),
               "type_filter": params.get("types") or "未限定",
               "depth": params.get("depth", 1)}
    if not nid:
        return {"status": "empty", "reason": note, "matches": {"nodes": [], "edges": []},
                "explain": explain}
    try:
        depth = int(params.get("depth", 1))
    except (TypeError, ValueError):
        return {"status": "error", "error": "bad_param",
                "detail": "depth 必须是整数", "explain": explain}
    depth = max(0, min(depth, 8))
    direction = params.get("direction", "out")
    if direction not in ("out", "in", "any"):
        return {"status": "error", "error": "bad_param",
                "detail": "direction 必须是 out/in/any", "explain": explain}
    relations = params.get("relation")
    if isinstance(relations, str):
        relations = [relations]
    types = params.get("types")
    if isinstance(types, str):
        types = [types]
    seen_nodes = {nid: 0}
    seen_edges = set()
    frontier = [nid]
    for d in range(1, depth + 1):
        nxt = []
        for cur in frontier:
            for eid, other in g.neighbors(cur, relations=relations,
                                          direction=direction, types=types):
                seen_edges.add(eid)
                if other not in seen_nodes:
                    seen_nodes[other] = d
                    nxt.append(other)
        frontier = nxt
    nodes = [_node_view(g, n) for n in sorted(seen_nodes)]
    edges = [_edge_view(g, e) for e in sorted(seen_edges)]
    explain["hit_counts"] = {"nodes": len(nodes), "edges": len(edges)}
    if not edges and len(nodes) == 1:
        return {"status": "empty",
                "reason": "节点 %s 在给定过滤条件下没有任何匹配邻边（空结果，如实报告）" % nid,
                "matches": {"nodes": nodes, "edges": []}, "explain": explain}
    return {"status": "ok", "matches": {"nodes": nodes, "edges": edges}, "explain": explain}


def op_shortest_path(g, params):
    src, note_s = _resolve_node(g, params, key="from")
    dst, note_d = _resolve_node(g, params, key="to")
    relations = params.get("relation")
    if isinstance(relations, str):
        relations = [relations]
    direction = params.get("direction", "any")
    if direction not in ("out", "in", "any"):
        return {"status": "error", "error": "bad_param", "detail": "direction 必须是 out/in/any"}
    try:
        max_depth = int(params.get("max_depth", 8))
    except (TypeError, ValueError):
        return {"status": "error", "error": "bad_param", "detail": "max_depth 必须是整数"}
    explain = {"from_resolution": note_s, "to_resolution": note_d,
               "relation_rule": _relation_explain(relations),
               "direction": direction, "max_depth": max_depth,
               "algorithm": "BFS（按 edge_id 排序展开，确定性最短路径）"}
    if not src:
        return {"status": "empty", "reason": "起点缺失：" + note_s, "path": None, "explain": explain}
    if not dst:
        return {"status": "empty", "reason": "终点缺失：" + note_d, "path": None, "explain": explain}
    if src == dst:
        return {"status": "ok", "path": {"nodes": [_node_view(g, src, False)], "edges": [],
                                         "length": 0}, "explain": explain}
    # BFS
    prev = {src: None}  # node -> (prev_node, edge_id)
    frontier = [src]
    for _ in range(max_depth):
        nxt = []
        for cur in frontier:
            for eid, other in g.neighbors(cur, relations=relations, direction=direction):
                if other in prev:
                    continue
                prev[other] = (cur, eid)
                if other == dst:
                    nxt = []
                    break
                nxt.append(other)
            if dst in prev:
                break
        if dst in prev:
            break
        frontier = nxt
        if not frontier:
            break
    if dst not in prev:
        return {"status": "empty",
                "reason": "在 max_depth=%d、direction=%s、关系过滤=%s 下，%s 与 %s 之间不存在路径"
                          "（可能不连通或过滤过严；空结果，如实报告）"
                          % (max_depth, direction, relations or "无", src, dst),
                "path": None, "explain": explain}
    # 回溯
    nodes_rev, edges_rev = [], []
    cur = dst
    while cur is not None:
        nodes_rev.append(cur)
        p = prev[cur]
        if p:
            edges_rev.append(p[1])
            cur = p[0]
        else:
            cur = None
    nodes = list(reversed(nodes_rev))
    edges = list(reversed(edges_rev))
    explain["path_length"] = len(edges)
    return {"status": "ok",
            "path": {"nodes": [_node_view(g, n, False) for n in nodes],
                     "edges": [_edge_view(g, e) for e in edges],
                     "length": len(edges)},
            "explain": explain}


def op_cross_source(g, params):
    nid, note = _resolve_node(g, params)
    explain = {"node_resolution": note,
               "rule": "汇总节点自身证据与其所有关联边证据中的 source_id，"
                       "统计不同来源数；>=2 视为具备跨源证据。"}
    if not nid:
        return {"status": "empty", "reason": note, "sources": [], "explain": explain}
    srcs = g.evidence_sources(nid)
    explain["distinct_sources"] = srcs
    if len(srcs) < 2:
        return {"status": "empty",
                "reason": "节点 %s 的证据只来自 %d 个来源（%s），不构成跨源证据（如实报告）"
                          % (nid, len(srcs), "、".join(srcs) or "无"),
                "sources": srcs, "explain": explain}
    per_source = {}
    for ev in g.nodes[nid].get("evidence", []):
        per_source.setdefault(ev["source_id"], []).append(ev)
    for eid in g.out_adj.get(nid, []) + g.in_adj.get(nid, []):
        for ev in g.edges[eid].get("evidence", []):
            per_source.setdefault(ev["source_id"], []).append(
                dict(ev, via_edge=eid))
    return {"status": "ok", "node": _node_view(g, nid), "sources": srcs,
            "evidence_by_source": {k: per_source[k] for k in sorted(per_source)},
            "explain": explain}


def op_merge_decisions(g, params):
    which = params.get("decision", "all")
    if which not in ("all", "merge", "no_merge"):
        return {"status": "error", "error": "bad_param",
                "detail": "decision 必须是 all/merge/no_merge"}
    ds = [d for d in g.merge_decisions if which == "all" or d.get("decision") == which]
    ds = sorted(ds, key=lambda d: d.get("id", ""))
    explain = {"filter": which, "hit": len(ds),
               "rule": "merge=跨篇同一概念已合并为 canonical_node（含依据）；"
                       "no_merge=同名/相似但不得合并（不同样品/条件/指标/对象，含依据）。"}
    if not ds:
        return {"status": "empty", "reason": "没有 decision=%s 的合并决策记录" % which,
                "decisions": [], "explain": explain}
    return {"status": "ok", "decisions": ds, "explain": explain}


DISPATCH = {
    "node_lookup": op_node_lookup,
    "neighborhood": op_neighborhood,
    "shortest_path": op_shortest_path,
    "cross_source": op_cross_source,
    "merge_decisions": op_merge_decisions,
}


def run_query(g, query):
    """执行单条查询，返回带 status/explain/result_hash 的结果对象。"""
    qid = query.get("id", "<无id查询>")
    op = query.get("op")
    params = query.get("params", {})
    if op not in DISPATCH:
        return {"id": qid, "op": op, "status": "error", "error": "unknown_operator",
                "detail": "算子 %r 未实现；支持的算子：%s。拒绝执行，而不是返回空结果。"
                          % (op, "、".join(OPERATORS)),
                "query_hash": result_hash(query)}
    res = DISPATCH[op](g, params)
    res["id"] = qid
    res["op"] = op
    res["params"] = params
    res["query_hash"] = result_hash(query)
    res["result_hash"] = result_hash({k: v for k, v in res.items() if k != "result_hash"})
    return res


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="单条/整组图谱查询")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--queries", required=True, help="queries.json（{queries:[...]}）")
    ap.add_argument("--out", default=None, help="查询结果输出路径")
    args = ap.parse_args(argv)
    try:
        g = load_graph(args.graph)
    except GraphLoadError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    with open(args.queries, "r", encoding="utf-8") as f:
        qs = json.load(f).get("queries", [])
    results = [run_query(g, q) for q in qs]
    payload = {"results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
