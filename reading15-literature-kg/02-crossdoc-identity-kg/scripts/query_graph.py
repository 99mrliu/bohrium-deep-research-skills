# -*- coding: utf-8 -*-
"""图谱查询执行器（确定性，仅标准库）。

支持至少三类真实执行的查询：
- neighbors：某节点的一跳邻居（含方向与证据）；
- filter：按实体类型 / 来源 / 谓词过滤节点或边；
- path：两节点间无向最短路径（BFS），展示跨篇合并带来的连通性。
每个查询返回 status / result / evidence，无法解析或无结果时如实报告。
"""
from normalize import normalize_surface


def _resolve_node(graph, node_id=None, node_name=None):
    """按 ID 或名称（含别名，规范化匹配）解析节点；多义时返回候选列表。"""
    if node_id:
        for n in graph["nodes"]:
            if n["id"] == node_id:
                return n, []
        return None, []
    if node_name is not None:
        key = normalize_surface(node_name)
        hits = [n for n in graph["nodes"]
                if normalize_surface(n.get("name")) == key
                or key in {normalize_surface(a) for a in n.get("aliases", [])}]
        if len(hits) == 1:
            return hits[0], []
        return (hits[0] if hits else None), hits if len(hits) > 1 else []
    return None, []


def _adjacency(graph):
    adj = {}
    for e in graph["edges"]:
        adj.setdefault(e["subject"], []).append((e["object"], e))
        adj.setdefault(e["object"], []).append((e["subject"], e))
    return adj


def q_neighbors(graph, node_id=None, node_name=None):
    node, ambiguous = _resolve_node(graph, node_id, node_name)
    if node is None:
        return {"status": "no_result",
                "result": None,
                "note": "节点无法解析" + ("（多义候选：%s）" % ", ".join(
                    a["id"] for a in ambiguous) if ambiguous else "")}
    adj = _adjacency(graph)
    by_id = {n["id"]: n for n in graph["nodes"]}
    items = []
    for other, edge in adj.get(node["id"], []):
        direction = "out" if edge["subject"] == node["id"] else "in"
        items.append({
            "neighbor": other,
            "neighbor_name": by_id.get(other, {}).get("name"),
            "predicate": edge["predicate"],
            "direction": direction,
            "edge_id": edge["id"],
            "evidence": edge["evidence"],
        })
    return {"status": "ok",
            "result": {"node": node["id"], "name": node["name"],
                       "neighbors": items},
            "evidence": [e for it in items for e in it["evidence"]]}


def q_filter(graph, entity_type=None, predicate=None, source_id=None,
             identity_status=None):
    nodes = [n for n in graph["nodes"]
             if (entity_type is None or n.get("entity_type") == entity_type)
             and (identity_status is None
                  or n.get("identity_status") == identity_status)
             and (source_id is None or any(
                 s.get("source_id") == source_id
                 for s in n.get("sources", [])))]
    edges = [e for e in graph["edges"]
             if (predicate is None or e.get("predicate") == predicate)
             and (source_id is None or any(
                 ev.get("source_id") == source_id
                 for ev in e.get("evidence", [])))]
    return {"status": "ok" if (nodes or edges) else "no_result",
            "result": {
                "nodes": [{"id": n["id"], "name": n["name"],
                           "entity_type": n["entity_type"],
                           "identity_status": n["identity_status"],
                           "sources": n["sources"]} for n in nodes],
                "edges": [{"id": e["id"], "subject": e["subject"],
                           "predicate": e["predicate"], "object": e["object"],
                           "evidence": e["evidence"]} for e in edges],
            },
            "evidence": [ev for e in edges for ev in e["evidence"]]}


def q_path(graph, start_name=None, end_name=None, start_id=None, end_id=None):
    start, amb1 = _resolve_node(graph, start_id, start_name)
    end, amb2 = _resolve_node(graph, end_id, end_name)
    if start is None or end is None:
        return {"status": "no_result", "result": None,
                "note": "起点或终点无法解析"}
    adj = _adjacency(graph)
    prev = {start["id"]: None}
    queue = [start["id"]]
    while queue:
        cur = queue.pop(0)
        if cur == end["id"]:
            break
        for nxt, edge in adj.get(cur, []):
            if nxt not in prev:
                prev[nxt] = (cur, edge)
                queue.append(nxt)
    if end["id"] not in prev:
        return {"status": "no_path",
                "result": None,
                "note": "两节点间不存在路径（如 KEEP_DISTINCT 保持分离时属预期）"}
    chain, ev = [], []
    cur = end["id"]
    by_id = {n["id"]: n for n in graph["nodes"]}
    while cur is not None:
        chain.append({"id": cur, "name": by_id.get(cur, {}).get("name")})
        if prev[cur] is None:
            break
        cur, edge = prev[cur]
        ev.extend(edge["evidence"])
    chain.reverse()
    return {"status": "ok",
            "result": {"path": chain, "length": len(chain) - 1},
            "evidence": ev}


_DISPATCH = {"neighbors": q_neighbors, "filter": q_filter, "path": q_path}


def run_queries(graph, specs):
    """逐条执行查询规格，返回带证据的结果列表（不抛异常，失败如实记录）。"""
    results = []
    for i, spec in enumerate(specs, start=1):
        qtype = spec.get("type")
        fn = _DISPATCH.get(qtype)
        entry = {"query_id": spec.get("query_id") or "Q%d" % i,
                 "spec": spec}
        if fn is None:
            entry.update({"status": "unsupported_query_type", "result": None})
        else:
            kwargs = {k: v for k, v in spec.items()
                      if k not in ("type", "query_id", "description")}
            try:
                entry.update(fn(graph, **kwargs))
            except Exception as exc:  # 容错：单个查询失败不影响其余
                entry.update({"status": "error", "result": None,
                              "note": "%s: %s" % (type(exc).__name__, exc)})
        results.append(entry)
    return results
