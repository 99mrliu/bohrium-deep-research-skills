#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_diff.py — 基于稳定 ID 的版本差异器。

按 ID 对齐 baseline 与 current：新增节点/边、字段级变化（before/after）、
冲突组清单。若发现 baseline 记录消失（删除/改号）则以退出码 2 报警——
本工作流的增量语义不允许任何记录消失。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_common as K

IGNORE_FIELDS = {"history"}  # history 只追加，字段级对比时单列


def _index(records):
    return {r["id"]: r for r in records}


def _field_changes(before, after):
    diffs = []
    for k in sorted((set(before) | set(after)) - IGNORE_FIELDS):
        bv, av = before.get(k), after.get(k)
        if bv != av:
            diffs.append({"field": k, "before": bv, "after": av})
    return diffs


def diff_graphs(gb, gc):
    nb, nc = _index(gb.get("nodes", [])), _index(gc.get("nodes", []))
    eb, ec = _index(gb.get("edges", [])), _index(gc.get("edges", []))
    added_nodes = [K.node_summary(nc[i]) for i in sorted(set(nc) - set(nb))]
    added_edges = [K.edge_summary(ec[i]) for i in sorted(set(ec) - set(eb))]
    removed_nodes = sorted(set(nb) - set(nc))
    removed_edges = sorted(set(eb) - set(ec))
    changed_nodes = [{"id": i, "changes": _field_changes(nb[i], nc[i])}
                     for i in sorted(set(nb) & set(nc))
                     if _field_changes(nb[i], nc[i])]
    changed_edges = [{"id": i, "changes": _field_changes(eb[i], ec[i])}
                     for i in sorted(set(eb) & set(ec))
                     if _field_changes(eb[i], ec[i])]
    conflicts = {}
    for e in gc.get("edges", []):
        grp = e.get("conflict_group")
        if grp:
            conflicts.setdefault(grp, []).append(e["id"])
    return {
        "schema": "kg-diff/1",
        "case_id": gc.get("case_id") or gb.get("case_id"),
        "baseline_version": gb.get("version"),
        "current_version": gc.get("version"),
        "summary": {
            "nodes_baseline": len(nb), "nodes_current": len(nc),
            "edges_baseline": len(eb), "edges_current": len(ec),
            "added_nodes": len(added_nodes), "added_edges": len(added_edges),
            "removed_nodes": len(removed_nodes), "removed_edges": len(removed_edges),
            "changed_nodes": len(changed_nodes), "changed_edges": len(changed_edges),
            "conflict_groups": len(conflicts),
        },
        "added_nodes": added_nodes, "added_edges": added_edges,
        "removed_node_ids": removed_nodes, "removed_edge_ids": removed_edges,
        "changed_nodes": changed_nodes, "changed_edges": changed_edges,
        "conflicts": [{"conflict_group": g, "edge_ids": sorted(ids)}
                      for g, ids in sorted(conflicts.items())],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="稳定 ID 版本差异器")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--out", help="diff JSON 输出路径")
    args = ap.parse_args(argv)
    gb = K.load_json(args.baseline)
    gc = K.load_json(args.current)
    d = diff_graphs(gb, gc)
    if args.out:
        K.dump_json(d, args.out)
    print(json.dumps(d["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if d["removed_node_ids"] or d["removed_edge_ids"]:
        print("VIOLATION: baseline 记录在 current 中消失（删除或改号）: nodes=%s edges=%s"
              % (d["removed_node_ids"], d["removed_edge_ids"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
