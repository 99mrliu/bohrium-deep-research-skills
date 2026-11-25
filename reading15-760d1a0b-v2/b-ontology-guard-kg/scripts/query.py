#!/usr/bin/env python3
"""query.py — typed graph-pattern query answering with qualifier filtering.

Executes the query_specs declared in case.json (or a file given via --queries)
against <work>/graph.json. Three typed query patterns are supported:

    neighborhood        entity + depth [+ relation_filter]
    edges_of_relation   relation [+ qualifier_filter {key: value}]
    contradiction_check claim_a + claim_b (label substring match)

Every result carries a status (ok / no_match / unknown_entity), the result
subgraph, supporting evidence (verbatim quotes), and an explicitly listed
`undetermined` set. Empty results are honest answers, not errors.

Usage:
    python3 query.py --work /app/work [--queries FILE] [--out FILE]

Defaults: queries from <work>/case_snapshot.json query_specs;
results to <work>/query_results.json.

Python 3 standard library only. Deterministic output.
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


def norm(s):
    return " ".join(str(s).casefold().split())


def find_nodes(graph, needle, types=None):
    """Deterministic entity resolution: exact (casefold) first, then substring."""
    n = norm(needle)
    cands = [nd for nd in graph["nodes"]
             if types is None or nd["type"] in types]
    exact = [nd for nd in cands
             if norm(nd["label"]) == n or n in [norm(x) for x in nd.get("merged_labels", [])]]
    if exact:
        return sorted(exact, key=lambda x: x["id"])
    sub = [nd for nd in cands
           if n in norm(nd["label"])
           or any(n in norm(x) for x in nd.get("merged_labels", []))]
    return sorted(sub, key=lambda x: x["id"])


def edge_evidence(edge):
    evs = edge.get("evidence")
    if isinstance(evs, dict):
        evs = [evs]
    return [{"source_id": e.get("source_id"), "paragraph_id": e.get("paragraph_id"),
             "quote": e.get("quote")} for e in (evs or [])]


def subgraph(graph, node_ids, edges):
    ids = set(node_ids)
    for e in edges:
        ids.add(e["subject"])
        ids.add(e["object"])
    return {
        "nodes": [nd for nd in graph["nodes"] if nd["id"] in ids],
        "edges": sorted(edges, key=lambda e: (e["relation"], e["subject"],
                                              e["object"], e["id"])),
    }


def q_neighborhood(graph, spec):
    label = spec.get("entity", "")
    depth = int(spec.get("depth", 1))
    rel_filter = spec.get("relation_filter")
    seeds = find_nodes(graph, label)
    if not seeds:
        return {"status": "unknown_entity",
                "message": "no node matches '%s'" % label,
                "subgraph": {"nodes": [], "edges": []},
                "evidence": [], "undetermined": ["all relations of '%s'" % label]}
    frontier = {s["id"] for s in seeds}
    seen = set(frontier)
    picked, picked_ids = [], set()
    for _ in range(max(depth, 0)):
        new = []
        for e in graph["edges"]:
            if rel_filter and e["relation"] not in rel_filter:
                continue
            if e["id"] in picked_ids:
                continue
            if e["subject"] in frontier or e["object"] in frontier:
                new.append(e)
                picked_ids.add(e["id"])
        picked.extend(new)
        frontier = {e["subject"] for e in new} | {e["object"] for e in new}
        frontier -= seen
        seen |= frontier
    undetermined = []
    for e in picked:
        if e["relation"] == "reviews-cites":
            undetermined.append(
                "edge %s is review/citation context, not direct evidence" % e["id"])
    ev = [dict(edge_id=e["id"], **ev) for e in picked for ev in edge_evidence(e)]
    return {"status": "ok" if picked else "no_match",
            "seed_nodes": [s["id"] for s in seeds],
            "subgraph": subgraph(graph, [s["id"] for s in seeds], picked),
            "evidence": sorted(ev, key=lambda x: (x["edge_id"], str(x.get("quote")))),
            "undetermined": sorted(undetermined)}


def q_edges_of_relation(graph, spec):
    rel = spec.get("relation")
    qf = spec.get("qualifier_filter") or {}
    known = set(graph.get("relations_present", []))
    if rel not in known:
        return {"status": "no_match",
                "message": "relation '%s' has no edges (present: %s)"
                           % (rel, ", ".join(sorted(known))),
                "subgraph": {"nodes": [], "edges": []}, "evidence": [],
                "undetermined": ["edges of relation '%s'" % rel]}
    hits = []
    for e in graph["edges"]:
        if e["relation"] != rel:
            continue
        quals = e.get("qualifiers", {})
        if any(str(quals.get(k)) != str(v) for k, v in qf.items()):
            continue
        hits.append(e)
    ev = [dict(edge_id=e["id"], **ev) for e in hits for ev in edge_evidence(e)]
    return {"status": "ok" if hits else "no_match",
            "relation": rel, "qualifier_filter": qf,
            "subgraph": subgraph(graph, [], hits),
            "evidence": sorted(ev, key=lambda x: (x["edge_id"], str(x.get("quote")))),
            "undetermined": [] if hits else ["edges of relation '%s' matching %s"
                                             % (rel, qf)]}


def q_contradiction_check(graph, spec):
    a = find_nodes(graph, spec.get("claim_a", ""), types={"claim"})
    b = find_nodes(graph, spec.get("claim_b", ""), types={"claim"})
    undetermined = []
    if not a or not b:
        missing = []
        if not a:
            missing.append("claim_a '%s'" % spec.get("claim_a"))
        if not b:
            missing.append("claim_b '%s'" % spec.get("claim_b"))
        return {"status": "unknown_entity",
                "message": "unresolved: " + "; ".join(missing),
                "subgraph": {"nodes": [], "edges": []}, "evidence": [],
                "undetermined": ["relation between " + " and ".join(missing)]}
    ids_a, ids_b = {n["id"] for n in a}, {n["id"] for n in b}
    links = [e for e in graph["edges"]
             if e["relation"] in ("contradicts", "compares")
             and ((e["subject"] in ids_a and e["object"] in ids_b)
                  or (e["subject"] in ids_b and e["object"] in ids_a))]
    verdict = "undetermined"
    if any(e["relation"] == "contradicts" for e in links):
        verdict = "contradiction"
    elif links:
        verdict = "compared_no_contradiction"
    # condition comparison: surfaces different-condition numeric conflicts
    conds = {}
    for side, ids in (("a", ids_a), ("b", ids_b)):
        conds[side] = sorted({str(e["qualifiers"].get("condition"))
                              for e in graph["edges"]
                              if e["subject"] in ids and e["relation"] == "reports"
                              and e["qualifiers"].get("condition")})
    if not links:
        undetermined.append("no contradicts/compares edge recorded between the two claims")
    if conds["a"] and conds["b"] and conds["a"] != conds["b"]:
        undetermined.append("conditions differ (%s vs %s): numeric values must NOT be merged"
                            % (conds["a"], conds["b"]))
    ev = [dict(edge_id=e["id"], **ev) for e in links for ev in edge_evidence(e)]
    return {"status": "ok", "verdict": verdict,
            "claim_a_nodes": sorted(ids_a), "claim_b_nodes": sorted(ids_b),
            "conditions": conds,
            "subgraph": subgraph(graph, sorted(ids_a | ids_b), links),
            "evidence": sorted(ev, key=lambda x: (x["edge_id"], str(x.get("quote")))),
            "undetermined": sorted(undetermined)}


HANDLERS = {"neighborhood": q_neighborhood,
            "edges_of_relation": q_edges_of_relation,
            "contradiction_check": q_contradiction_check}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Execute typed query specs against graph.")
    parser.add_argument("--work", required=True)
    parser.add_argument("--queries", default=None,
                        help="JSON file with a list of query specs "
                             "(default: query_specs in <work>/case_snapshot.json)")
    parser.add_argument("--out", default=None,
                        help="output path (default: <work>/query_results.json)")
    args = parser.parse_args(argv)

    graph = load_json(os.path.join(args.work, "graph.json"))
    if graph is None:
        print("FATAL: graph.json missing; run build_graph.py first", file=sys.stderr)
        return 2

    if args.queries:
        specs = load_json(args.queries, [])
    else:
        case = load_json(os.path.join(args.work, "case_snapshot.json"), {})
        specs = case.get("query_specs") or []
    if not isinstance(specs, list):
        specs = []
    if not specs:
        print("query: no query_specs found; nothing executed")
    # deterministic execution order
    specs = sorted([s for s in specs if isinstance(s, dict)],
                   key=lambda s: str(s.get("query_id", "")))

    results = []
    for spec in specs:
        qtype = spec.get("type")
        handler = HANDLERS.get(qtype)
        res = {"query_id": spec.get("query_id"), "type": qtype, "spec": spec}
        if handler is None:
            res.update({"status": "unsupported_query_type",
                        "message": "supported types: %s" % ", ".join(sorted(HANDLERS)),
                        "subgraph": {"nodes": [], "edges": []},
                        "evidence": [], "undetermined": ["entire query"]})
        else:
            res.update(handler(graph, spec))
        results.append(res)

    out = {"query_count": len(results),
           "executed": sum(1 for r in results if r["status"] not in
                           ("unsupported_query_type",)),
           "results": results}
    out_path = args.out or os.path.join(args.work, "query_results.json")
    dump_json(out_path, out)
    for r in results:
        print("query %s (%s): %s, %d nodes, %d edges, %d undetermined"
              % (r["query_id"], r["type"], r["status"],
                 len(r["subgraph"]["nodes"]), len(r["subgraph"]["edges"]),
                 len(r.get("undetermined", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
