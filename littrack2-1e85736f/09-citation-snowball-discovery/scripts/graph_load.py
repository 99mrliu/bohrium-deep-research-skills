#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_load.py — 加载保留参考图谱（retained reference graph）。

仅使用 Python3 标准库，完全离线。支持两类布局（详见 references/graph-layout.md）：

1. nodes/edges 布局：
   {"nodes": [{"id": ..., ...}, ...] 或 {"<id>": {...}, ...},
    "edges": [{"source": ..., "target": ..., "id"?: ..., "relation"?: ...}, ...]}
   约定边 source -> target 表示 "source 引用 target"（backward 方向）。
   若边带 "relation": "cited_by"，则视作反向声明，加载时翻转。

2. adjacency 布局：
   {"adjacency": {"A": ["B", ...], ...},            # A 引用 B
    "cited_by": {"A": ["X", ...], ...} (可选),      # X 引用 A
    "node_records": {"<id>": {...}} (可选)}         # 节点元数据

每个节点/边都带 locator（文件内 JSON 指针），供结果回溯。
"""
import json
import sys


class GraphError(Exception):
    pass


class Graph:
    def __init__(self, path):
        self.path = path
        self.layout = None
        self.nodes = {}  # id -> {"record": dict, "locator": str}
        self.edges = []  # [{"id","source","target","locator"}]，source 引用 target

    def backward_edges(self, node_id):
        """node_id 的参考文献方向边（node_id 是 source）。"""
        return [e for e in self.edges if e["source"] == node_id]

    def forward_edges(self, node_id):
        """引用 node_id 的方向边（node_id 是 target）。"""
        return [e for e in self.edges if e["target"] == node_id]

    def summary(self):
        return {
            "path": self.path,
            "layout": self.layout,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise GraphError("图谱文件不存在: %s" % path)
    except json.JSONDecodeError as e:
        raise GraphError("图谱文件不是合法 JSON: %s (%s)" % (path, e))


def _load_nodes_edges(g, data):
    g.layout = "nodes/edges"
    nodes = data.get("nodes", [])
    if isinstance(nodes, dict):
        for nid, rec in nodes.items():
            g.nodes[str(nid)] = {"record": rec if isinstance(rec, dict) else {},
                                 "locator": "/nodes/%s" % nid}
    elif isinstance(nodes, list):
        for i, rec in enumerate(nodes):
            if not isinstance(rec, dict):
                raise GraphError("节点不是对象: /nodes/%d" % i)
            nid = rec.get("id") or rec.get("node_id") or rec.get("doi")
            if not nid:
                raise GraphError("节点缺少 id/node_id/doi: /nodes/%d" % i)
            g.nodes[str(nid)] = {"record": rec, "locator": "/nodes/%d" % i}
    else:
        raise GraphError("nodes 既不是数组也不是对象")

    edges = data.get("edges", [])
    if not isinstance(edges, list):
        raise GraphError("edges 不是数组")
    for i, rec in enumerate(edges):
        if not isinstance(rec, dict):
            raise GraphError("边不是对象: /edges/%d" % i)
        src = rec.get("source") or rec.get("from")
        tgt = rec.get("target") or rec.get("to")
        if not src or not tgt:
            raise GraphError("边缺少 source/target: /edges/%d" % i)
        src, tgt = str(src), str(tgt)
        if rec.get("relation") == "cited_by":
            src, tgt = tgt, src
        g.edges.append({
            "id": str(rec.get("id", "e%d" % i)),
            "source": src,
            "target": tgt,
            "locator": "/edges/%d" % i,
        })


def _load_adjacency(g, data):
    g.layout = "adjacency"
    records = data.get("node_records", {})
    if isinstance(records, dict):
        for nid, rec in records.items():
            g.nodes[str(nid)] = {"record": rec if isinstance(rec, dict) else {},
                                 "locator": "/node_records/%s" % nid}
    n = 0
    adj = data.get("adjacency", {})
    if not isinstance(adj, dict):
        raise GraphError("adjacency 不是对象")
    for src, targets in adj.items():
        if not isinstance(targets, list):
            raise GraphError("adjacency[%s] 不是数组" % src)
        for t in targets:
            g.edges.append({"id": "a%d" % n, "source": str(src), "target": str(t),
                            "locator": "/adjacency/%s" % src})
            n += 1
    cb = data.get("cited_by", {})
    if cb:
        if not isinstance(cb, dict):
            raise GraphError("cited_by 不是对象")
        for tgt, sources in cb.items():
            if not isinstance(sources, list):
                raise GraphError("cited_by[%s] 不是数组" % tgt)
            for s in sources:
                g.edges.append({"id": "a%d" % n, "source": str(s), "target": str(tgt),
                                "locator": "/cited_by/%s" % tgt})
                n += 1
    # adjacency 布局允许节点仅出现在边里：补空记录，locator=None 并在结果中如实体现
    for e in g.edges:
        for nid in (e["source"], e["target"]):
            g.nodes.setdefault(nid, {"record": {}, "locator": None})


def load_graph(path):
    """加载图谱文件，返回 Graph；无法识别布局时抛 GraphError。"""
    data = _read_json(path)
    if not isinstance(data, dict):
        raise GraphError("图谱顶层不是对象: %s" % path)
    g = Graph(path)
    if "nodes" in data or "edges" in data:
        _load_nodes_edges(g, data)
    elif "adjacency" in data or "cited_by" in data:
        _load_adjacency(g, data)
    else:
        raise GraphError("无法识别的图谱布局（既无 nodes/edges 也无 adjacency/cited_by）: %s" % path)
    return g


def main(argv):
    if len(argv) != 2:
        print("用法: graph_load.py <reference_graph.json>", file=sys.stderr)
        return 2
    try:
        g = load_graph(argv[1])
    except GraphError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    out = {
        "graph": g.summary(),
        "nodes": [{"id": nid, "locator": v["locator"]} for nid, v in sorted(g.nodes.items())],
        "edges": g.edges,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
