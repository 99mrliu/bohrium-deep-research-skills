#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_query.py — 查询执行器。

支持两种方式：
1. 批量：--spec query-specs.json（查询清单）+ --baseline/--current 图，
   逐条真实执行并把结果与证据写入 queries.json；
2. 单次：--graph G --op find_nodes --args '{"type":"material"}' 直接打印。

查询算子：find_nodes / find_edges / neighbors / evidence / conflicts /
node_history / diff_summary。所有结果内联 evidence（source_id +
paragraph_id + 原文短引），保证"查得到、回得去"。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_common as K
import kg_diff as D


def _match_label(text, sub):
    return K.norm_label(sub) in K.norm_label(text)


def op_find_nodes(g, args):
    out = []
    for n in g.get("nodes", []):
        if n.get("status") == "merged":
            continue
        if args.get("type") and n.get("type") != args["type"]:
            continue
        if args.get("label_contains"):
            hay = [n.get("label", "")] + [
                a.get("label", "") if isinstance(a, dict) else str(a)
                for a in n.get("aliases", [])]
            if not any(_match_label(h, args["label_contains"]) for h in hay):
                continue
        out.append(K.node_summary(n))
    return out


def op_find_edges(g, args):
    res = K.build_resolver(g)

    def _ep_ok(val, want):
        if not want:
            return True
        wids = res.get(K.norm_label(want), [want])
        return val in wids
    out = []
    for e in g.get("edges", []):
        if args.get("relation") and e.get("relation") != args["relation"]:
            continue
        if not _ep_ok(e.get("from"), args.get("from")):
            continue
        if not _ep_ok(e.get("to"), args.get("to")):
            continue
        if args.get("status") and e.get("status", "active") != args["status"]:
            continue
        out.append(K.edge_summary(e))
    return out


def op_neighbors(g, args):
    nid, err = K.resolve_ref(args.get("node"), g)
    if err:
        return {"error": err}
    depth = min(int(args.get("depth", 1)), 3)
    seen_n, seen_e, frontier = {nid}, set(), {nid}
    for _ in range(depth):
        nxt = set()
        for e in g.get("edges", []):
            if e["from"] in frontier or e["to"] in frontier:
                seen_e.add(e["id"])
                for ep in (e["from"], e["to"]):
                    if ep not in seen_n:
                        nxt.add(ep)
        seen_n |= nxt
        frontier = nxt
    return {
        "center": nid,
        "nodes": [K.node_summary(K.find_node(g, i)) for i in sorted(seen_n)
                  if K.find_node(g, i)],
        "edges": [K.edge_summary(K.find_edge(g, i)) for i in sorted(seen_e)
                  if K.find_edge(g, i)],
    }


def op_evidence(g, args):
    rid = args.get("id")
    rec = K.find_node(g, rid) or K.find_edge(g, rid)
    if rec is None:
        return {"error": "图中不存在 id=%s" % rid}
    return rec


def op_conflicts(g, _args):
    groups = {}
    for e in g.get("edges", []):
        grp = e.get("conflict_group")
        if grp:
            groups.setdefault(grp, []).append(K.edge_summary(e))
    return [{"conflict_group": grp, "edges": edges,
             "note": "冲突双方并列保留，均未覆盖；以各自 evidence 回查原文"}
            for grp, edges in sorted(groups.items())]


def op_node_history(graphs, args):
    """跨版本单节点对比：展示 baseline→current 的 before/after。"""
    ref = args.get("id") or args.get("label") or args.get("node")
    out = {}
    nid = None
    for ver in ("baseline", "current"):
        g = graphs.get(ver)
        if not g:
            out[ver] = None
            continue
        rid, err = K.resolve_ref({"id": ref} if str(ref).startswith(("n_", "e_"))
                                 else {"label": ref}, g)
        if err:
            out[ver] = None
            continue
        nid = nid or rid
        out[ver] = K.find_node(g, rid)
    if nid is None:
        return {"error": "两个版本中都找不到 %r" % ref}
    b, c = out.get("baseline"), out.get("current")
    changed = []
    if b and c:
        for k in sorted((set(b) | set(c)) - {"history"}):
            if b.get(k) != c.get(k):
                changed.append(k)
    return {"node_id": nid, "baseline": b, "current": c,
            "changed_fields": changed,
            "note": "同一稳定 ID 的 before/after；baseline 为封存版本"}


