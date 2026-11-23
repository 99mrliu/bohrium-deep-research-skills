#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_graph.py — 确定性查询执行器。

支持三类真实查询（结果子图均携带完整证据，排序与遍历完全确定）：

1. neighborhood：节点邻域
   {"type":"neighborhood","node":"n_method_fc","hops":1}
   以无向 BFS 取 hops 层内全部节点及它们之间的边。
2. by-type：按类型（可选按来源）筛选
   {"type":"by-type","kind":"metric","source_id":"S1"  // source_id 可选}
   返回 kind 匹配的节点；给 source_id 时仅保留证据覆盖该源的节点。
   边为结果节点集合内部的边。
3. path：两节点间最短连接路径
   {"type":"path","from":"n_paper_p1","to":"n_paper_s1"}
   无向 BFS 最短路径，邻接点按 node_id 升序、并行边按 edge_id 升序，
   保证同一图同一查询结果逐字节稳定。不可达时返回空子图并注明。

CLI：
  单条：python3 query_graph.py --graph graph.json --query neighborhood \
        --node n_method_fc --hops 1
  批量：python3 query_graph.py --graph graph.json \
        --batch query_specs.json --out queries.json
  批量输入接受：列表 [{query_id, query:{...}}]、{"queries":[...]}、
  或 case.json（自动读取其中 query_specs 字段）。
"""

from __future__ import annotations

import argparse
import json
import sys

import kgcommon as k


class GraphIndex:
    def __init__(self, graph):
        self.nodes = {n["node_id"]: n for n in graph.get("nodes", [])}
        self.edges = {e["edge_id"]: e for e in graph.get("edges", [])}
        # 无向邻接：node_id -> [(neighbor_id, edge_id), ...] 确定性排序
        adj = {}
        for e in graph.get("edges", []):
            s, o = e.get("subject"), e.get("object")
            if s not in self.nodes or o not in self.nodes:
                continue
            adj.setdefault(s, []).append((o, e["edge_id"]))
            adj.setdefault(o, []).append((s, e["edge_id"]))
        self.adj = {nid: sorted(v) for nid, v in adj.items()}

    def neighbors(self, nid):
        return self.adj.get(nid, [])


def _subgraph(idx, node_ids, edge_ids, note=None):
    nodes = [idx.nodes[i] for i in sorted(node_ids) if i in idx.nodes]
    edges = [idx.edges[i] for i in sorted(edge_ids) if i in idx.edges]
    result = {"nodes": nodes, "edges": edges}
    if note:
        result["note"] = note
    return result


def q_neighborhood(idx, params):
    start = params.get("node")
    hops = int(params.get("hops", 1))
    if start not in idx.nodes:
        return _subgraph(idx, [], [], note=f"起点节点 '{start}' 不存在")
    seen = {start}
    frontier = {start}
    edge_ids = set()
    for _ in range(hops):
        nxt = set()
        for nid in sorted(frontier):
            for nbr, eid in idx.neighbors(nid):
                edge_ids.add(eid)
                if nbr not in seen:
                    seen.add(nbr)
                    nxt.add(nbr)
        frontier = nxt
        if not frontier:
            break
    # 补齐结果节点集合内部的全部边
    for e in idx.edges.values():
        if e["subject"] in seen and e["object"] in seen:
            edge_ids.add(e["edge_id"])
    return _subgraph(idx, seen, edge_ids)


def q_by_type(idx, params):
    kind = params.get("kind")
    sid = params.get("source_id")
    node_ids = set()
    for nid, node in idx.nodes.items():
        if kind and node.get("kind") != kind:
            continue
        if sid and sid not in (node.get("source_ids") or []):
            continue
        node_ids.add(nid)
    edge_ids = {eid for eid, e in idx.edges.items()
                if e["subject"] in node_ids and e["object"] in node_ids}
    note = None
    if not node_ids:
        note = "无匹配节点（如实返回空子图）"
    return _subgraph(idx, node_ids, edge_ids, note=note)


def q_path(idx, params):
    src, dst = params.get("from"), params.get("to")
    for label, nid in (("from", src), ("to", dst)):
        if nid not in idx.nodes:
            return _subgraph(idx, [], [], note=f"端点 {label}='{nid}' 不存在")
    # 无向 BFS，确定性邻接顺序
    prev = {src: None}  # nid -> (prev_nid, edge_id)
    queue = [src]
    while queue:
        nid = queue.pop(0)
        if nid == dst:
            break
        for nbr, eid in idx.neighbors(nid):
            if nbr not in prev:
                prev[nbr] = (nid, eid)
                queue.append(nbr)
    if dst not in prev:
        return _subgraph(idx, [], [], note=f"'{src}' 与 '{dst}' 之间不可达")
    node_ids, edge_ids = set(), set()
    cur = dst
    while cur != src:
        node_ids.add(cur)
        p, eid = prev[cur]
        edge_ids.add(eid)
        cur = p
    node_ids.add(src)
    result = _subgraph(idx, node_ids, edge_ids)
    result["path_length_edges"] = len(edge_ids)
    return result


QUERY_TYPES = {
    "neighborhood": q_neighborhood,
    "by-type": q_by_type,
    "path": q_path,
}


def run_query(graph, query):
    idx = GraphIndex(graph)
    qtype = query.get("type")
    fn = QUERY_TYPES.get(qtype)
    if fn is None:
        return {"ok": False, "error": f"未知查询类型 {qtype!r}，支持 {sorted(QUERY_TYPES)}"}
    result = fn(idx, query)
    return {
        "ok": True,
        "result": result,
        "summary": {"node_count": len(result["nodes"]), "edge_count": len(result["edges"])},
    }


def _extract_batch(raw):
    """容忍批量输入的多种包装形态。"""
    if isinstance(raw, dict) and isinstance(raw.get("query_specs"), list):
        raw = raw["query_specs"]  # case.json 形态
    elif isinstance(raw, dict) and isinstance(raw.get("queries"), list):
        raw = raw["queries"]
    if not isinstance(raw, list):
        raise ValueError("批量查询输入不可识别")
    out = []
    for i, item in enumerate(raw):
        if isinstance(item, dict) and "query" in item:
            out.append({"query_id": item.get("query_id", f"q{i+1}"), "query": item["query"]})
        elif isinstance(item, dict):
            qid = item.pop("query_id", f"q{i+1}")
            out.append({"query_id": qid, "query": item})
        else:
            raise ValueError(f"第 {i} 条查询不是对象")
    return out


def run_batch(graph, specs):
    results = []
    for spec in specs:
        r = run_query(graph, spec["query"])
        results.append({
            "query_id": spec["query_id"],
            "type": spec["query"].get("type"),
            "params": {kk: vv for kk, vv in spec["query"].items() if kk != "type"},
            "ok": r.get("ok", False),
            "summary": r.get("summary"),
            "result": r.get("result"),
            "error": r.get("error"),
        })
    return {"format": k.FORMAT_QUERIES, "queries": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性图谱查询执行器")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--query", choices=sorted(QUERY_TYPES), help="单条查询类型")
    ap.add_argument("--node", help="neighborhood：起点节点")
    ap.add_argument("--hops", type=int, default=1, help="neighborhood：层数（默认 1）")
    ap.add_argument("--kind", help="by-type：节点类型")
    ap.add_argument("--source-id", default=None, help="by-type：限定证据来源（可选）")
    ap.add_argument("--from", dest="from_", help="path：起点")
    ap.add_argument("--to", dest="to", help="path：终点")
    ap.add_argument("--batch", help="批量查询 JSON（列表/包装/case.json）")
    ap.add_argument("--out", help="输出 JSON 路径；缺省打印到 stdout")
    args = ap.parse_args(argv)

    graph = k.read_json(args.graph)
    if args.batch:
        specs = _extract_batch(k.read_json(args.batch))
        payload = run_batch(graph, specs)
    else:
        if not args.query:
            ap.error("必须指定 --query 或 --batch")
        params = {"type": args.query}
        if args.query == "neighborhood":
            params.update({"node": args.node, "hops": args.hops})
        elif args.query == "by-type":
            params.update({"kind": args.kind})
            if args.source_id:
                params["source_id"] = args.source_id
        elif args.query == "path":
            params.update({"from": args.from_, "to": args.to})
        r = run_query(graph, params)
        payload = {"format": k.FORMAT_QUERIES, "queries": [{
            "query_id": "adhoc", "type": args.query,
            "params": {kk: vv for kk, vv in params.items() if kk != "type"},
            "ok": r.get("ok", False), "summary": r.get("summary"),
            "result": r.get("result"), "error": r.get("error"),
        }]}

    if args.out:
        k.write_json(args.out, payload)
        n_ok = sum(1 for q in payload["queries"] if q["ok"])
        print(f"[query_graph] executed={len(payload['queries'])} ok={n_ok} -> {args.out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    failed = [q for q in payload["queries"] if not q["ok"]]
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
