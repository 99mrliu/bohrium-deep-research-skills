#!/usr/bin/env python3
"""query.py — execute the case's query_specs against the built graph (stage 6).

Supported query types (generic, driven by case.json query_specs):
  neighborhood      params: {"entity": <label-or-alias>, "hops": N}
                    -> result subgraph within N hops of every matching node
  edges_by_relation params: {"relation": <relation-type>}
                    -> all edges of that type + endpoint nodes + evidence
  conflict_check    params: {"metric": <metric label or abbreviation>}
                    -> all claims measuring that metric, grouped by value;
                       distinct values under distinct conditions are reported
                       as preserved conflicts, never merged

Every executed query returns: result subgraph, supporting evidence
(source_id + paragraph_id + verbatim quote), and an explicit list of
undetermined/unknown relations. Empty results are reported honestly.

Usage:
    python3 query.py --work /app/work

Outputs: <work>/queries.json  (deterministic, sorted)
Python 3.9+, standard library only.
"""
import argparse
import json
import os
import re
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def norm(s):
    return re.sub(r"[\s\-_]+", "", str(s or "")).casefold()


def node_matches(node, query):
    q = norm(query)
    if not q:
        return False
    if norm(node.get("label")) == q:
        return True
    return any(norm(a) == q for a in node.get("aliases") or [])


def collect_evidence(objs):
    seen = {}
    for o in objs:
        for e in o.get("evidence") or []:
            key = (e.get("source_id"), e.get("paragraph_id"), e.get("quote"))
            seen[key] = {"source_id": e.get("source_id"),
                         "paragraph_id": e.get("paragraph_id"),
                         "quote": e.get("quote")}
    return [seen[k] for k in sorted(seen)]


def subgraph(graph, node_ids, edge_ids):
    nodes = [n for n in graph["nodes"] if n["id"] in node_ids]
    edges = [e for e in graph["edges"] if e["id"] in edge_ids]
    return {
        "nodes": sorted(({"id": n["id"], "entity_type": n["entity_type"],
                          "label": n["label"], "aliases": n.get("aliases") or []}
                         for n in nodes), key=lambda n: n["id"]),
        "edges": sorted(({"id": e["id"], "relation": e["relation"],
                          "subject": e["subject"], "object": e["object"]}
                         for e in edges), key=lambda e: e["id"]),
    }


def run_neighborhood(graph, params):
    entity = params.get("entity") or ""
    hops = int(params.get("hops") or 1)
    seeds = [n["id"] for n in graph["nodes"] if node_matches(n, entity)]
    if not seeds:
        return {"matched_seeds": [], "subgraph": {"nodes": [], "edges": []},
                "evidence": [],
                "undetermined": ["no node matches entity '%s'; the graph does not "
                                 "contain this object (checked label + aliases)" % entity]}
    node_ids = set(seeds)
    edge_ids = set()
    frontier = set(seeds)
    for _ in range(max(hops, 0)):
        nxt = set()
        for e in graph["edges"]:
            if e["subject"] in frontier or e["object"] in frontier:
                edge_ids.add(e["id"])
                for end in (e["subject"], e["object"]):
                    if end not in node_ids:
                        nxt.add(end)
                        node_ids.add(end)
        frontier = nxt
    objs = ([n for n in graph["nodes"] if n["id"] in node_ids] +
            [e for e in graph["edges"] if e["id"] in edge_ids])
    return {"matched_seeds": sorted(seeds),
            "subgraph": subgraph(graph, node_ids, edge_ids),
            "evidence": collect_evidence(objs),
            "undetermined": []}


def run_edges_by_relation(graph, params):
    rel = params.get("relation") or ""
    edges = [e for e in graph["edges"] if e.get("relation") == rel]
    node_ids = set()
    for e in edges:
        node_ids.add(e["subject"])
        node_ids.add(e["object"])
    objs = edges + [n for n in graph["nodes"] if n["id"] in node_ids]
    undetermined = []
    if not edges:
        known = sorted({e.get("relation") for e in graph["edges"]})
        undetermined.append("no edges of relation '%s'; relation types present: %s" % (rel, known))
    return {"matched_seeds": [],
            "subgraph": subgraph(graph, node_ids, {e["id"] for e in edges}),
            "evidence": collect_evidence(objs),
            "undetermined": undetermined}


