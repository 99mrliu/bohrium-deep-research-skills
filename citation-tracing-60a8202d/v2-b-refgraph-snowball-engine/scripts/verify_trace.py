#!/usr/bin/env python3
"""verify_trace.py -- self-check gate for the snowball deliverables.

Offline only. Python 3 standard library only. Location independent.

Run AFTER snowball.py. Checks (defects are reported with level error/warning):

  1. files_exist_and_parse   graph.json / result.json / trace_graph.json readable
  2. edge_locators           every result/trace edge carries source locators
                             with a non-empty file (and pointer)
  3. direction_consistency   no (source,target) pair labelled both forward and
                             backward (contradiction); every forward edge has a
                             matching backward mirror edge in the graph
  4. no_dangling_nodes       every edge endpoint exists in the node set; every
                             node is reachable from the seed along trace edges
  5. contract_mirror         result.json contains case_id and every field of
                             the case's output_contract
  6. layer_consistency       sum of layer additions == non-seed node count;
                             candidate layers within [0, max_depth]
  7. honest_status           status is one of ok/partial/failed and consistent
                             with content (failed => empty candidates)

Prints a JSON report plus a final line "ok=true" / "ok=false".
Exit code 0 when ok, 1 when defects found, 2 on unreadable inputs.
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def main():
    ap = argparse.ArgumentParser(description="Verify snowball trace deliverables.")
    ap.add_argument("--graph", default="/app/work/graph.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--trace", default="/app/output/trace_graph.json")
    ap.add_argument("--case", default="/input/case.json")
    args = ap.parse_args()

    defects = []

    def defect(check, level, detail):
        defects.append({"check": check, "level": level, "detail": detail})

    graph, err = load_json(args.graph)
    if graph is None:
        defect("files_exist_and_parse", "error", "graph unreadable: %s" % err)
        graph = {"nodes": [], "edges": [], "registry": []}
    result, err = load_json(args.result)
    if result is None:
        defect("files_exist_and_parse", "error", "result.json unreadable: %s" % err)
        print(json.dumps({"ok": False, "defects": defects}, ensure_ascii=False, indent=2))
        print("ok=false")
        return 2
    trace, err = load_json(args.trace)
    if trace is None:
        defect("files_exist_and_parse", "error", "trace_graph.json unreadable: %s" % err)
        trace = {"nodes": [], "edges": []}

    gnodes = {n["id"] for n in graph.get("nodes", [])}
    gedges = graph.get("edges", [])
    gpair = {}
    for e in gedges:
        gpair.setdefault((e["source"], e["target"]), set()).add(e["direction"])

    trace_node_ids = {n["id"] for n in trace.get("nodes", [])}
    trace_edges = trace.get("edges", [])
    result_edges = result.get("edges", [])

    # ---- 2. edge locators ---------------------------------------------------
    for label, elist in (("trace", trace_edges), ("result", result_edges)):
        for i, e in enumerate(elist):
            locs = e.get("sources") or []
            if not locs or not all(isinstance(l, dict) and l.get("file") for l in locs):
                defect("edge_locators", "error",
                       "%s edge %d (%s->%s) lacks source.file locator" %
                       (label, i, e.get("source"), e.get("target")))
            elif not all(l.get("pointer") for l in locs):
                defect("edge_locators", "warning",
                       "%s edge %d (%s->%s) locator missing pointer" %
                       (label, i, e.get("source"), e.get("target")))

    # ---- 3. direction consistency -------------------------------------------
    pair_dirs = {}
    for e in trace_edges:
        pair_dirs.setdefault((e["source"], e["target"]), set()).add(e["direction"])
    for (s, t), dirs in sorted(pair_dirs.items()):
        if len(dirs) > 1:
            defect("direction_consistency", "error",
                   "edge %s -> %s labelled with conflicting directions %s" %
                   (s, t, sorted(dirs)))
    for e in trace_edges:
        if e["direction"] == "forward":
            mirror = gpair.get((e["target"], e["source"]), set())
            if "backward" not in mirror:
                defect("direction_consistency", "error",
                       "forward edge %s -> %s has no backward mirror (%s cites %s) "
                       "in graph" % (e["source"], e["target"], e["target"], e["source"]))
        if (e["source"], e["target"]) not in gpair:
            defect("direction_consistency", "warning",
                   "trace edge %s -> %s not present in graph.json" %
                   (e["source"], e["target"]))
        if e.get("direction_restored") and e["direction"] != "forward":
            defect("direction_consistency", "error",
                   "direction_restored=true on a non-forward edge %s -> %s" %
                   (e["source"], e["target"]))

    # ---- 4. dangling nodes / reachability -----------------------------------
    for label, elist, nset in (("trace", trace_edges, trace_node_ids),):
        for e in elist:
            for endpoint in (e["source"], e["target"]):
                if endpoint not in nset:
                    defect("no_dangling_nodes", "error",
                           "%s edge endpoint %s missing from node set" % (label, endpoint))
                if endpoint not in gnodes:
                    defect("no_dangling_nodes", "warning",
                           "%s edge endpoint %s not in graph.json nodes" % (label, endpoint))
    seed_ids = (trace.get("seed_node_ids") or
                (result.get("seed") or {}).get("resolved_node_ids") or [])
    adjacency = {}
    for e in trace_edges:
        adjacency.setdefault(e["source"], []).append(e["target"])
    reachable = set()
    stack = list(seed_ids)
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(adjacency.get(cur, []))
    for nid in sorted(trace_node_ids - reachable):
        defect("no_dangling_nodes", "error",
               "trace node %s unreachable from seed" % nid)

    # ---- 5. contract mirror --------------------------------------------------
    if not result.get("case_id"):
        defect("contract_mirror", "error", "result.json missing case_id")
    case, case_err = load_json(args.case)
    if case is None:
        defect("contract_mirror", "warning",
               "case.json unreadable (%s); contract mirror not verifiable" % case_err)
    else:
        contract = case.get("output_contract")
        fields = (list(contract.keys()) if isinstance(contract, dict)
                  else [f for f in contract if isinstance(f, str)]
                  if isinstance(contract, list) else [])
        for f in fields:
            if f not in result:
                defect("contract_mirror", "error",
                       "output_contract field '%s' not mirrored in result.json" % f)

    # ---- 6. layer consistency ------------------------------------------------
    layers = result.get("layers", [])
    added_total = sum(l.get("n_added", 0) for l in layers)
    candidates = result.get("candidates", [])
    non_seed = len(candidates) - len([s for s in seed_ids if s in trace_node_ids])
    if added_total != max(non_seed, 0):
        defect("layer_consistency", "warning",
               "layer additions (%d) != non-seed candidates (%d)" %
               (added_total, non_seed))
    max_depth = ((result.get("params") or {}).get("max_depth"))
    for c in candidates:
        lay = c.get("layer")
        if lay is None or lay < 0 or (max_depth is not None and lay > max_depth):
            defect("layer_consistency", "error",
                   "candidate %s has invalid layer %s" % (c.get("id"), lay))
    cand_ids = {c["id"] for c in candidates}
    if cand_ids != trace_node_ids:
        defect("layer_consistency", "warning",
               "result candidates and trace nodes differ: %s vs %s" %
               (sorted(cand_ids - trace_node_ids), sorted(trace_node_ids - cand_ids)))

    # ---- 7. honest status -----------------------------------------------------
    status = result.get("status")
    if status not in ("ok", "partial", "failed"):
        defect("honest_status", "error", "status must be ok/partial/failed, got %r" % status)
    if status == "failed" and candidates:
        defect("honest_status", "warning",
               "status=failed but candidates non-empty")
    if status == "ok" and not candidates:
        defect("honest_status", "error", "status=ok but zero candidates")

    ok = not any(d["level"] == "error" for d in defects)
    report = {
        "ok": ok,
        "n_errors": sum(1 for d in defects if d["level"] == "error"),
        "n_warnings": sum(1 for d in defects if d["level"] == "warning"),
        "checked": {
            "graph": str(args.graph), "result": str(args.result),
            "trace": str(args.trace), "case": str(args.case),
        },
        "defects": defects,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("ok=%s" % ("true" if ok else "false"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
