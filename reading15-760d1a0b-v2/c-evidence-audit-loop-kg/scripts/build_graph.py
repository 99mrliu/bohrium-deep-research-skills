#!/usr/bin/env python3
"""build_graph.py — build the evidence-bound knowledge graph (stage 5).

Reads the final (repaired) extraction and the LATEST audit_report.json, keeps
ONLY audit-accepted items, applies merge ops (union-find; canonical node id =
lexicographically smallest member id; all labels kept as aliases), keeps
nonmerge decisions and unreported items, and preserves numeric conflicts as
separate claim nodes linked by conflicts-with edges.

Usage:
    python3 build_graph.py --work /app/work

Outputs: <work>/graph.json  (deterministic, sorted)
Python 3.9+, standard library only.
"""
import argparse
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def evidence_list(item):
    ev = item.get("evidence")
    if ev is None:
        return []
    if isinstance(ev, dict):
        return [ev]
    return [e for e in ev if isinstance(e, dict)]


def norm_evidence(ev):
    return {
        "paragraph_id": str(ev.get("paragraph_id") or ""),
        "quote": str(ev.get("quote") or ""),
        "source_id": str(ev.get("source_id") or ""),
    }


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
            self.parent[max(ra, rb)] = min(ra, rb)


def main():
    ap = argparse.ArgumentParser(description="Build graph from audit-accepted extraction items")
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    work = args.work

    rep = os.path.join(work, "extraction.repaired.json")
    draft_path = rep if os.path.isfile(rep) else os.path.join(work, "extraction.draft.json")
    draft = load_json(draft_path)
    report = load_json(os.path.join(work, "audit_report.json"))
    accepted_ids = set(report.get("verdicts", {}).get("accept") or [])

    items = [it for it in (draft.get("items") or [])
             if isinstance(it, dict) and str(it.get("id")) in accepted_ids]
    by_id = {str(it["id"]): it for it in items}

    uf = UnionFind()
    merges_applied = []
    for it in items:
        if it.get("op") == "merge":
            members = [str(m) for m in it.get("members") or [] if str(m) in by_id]
            if len(members) < 2:
                continue
            for m in members[1:]:
                uf.union(members[0], m)
            merges_applied.append({
                "id": str(it["id"]),
                "members": sorted(members),
                "normalized_key": it.get("normalized_key"),
                "reason": it.get("reason"),
                "evidence": sorted((norm_evidence(e) for e in evidence_list(it)),
                                   key=lambda e: (e["source_id"], e["paragraph_id"])),
            })

    def canon(x):
        return uf.find(x)

    # group node items by canonical id
    groups = {}
    for it in items:
        if it.get("op") == "node":
            groups.setdefault(canon(str(it["id"])), []).append(it)

    nodes = []
    for cid in sorted(groups.keys()):
        members = sorted(groups[cid], key=lambda n: str(n["id"]))
        canonical = members[0]
        labels = sorted({str(n.get("label")) for n in members})
        evs = []
        for n in members:
            evs.extend(norm_evidence(e) for e in evidence_list(n))
        evs = sorted({(e["source_id"], e["paragraph_id"], e["quote"]): e for e in evs}.values(),
                     key=lambda e: (e["source_id"], e["paragraph_id"]))
        node = {
            "id": cid,
            "entity_type": canonical.get("entity_type"),
            "label": canonical.get("label"),
            "aliases": labels,
            "evidence": evs,
        }
        if canonical.get("attributes"):
            node["attributes"] = canonical["attributes"]
        if len(members) > 1:
            node["merged_from"] = sorted(str(n["id"]) for n in members)
        nodes.append(node)

    node_ids = {n["id"] for n in nodes}
    edges = []
    dropped_edges = []
    for it in items:
        if it.get("op") != "edge":
            continue
        s, o = canon(str(it.get("subject"))), canon(str(it.get("object")))
        if s not in node_ids or o not in node_ids:
            dropped_edges.append({"id": str(it["id"]),
                                  "reason": "endpoint node not present in accepted graph"})
            continue
        edge = {
            "id": str(it["id"]),
            "relation": it.get("relation"),
            "subject": s,
            "object": o,
            "evidence": sorted((norm_evidence(e) for e in evidence_list(it)),
                               key=lambda e: (e["source_id"], e["paragraph_id"])),
        }
        if it.get("qualifiers"):
            edge["qualifiers"] = it["qualifiers"]
        edges.append(edge)
    edges.sort(key=lambda e: e["id"])

    nonmerges = []
    for it in items:
        if it.get("op") == "nonmerge":
            nonmerges.append({
                "id": str(it["id"]),
                "members": sorted(canon(str(m)) for m in (it.get("members") or [])),
                "reason": it.get("reason"),
                "evidence": sorted((norm_evidence(e) for e in evidence_list(it)),
                                   key=lambda e: (e["source_id"], e["paragraph_id"])),
            })
    nonmerges.sort(key=lambda r: r["id"])

    unreported = []
    for it in items:
        if it.get("op") == "unreported":
            unreported.append({
                "id": str(it["id"]),
                "topic": it.get("topic"),
                "reason": it.get("reason"),
                "scope": it.get("scope"),
                "evidence": sorted((norm_evidence(e) for e in evidence_list(it)),
                                   key=lambda e: (e["source_id"], e["paragraph_id"])),
            })
    unreported.sort(key=lambda r: r["id"])

    notes = sorted(str(it.get("text")) for it in items if it.get("op") == "note")

    graph = {
        "case_id": report.get("case_id"),
        "built_from": os.path.basename(draft_path),
        "audit_iteration": report.get("iteration"),
        "nodes": nodes,
        "edges": edges,
        "merges": sorted(merges_applied, key=lambda m: m["id"]),
        "nonmerges": nonmerges,
        "unreported": unreported,
        "notes": notes,
        "dropped_edges": dropped_edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "merge_count": len(merges_applied),
            "nonmerge_count": len(nonmerges),
            "unreported_count": len(unreported),
        },
    }
    dump_json(graph, os.path.join(work, "graph.json"))
    print("build_graph: nodes=%d edges=%d merges=%d nonmerges=%d unreported=%d dropped_edges=%d" % (
        len(nodes), len(edges), len(merges_applied), len(nonmerges), len(unreported),
        len(dropped_edges)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