def run_conflict_check(graph, params):
    metric = params.get("metric") or ""
    metric_nodes = [n for n in graph["nodes"]
                    if n.get("entity_type") == "metric" and
                    (norm(metric) in norm(n.get("label")) or node_matches(n, metric))]
    metric_ids = {n["id"] for n in metric_nodes}
    claims = {}
    for e in graph["edges"]:
        if e.get("relation") == "measures" and e.get("object") in metric_ids:
            claims[e["subject"]] = True
        if e.get("relation") == "measures" and e.get("subject") in metric_ids:
            claims[e["object"]] = True
    claim_nodes = [n for n in graph["nodes"] if n["id"] in claims]
    by_value = {}
    for n in claim_nodes:
        val = str((n.get("attributes") or {}).get("value") or "unknown")
        by_value.setdefault(val, []).append(n["id"])
    conflict_edges = [e for e in graph["edges"]
                      if e.get("relation") == "conflicts-with"
                      and e["subject"] in claims and e["object"] in claims]
    node_ids = set(claims) | metric_ids
    edge_ids = {e["id"] for e in conflict_edges}
    for e in graph["edges"]:
        if e.get("relation") == "measures" and (e["subject"] in claims or e["object"] in claims):
            edge_ids.add(e["id"])
    objs = claim_nodes + metric_nodes + conflict_edges
    distinct_values = sorted(by_value.keys())
    undetermined = []
    if len(distinct_values) > 1:
        undetermined.append(
            "metric '%s' has %d distinct reported values %s under different "
            "conditions/papers; they are PRESERVED as separate claims and are not "
            "directly comparable — no single merged value is asserted" %
            (metric, len(distinct_values), distinct_values))
    if not claim_nodes:
        undetermined.append("no claims measuring metric '%s' found in the graph" % metric)
    return {"matched_seeds": sorted(metric_ids),
            "claims_by_value": {k: sorted(v) for k, v in sorted(by_value.items())},
            "distinct_value_count": len(distinct_values),
            "conflict_edges": sorted(e["id"] for e in conflict_edges),
            "subgraph": subgraph(graph, node_ids, edge_ids),
            "evidence": collect_evidence(objs),
            "undetermined": undetermined}


RUNNERS = {
    "neighborhood": run_neighborhood,
    "edges_by_relation": run_edges_by_relation,
    "conflict_check": run_conflict_check,
}


def main():
    ap = argparse.ArgumentParser(description="Execute case query_specs against the graph")
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    work = args.work

    graph = load_json(os.path.join(work, "graph.json"))
    corpus = load_json(os.path.join(work, "corpus.json"))
    specs = corpus.get("query_specs") or []

    results = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        qid = str(spec.get("query_id") or "q?")
        qtype = str(spec.get("type") or "")
        params = spec.get("params") or {}
        runner = RUNNERS.get(qtype)
        if runner is None:
            results.append({
                "query_id": qid, "type": qtype, "status": "unsupported",
                "supported_types": sorted(RUNNERS),
                "undetermined": ["query type '%s' is not supported by this skill" % qtype],
            })
            continue
        out = runner(graph, params)
        out.update({"query_id": qid, "type": qtype, "status": "executed",
                    "params": params,
                    "question": spec.get("question")})
        results.append(out)
    results.sort(key=lambda r: r["query_id"])

    doc = {
        "case_id": graph.get("case_id"),
        "queries_executed": sum(1 for r in results if r.get("status") == "executed"),
        "queries_total": len(results),
        "results": results,
    }
    dump_json(doc, os.path.join(work, "queries.json"))
    print("query: executed %d/%d query specs" % (doc["queries_executed"], doc["queries_total"]))
    for r in results:
        if r.get("status") == "executed":
            sg = r.get("subgraph") or {}
            print("  %s [%s]: nodes=%d edges=%d evidence=%d undetermined=%d" % (
                r["query_id"], r["type"], len(sg.get("nodes") or []),
                len(sg.get("edges") or []), len(r.get("evidence") or []),
                len(r.get("undetermined") or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
