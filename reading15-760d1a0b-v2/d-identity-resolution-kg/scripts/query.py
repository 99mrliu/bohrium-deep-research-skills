#!/usr/bin/env python3
"""query.py — execute the case's query_specs against the built graph.

Supported deterministic query types:
  neighborhood      {"entity": <surface>, "hops": N}
                    BFS over edges (both directions) from the canonical entity;
  edges_by_relation {"relation": <relation-type>}
  conflict_check    {"entity": <surface>, "metric": <metric>}
                    all preserved conflicts touching that entity/metric;

Every result returns a subgraph, the supporting evidence (verbatim quotes with
paragraph addresses), and an explicit list of relation types from the
vocabulary that remain undetermined (no matching edges) inside the subgraph.
Empty results are reported honestly with status "empty".

Output: <work>/query_results.json

Usage: python3 query.py --work /app/work
"""
import argparse
import os
import sys

import kgcommon as K


def _subgraph(graph, node_ids, edges):
    nodes = [n for n in graph["nodes"]
             if n.get("entity_id") in node_ids or n.get("claim_id") in node_ids]
    evidence = []
    for n in nodes:
        if n.get("type") == "claim":
            evidence.append({"node": n["claim_id"],
                             "source_id": n["source_id"],
                             "paragraph_id": n["paragraph_id"],
                             "quote": n["quote"]})
        else:
            for m in n.get("mentions", [])[:3]:
                evidence.append({"node": n["entity_id"],
                                 "source_id": m["source_id"],
                                 "paragraph_id": m["paragraph_id"],
                                 "quote": m["quote"]})
    for e in edges:
        if e.get("quote") and e.get("paragraph_id"):
            evidence.append({"edge": e["edge_id"],
                             "source_id": e["source_id"],
                             "paragraph_id": e["paragraph_id"],
                             "quote": e["quote"]})
    evidence.sort(key=lambda ev: (str(ev.get("source_id")),
                                  str(ev.get("paragraph_id")),
                                  str(ev.get("quote"))))
    return nodes, edges, evidence


def _unknown_relations(graph, edges):
    present = {e["relation"] for e in edges}
    return sorted(r for r in graph.get("relation_vocabulary", [])
                  if r not in present)


