#!/usr/bin/env python3
"""build_graph.py — build the typed knowledge graph from validated ops.

Reads <work>/validation_state.json (produced by validate_ontology.py) and
applies merge ops (union-find, keep-id wins), producing a deterministic
typed graph plus the merge ledger and nonmerge registry required by the
runtime contract.

Usage:
    python3 build_graph.py --work /app/work

Outputs under <work>:
    graph.json        nodes/edges with types, qualifiers, polarity, evidence
    merge_ledger.json accepted merges (keep/drop, types, reason, evidence)
    nonmerge_registry.json explicit non-merges with reasons

Python 3 standard library only. Deterministic: all lists sorted.
"""
import argparse
import json
import os
import sys


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build typed graph from validated ops.")
    parser.add_argument("--work", required=True)
    args = parser.parse_args(argv)

    state = load_json(os.path.join(args.work, "validation_state.json"))
    if state is None:
        print("FATAL: validation_state.json missing; run validate_ontology.py first",
              file=sys.stderr)
        return 2

    nodes = state["nodes"]
    edges = state["edges"]
    merges = state["merges"]
    nonmerges = state["nonmerges"]

    uf = UnionFind()
    for nid in nodes:
        uf.find(nid)
    ledger = []
    for m in merges:
        keep, drop = m["keep"], m["drop"]
        uf.union(keep, drop)
        ledger.append({
            "keep": keep,
            "drop": drop,
            "entity_type": nodes.get(keep, {}).get("type"),
            "keep_label": nodes.get(keep, {}).get("label"),
            "drop_label": nodes.get(drop, {}).get("label"),
            "reason": m.get("reason"),
            "evidence": m.get("evidence"),
        })

    def canon(nid):
        root = uf.find(nid)
        # canonical id = the lexicographically smallest 'keep' target in the set,
        # falling back to the root; deterministic either way.
        members = [m for m in nodes if uf.find(m) == root]
        keeps = [m["keep"] for m in merges if m["keep"] in members]
        return sorted(keeps)[0] if keeps else root

    out_nodes = []
    for nid in sorted(nodes):
        c = canon(nid)
        if c != nid:
            continue  # merged away
        n = nodes[nid]
        aliases = sorted(m for m in nodes if m != nid and canon(m) == nid)
        out_nodes.append({
            "id": nid,
            "type": n.get("type"),
            "label": n.get("label"),
            "merged_ids": aliases,
            "merged_labels": sorted(nodes[a].get("label") for a in aliases),
            "evidence": n.get("evidence"),
        })

    out_edges = []
    for eid in sorted(edges):
        e = edges[eid]
        out_edges.append({
            "id": eid,
            "relation": e.get("relation"),
            "subject": canon(e["subject"]),
            "object": canon(e["object"]),
            "polarity": e.get("polarity") or None,
            "qualifiers": e.get("qualifiers", {}),
            "evidence": e.get("evidence"),
        })
    out_edges.sort(key=lambda e: (e["relation"], e["subject"], e["object"], e["id"]))

    registry = [{
        "a": nm.get("a"), "b": nm.get("b"),
        "a_label": nodes.get(nm.get("a"), {}).get("label"),
        "b_label": nodes.get(nm.get("b"), {}).get("label"),
        "reason": nm.get("reason"), "evidence": nm.get("evidence"),
    } for nm in nonmerges]
    registry.sort(key=lambda r: (str(r["a"]), str(r["b"])))

    graph = {
        "node_count": len(out_nodes),
        "edge_count": len(out_edges),
        "nodes": out_nodes,
        "edges": out_edges,
        "relations_present": sorted({e["relation"] for e in out_edges}),
        "entity_types_present": sorted({n["type"] for n in out_nodes}),
    }
    dump_json(os.path.join(args.work, "graph.json"), graph)
    dump_json(os.path.join(args.work, "merge_ledger.json"),
              {"merge_count": len(ledger),
               "merges": sorted(ledger, key=lambda m: (m["keep"], m["drop"]))})
    dump_json(os.path.join(args.work, "nonmerge_registry.json"),
              {"nonmerge_count": len(registry), "nonmerges": registry})

    print("build: %d nodes, %d edges, %d merges, %d nonmerges"
          % (len(out_nodes), len(out_edges), len(ledger), len(registry)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