def op_diff_summary(graphs, _args):
    if not graphs.get("baseline") or not graphs.get("current"):
        return {"error": "需要同时提供 baseline 与 current 图"}
    d = D.diff_graphs(graphs["baseline"], graphs["current"])
    return {"summary": d["summary"],
            "added_node_ids": [n["id"] for n in d["added_nodes"]],
            "added_edge_ids": [e["id"] for e in d["added_edges"]],
            "changed_node_ids": [c["id"] for c in d["changed_nodes"]],
            "changed_edge_ids": [c["id"] for c in d["changed_edges"]],
            "conflicts": d["conflicts"],
            "removed": d["removed_node_ids"] + d["removed_edge_ids"]}


def run_query(q, graphs):
    which = q.get("graph", "current")
    op = q.get("op")
    args = q.get("args") or {}
    if op in ("node_history", "diff_summary"):
        result = {"node_history": op_node_history, "diff_summary": op_diff_summary}[op](
            graphs, args)
        count = 1 if "error" not in result else 0
    else:
        g = graphs.get(which)
        if g is None:
            return {"error": "版本 %s 的图不存在" % which}, 0
        fn = {"find_nodes": op_find_nodes, "find_edges": op_find_edges,
              "neighbors": op_neighbors, "evidence": op_evidence,
              "conflicts": op_conflicts}[op]
        result = fn(g, args)
        count = (len(result) if isinstance(result, list)
                 else (0 if isinstance(result, dict) and "error" in result else 1))
    return result, count


def main(argv=None):
    ap = argparse.ArgumentParser(description="图谱查询执行器")
    ap.add_argument("--baseline", help="baseline 图（graph-v1.json）")
    ap.add_argument("--current", help="当前图（graph-v2.json，缺省回退 baseline）")
    ap.add_argument("--graph", help="单次查询模式：图文件")
    ap.add_argument("--spec", help="查询清单 JSON（批量真实执行）")
    ap.add_argument("--out", help="queries.json 输出路径")
    ap.add_argument("--op", help="单次查询算子")
    ap.add_argument("--args", help="单次查询参数 JSON 字符串", default="{}")
    args = ap.parse_args(argv)

    graphs = {}
    if args.baseline and os.path.exists(args.baseline):
        graphs["baseline"] = K.load_json(args.baseline)
    cur = args.current or args.graph
    if cur and os.path.exists(cur):
        graphs["current"] = K.load_json(cur)
    if "current" not in graphs and "baseline" in graphs:
        graphs["current"] = graphs["baseline"]

    if args.op:  # 单次模式
        g = graphs.get("current")
        if g is None:
            print("ERROR: 需要 --graph/--current", file=sys.stderr)
            return 2
        qargs = json.loads(args.args)
        result, _ = run_query({"graph": "current", "op": args.op, "args": qargs},
                              graphs)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not args.spec:
        print("ERROR: 需要 --spec 或 --op", file=sys.stderr)
        return 2
    spec = K.load_json(args.spec)
    queries = []
    for q in spec.get("queries", []):
        result, count = run_query(q, graphs)
        queries.append({
            "name": q.get("name"), "question": q.get("question"),
            "graph": q.get("graph", "current"), "op": q.get("op"),
            "args": q.get("args") or {},
            "executed": True, "result_count": count, "results": result,
        })
    doc = {"schema": K.SCHEMA_QUERIES,
           "case_id": (graphs.get("current") or graphs.get("baseline") or {}).get(
               "case_id"),
           "synthetic": bool(spec.get("synthetic")),
           "versions_queried": sorted(graphs.keys()),
           "queries": queries}
    if args.out:
        K.dump_json(doc, args.out)
    print("已真实执行 %d 个查询（版本: %s）"
          % (len(queries), ",".join(sorted(graphs.keys()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