def run_query(spec, graph, conflicts):
    qtype = spec.get("type")
    params = spec.get("params") or {}
    result = {"query_id": spec.get("query_id"), "type": qtype,
              "params": params, "status": "answered"}

    if qtype == "neighborhood":
        surface = params.get("entity", "")
        hops = int(params.get("hops", 1))
        key = K.norm_key(surface)
        starts = [n.get("entity_id") for n in graph["nodes"]
                  if n.get("type") != "claim" and key in n.get("member_keys", [])]
        if not starts:
            result.update({"status": "empty",
                           "note": "no canonical entity matches %r" % surface,
                           "subgraph": {"nodes": [], "edges": []},
                           "evidence": [], "undetermined_relations": []})
            return result
        adj = {}
        for e in graph["edges"]:
            adj.setdefault(e["subject"], []).append(e)
            adj.setdefault(e["object"], []).append(e)
        seen_nodes = set(starts)
        seen_edges, frontier = [], list(starts)
        for _ in range(max(hops, 0)):
            nxt = []
            for nid in frontier:
                for e in adj.get(nid, []):
                    if e["edge_id"] not in {x["edge_id"] for x in seen_edges}:
                        seen_edges.append(e)
                    for end in (e["subject"], e["object"]):
                        if end not in seen_nodes:
                            seen_nodes.add(end)
                            nxt.append(end)
            frontier = nxt
        nodes, edges, evidence = _subgraph(graph, seen_nodes, seen_edges)
        result.update({
            "resolved_entity": sorted(starts),
            "subgraph": {"nodes": nodes, "edges": edges},
            "evidence": evidence,
            "undetermined_relations": _unknown_relations(graph, edges),
        })
        return result

    if qtype == "edges_by_relation":
        rel = params.get("relation")
        edges = [e for e in graph["edges"] if e["relation"] == rel]
        if not edges:
            result.update({"status": "empty",
                           "note": "no edges of relation %r" % rel,
                           "subgraph": {"nodes": [], "edges": []},
                           "evidence": [], "undetermined_relations": [rel]})
            return result
        node_ids = {e["subject"] for e in edges} | {e["object"] for e in edges}
        nodes, edges, evidence = _subgraph(graph, node_ids, edges)
        result.update({"subgraph": {"nodes": nodes, "edges": edges},
                       "evidence": evidence,
                       "undetermined_relations": _unknown_relations(graph, edges)})
        return result

    if qtype == "conflict_check":
        key = K.norm_key(params.get("entity", ""))
        mkey = K.norm_key(params.get("metric", ""))
        hits = []
        for conf in conflicts.get("conflicts", []):
            ent_ok = not key or any(
                key == K.norm_key(a)
                for a in graph_node_aliases(graph, conf["entity_id"]))
            met_ok = not mkey or K.norm_key(conf["metric"]) == mkey
            if ent_ok and met_ok:
                hits.append(conf)
        if not hits:
            result.update({"status": "empty",
                           "note": "no preserved conflicts match",
                           "conflicts": [], "evidence": [],
                           "undetermined_relations": ["conflicts-with"]})
            return result
        evidence = []
        edge_ids = []
        for conf in hits:
            for c in conf["claims"]:
                evidence.append({"claim_id": c["claim_id"],
                                 "source_id": c["source_id"],
                                 "paragraph_id": c["paragraph_id"],
                                 "quote": c["quote"]})
            for e in graph["edges"]:
                if (e["relation"] == "conflicts-with"
                        and e["qualifiers"].get("conflict_id") == conf["conflict_id"]):
                    edge_ids.append(e["edge_id"])
        evidence.sort(key=lambda ev: (str(ev["source_id"]),
                                      str(ev["paragraph_id"])))
        result.update({"conflicts": hits, "conflict_edge_ids": sorted(edge_ids),
                       "evidence": evidence,
                       "undetermined_relations": []})
        return result

    result.update({"status": "unsupported",
                   "note": "query type %r not supported by this bundle" % qtype,
                   "subgraph": {"nodes": [], "edges": []}, "evidence": [],
                   "undetermined_relations": []})
    return result


def graph_node_aliases(graph, entity_id):
    for n in graph["nodes"]:
        if n.get("entity_id") == entity_id:
            return n.get("aliases", [])
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    work = args.work
    try:
        corpus = K.load_json(os.path.join(work, "corpus.json"))
        graph = K.load_json(os.path.join(work, "graph.json"))
        conflicts = K.load_json(os.path.join(work, "conflict_registry.json"))
    except Exception as exc:
        print("ERROR: %s; run earlier stages first" % exc, file=sys.stderr)
        return 2

    specs = corpus.get("query_specs") or []
    if not specs:
        specs = [{"query_id": "Q-auto-1", "type": "edges_by_relation",
                  "params": {"relation": "uses"},
                  "description": "fallback query: case.json declared no query_specs"},
                 {"query_id": "Q-auto-2", "type": "conflict_check",
                  "params": {}, "description": "fallback: list all conflicts"},
                 {"query_id": "Q-auto-3", "type": "neighborhood",
                  "params": {"entity": "", "hops": 1},
                  "description": "fallback: likely empty neighborhood"}]
    results = [run_query(spec, graph, conflicts) for spec in specs]
    out = {"notice": K.NOTICE,
           "executed": len(results),
           "answered": sum(1 for r in results if r["status"] == "answered"),
           "queries": results}
    K.dump_json(out, os.path.join(work, "query_results.json"))
    print("query: %d executed, %d answered -> %s"
          % (out["executed"], out["answered"],
             os.path.join(work, "query_results.json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
