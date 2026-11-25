#!/usr/bin/env python3
"""snowball.py -- direction-aware multi-hop snowball traversal over graph.json.

Offline only. Python 3 standard library only. Location independent.

Pipeline position: run AFTER refgraph.py (which builds <workdir>/graph.json).

What it does:
  1. Robust seed resolution: scans several case.json fields for DOI strings
     (every attempt is logged), falls back to a DOI regex over task.md.
  2. Keyword extraction from task.md for relevance pruning.
  3. Layered BFS expansion from the seed:
       backward branch follows reference edges (citing -> cited),
       forward  branch follows citation edges (cited  -> citing),
     both branches expanded within the same layer.
  4. Pruning (every decision logged to pruning_log, kept or pruned):
       - year_min filter, with a foundational-classic exception
         (cited_by_count >= --classic-citedby is always kept);
       - keyword relevance filter (zero keyword overlap is pruned,
         stubs and classics exempt);
       - per-parent per-direction branch cap --max-branch
         (classics exempt; overflow pruned as branch_cap);
       - global node budget --max-nodes (overflow pruned as node_budget).
  5. Stop criteria logged to stop_log: depth limit, node budget exhausted,
     or a whole layer with zero new nodes.

Outputs:
  <out>/result.json       case_id, status, seed (+parse attempts), candidates
                          (nodes with layer/direction), edges, layers stats,
                          pruning_log, stop_log, sources, evidence_records,
                          uncertainty; every field of the case's
                          output_contract is mirrored (unfillable -> null +
                          uncertainty note). Honest status ok/partial/failed.
  <out>/trace_graph.json  the traversed subgraph with layer/direction labels.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

DOI_RE = re.compile(r"10\.\d{4,9}/[A-Za-z0-9._/:+\-]+")
WORD_RE = re.compile(r"[a-z][a-z0-9\-]{3,}")

STOPWORDS = {
    "this", "that", "with", "from", "into", "using", "used", "use", "uses",
    "based", "between", "which", "their", "there", "where", "when", "what",
    "have", "has", "been", "were", "are", "and", "the", "for", "its", "his",
    "her", "our", "your", "they", "them", "then", "than", "such", "also",
    "via", "per", "each", "other", "more", "most", "some", "any", "all",
    "paper", "papers", "study", "studies", "work", "works", "task", "case",
    "given", "provide", "provided", "please", "should", "must", "will",
    "about", "these", "those", "over", "under", "both", "same", "different",
    "identify", "find", "related", "relevant", "literature", "review",
    "include", "including", "following", "along", "through", "within",
    "demo", "real",
}

SEED_FIELD_CANDIDATES = [
    "seed", "seeds", "seed_doi", "seed_dois", "seed_paper", "seed_papers",
    "paper", "papers", "target", "target_doi", "query", "research_question",
    "doi", "title",
]


def norm_doi(raw):
    if raw is None:
        return None
    d = str(raw).strip().strip("<>")
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    return d.strip().rstrip(".,;)").lower() or None


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def find_dois_in(obj):
    """Recursively collect DOI-looking strings from any JSON value."""
    found = []
    if isinstance(obj, str):
        found.extend(m.group(0).rstrip(".,;)").lower() for m in DOI_RE.finditer(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(find_dois_in(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(find_dois_in(v))
    return found


def find_titles_in(obj):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "title" and isinstance(v, str):
                found.append(v)
            else:
                found.extend(find_titles_in(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(find_titles_in(v))
    return found


def extract_keywords(text, top_n=12):
    text = DOI_RE.sub(" ", text)  # drop DOI strings before tokenising
    words = [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS]
    common = Counter(words).most_common()
    common.sort(key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in common[:top_n]]


def keyword_score(node, keywords):
    text = " ".join(filter(None, [node.get("title") or "",
                                  " ".join(node.get("authors") or []),
                                  node.get("venue") or ""])).lower()
    if not text.strip():
        return 0
    return sum(1 for kw in keywords if kw in text)


def main():
    ap = argparse.ArgumentParser(description="Direction-aware snowball traversal.")
    ap.add_argument("--graph", default=None,
                    help="path to graph.json (default: <workdir>/graph.json)")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--max-nodes", type=int, default=250)
    ap.add_argument("--max-branch", type=int, default=40)
    ap.add_argument("--year-min", type=int, default=None)
    ap.add_argument("--classic-citedby", type=int, default=1000,
                    help="cited_by_count threshold for the foundational-classic exception")
    args = ap.parse_args()

    workdir = Path(args.workdir)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    graph_path = Path(args.graph) if args.graph else workdir / "graph.json"

    uncertainty = []

    # ---- load inputs -------------------------------------------------------
    graph, err = load_json(graph_path)
    if graph is None:
        print(json.dumps({"ok": False, "error": "cannot read graph: %s" % err}))
        return 2
    case, case_err = load_json(args.case)
    if case is None:
        case = {}
        uncertainty.append("case.json unreadable (%s); contract fields unknown" % case_err)
    task_text = ""
    task_path = Path(args.task)
    if task_path.exists():
        task_text = task_path.read_text(encoding="utf-8", errors="replace")
    else:
        alt = Path(args.case).parent / "task.md"
        if alt.exists():
            task_text = alt.read_text(encoding="utf-8", errors="replace")
        else:
            uncertainty.append("task.md not found; keyword pruning disabled "
                               "(relevance filter passes everything)")

    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    back_adj, fwd_adj = {}, {}
    for e in edges:
        if e["direction"] == "backward":
            back_adj.setdefault(e["source"], []).append(e["target"])
        else:
            fwd_adj.setdefault(e["source"], []).append(e["target"])
    for adj in (back_adj, fwd_adj):
        for k in adj:
            adj[k] = sorted(set(adj[k]))
    doi_index = {n["doi"]: n["id"] for n in nodes.values() if n.get("doi")}
    title_index = {}
    for n in nodes.values():
        if n.get("title"):
            key = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", n["title"])).strip().lower()
            title_index.setdefault(key, n["id"])

    # ---- seed resolution (every attempt logged) -----------------------------
    parse_attempts = []
    requested_dois, requested_titles = [], []
    for field in SEED_FIELD_CANDIDATES:
        if field in case:
            dois = find_dois_in(case[field])
            titles = find_titles_in(case[field])
            parse_attempts.append({"strategy": "case.json field",
                                   "field": field,
                                   "dois_found": sorted(set(dois)),
                                   "titles_found": titles[:5]})
            requested_dois.extend(dois)
            requested_titles.extend(titles)
    if task_text:
        dois = [m.group(0).rstrip(".,;)").lower() for m in DOI_RE.finditer(task_text)]
        parse_attempts.append({"strategy": "task.md DOI regex",
                               "field": "task.md",
                               "dois_found": sorted(set(dois)),
                               "titles_found": []})
        requested_dois.extend(dois)

    seed_ids, seen = [], set()
    for d in requested_dois:
        nid = doi_index.get(norm_doi(d))
        if nid and nid not in seen:
            seed_ids.append(nid)
            seen.add(nid)
    if not seed_ids:
        for t in requested_titles:
            key = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip().lower()
            nid = title_index.get(key)
            if nid and nid not in seen:
                seed_ids.append(nid)
                seen.add(nid)
    parse_attempts.append({"strategy": "graph resolution",
                           "field": None,
                           "dois_found": seed_ids,
                           "titles_found": []})

    seed_block = {
        "requested_dois": sorted(set(requested_dois)),
        "requested_titles": requested_titles[:10],
        "parse_attempts": parse_attempts,
        "resolved_node_ids": seed_ids,
        "primary": seed_ids[0] if seed_ids else None,
    }

    keywords = extract_keywords(task_text) if task_text else []

    # ---- layered BFS --------------------------------------------------------
    pruning_log, stop_log, layers = [], [], []
    evidence = {}
    layer_of = {}
    direction_of = {}
    visited = set(seed_ids)
    frontier = list(seed_ids)
    for s in seed_ids:
        layer_of[s] = 0
        direction_of[s] = {"seed"}
        evidence[s] = [{"kind": "seed", "detail": "resolved from case/task input",
                        "locators": nodes[s].get("sources", [])}]
    budget_exhausted = False
    depth_reached = 0

    for depth in range(1, args.max_depth + 1):
        depth_reached = depth
        new_nodes = []
        pruned_this_layer = Counter()
        for parent in sorted(frontier):
            if budget_exhausted:
                break
            for direction, adj in (("backward", back_adj), ("forward", fwd_adj)):
                cands = []
                for tgt in adj.get(parent, []):
                    if tgt in visited:
                        continue
                    node = nodes.get(tgt)
                    if node is None:
                        continue
                    score = keyword_score(node, keywords) if keywords else 1
                    cbc = node.get("cited_by_count")
                    classic = bool(cbc is not None and cbc >= args.classic_citedby)
                    year = node.get("year")
                    base = {"node": tgt, "depth": depth, "parent": parent,
                            "direction": direction}
                    # 1) year filter with classic exception
                    if args.year_min is not None and year is not None and year < args.year_min:
                        if classic:
                            pruning_log.append({**base, "action": "kept",
                                                "reason": "classic_exception",
                                                "detail": "year %s < year-min %s but "
                                                "cited_by_count %s >= %s" %
                                                (year, args.year_min, cbc,
                                                 args.classic_citedby)})
                        else:
                            pruning_log.append({**base, "action": "pruned",
                                                "reason": "year_below_min",
                                                "detail": "year %s < year-min %s" %
                                                (year, args.year_min)})
                            pruned_this_layer["year_below_min"] += 1
                            continue
                    # 2) keyword relevance filter (stubs and classics exempt)
                    if keywords and score == 0 and not node.get("stub") and not classic:
                        pruning_log.append({**base, "action": "pruned",
                                            "reason": "keyword_irrelevant",
                                            "detail": "zero overlap with task keywords"})
                        pruned_this_layer["keyword_irrelevant"] += 1
                        continue
                    if node.get("stub"):
                        pruning_log.append({**base, "action": "kept",
                                            "reason": "kept_stub",
                                            "detail": "unresolved target kept as honest "
                                            "stub (locator only, no fabricated metadata)"})
                    cands.append({"id": tgt, "score": score, "classic": classic,
                                  "year": year or 0})
                # 3) per-parent per-direction branch cap (classics exempt)
                cands.sort(key=lambda c: (-c["score"], -c["year"], c["id"]))
                kept_nonclassic = 0
                for c in cands:
                    base = {"node": c["id"], "depth": depth, "parent": parent,
                            "direction": direction}
                    if c["classic"]:
                        if kept_nonclassic >= args.max_branch:
                            pruning_log.append({**base, "action": "kept",
                                                "reason": "classic_exception",
                                                "detail": "kept beyond branch cap "
                                                "(foundational classic)"})
                    else:
                        if kept_nonclassic >= args.max_branch:
                            pruning_log.append({**base, "action": "pruned",
                                                "reason": "branch_cap",
                                                "detail": "exceeds max-branch %d for "
                                                "parent %s/%s" % (args.max_branch,
                                                                  parent, direction)})
                            pruned_this_layer["branch_cap"] += 1
                            continue
                        kept_nonclassic += 1
                    # merge with an already-accepted node from another parent
                    existing = next((n for n in new_nodes if n["id"] == c["id"]), None)
                    if existing is not None:
                        existing["parents"].append({"parent": parent,
                                                    "direction": direction})
                        continue
                    # 4) global node budget
                    if len(visited) + len(new_nodes) >= args.max_nodes:
                        pruning_log.append({**base, "action": "pruned",
                                            "reason": "node_budget",
                                            "detail": "global max-nodes %d reached" %
                                            args.max_nodes})
                        pruned_this_layer["node_budget"] += 1
                        budget_exhausted = True
                        continue
                    new_nodes.append({"id": c["id"],
                                      "parents": [{"parent": parent,
                                                   "direction": direction}],
                                      "score": c["score"],
                                      "classic": c["classic"]})

        for item in new_nodes:
            nid = item["id"]
            visited.add(nid)
            layer_of[nid] = depth
            evidence[nid] = []
            for via in item["parents"]:
                direction_of.setdefault(nid, set()).add(via["direction"])
                edge_locators = []
                for e in edges:
                    if e["source"] == via["parent"] and e["target"] == nid and \
                            e["direction"] == via["direction"]:
                        edge_locators = e.get("sources", [])
                        break
                evidence[nid].append({
                    "kind": "edge",
                    "detail": "reached via %s edge %s -> %s (score=%s%s)" % (
                        via["direction"], via["parent"], nid, item["score"],
                        ", classic" if item["classic"] else ""),
                    "parent": via["parent"],
                    "direction": via["direction"],
                    "locators": edge_locators,
                })

        layers.append({
            "depth": depth,
            "added": [n["id"] for n in new_nodes],
            "n_added": len(new_nodes),
            "n_backward": sum(1 for n in new_nodes
                              if any(p["direction"] == "backward" for p in n["parents"])),
            "n_forward": sum(1 for n in new_nodes
                             if any(p["direction"] == "forward" for p in n["parents"])),
            "pruned": dict(sorted(pruned_this_layer.items())),
        })
        frontier = [n["id"] for n in new_nodes]

        if budget_exhausted:
            stop_log.append({"depth": depth, "reason": "node_budget",
                             "detail": "global node budget %d exhausted; traversal "
                             "stopped early" % args.max_nodes})
            break
        if not new_nodes:
            stop_log.append({"depth": depth, "reason": "zero_growth_layer",
                             "detail": "layer %d added zero new nodes; natural stop" % depth})
            break
        if depth == args.max_depth:
            stop_log.append({"depth": depth, "reason": "depth_limit",
                             "detail": "max-depth %d reached" % args.max_depth})

    if not seed_ids:
        stop_log.append({"depth": 0, "reason": "no_seed",
                         "detail": "no seed identifier could be resolved into the graph"})
    if budget_exhausted:
        uncertainty.append("node budget exhausted; deeper layers unexplored")

    # ---- trace subgraph ------------------------------------------------------
    included = sorted(visited)
    included_set = set(included)
    trace_edges = [e for e in edges
                   if e["source"] in included_set and e["target"] in included_set]
    trace_edges.sort(key=lambda e: (e["source"], e["target"], e["direction"]))

    candidates = []
    for nid in included:
        node = nodes[nid]
        candidates.append({
            "id": nid,
            "doi": node.get("doi"),
            "title": node.get("title"),
            "year": node.get("year"),
            "authors": node.get("authors") or [],
            "venue": node.get("venue"),
            "cited_by_count": node.get("cited_by_count"),
            "stub": bool(node.get("stub")),
            "title_hint": node.get("title_hint") if node.get("stub") else None,
            "layer": layer_of.get(nid),
            "directions": sorted(direction_of.get(nid, set())),
            "keyword_score": keyword_score(node, keywords) if keywords else None,
            "sources": node.get("sources", []),
        })
    candidates.sort(key=lambda c: (c["layer"] if c["layer"] is not None else 99, c["id"]))

    evidence_records = []
    for nid in included:
        for ev in evidence.get(nid, []):
            evidence_records.append({"node": nid, **ev})

    # ---- status --------------------------------------------------------------
    if not seed_ids:
        status = "failed"
        uncertainty.append("no resolvable seed: check case.json fields and task.md DOIs")
    elif len(included) == len(seed_ids):
        status = "partial"
        uncertainty.append("seed resolved but zero expansions survived pruning; "
                           "seed may have no resolvable edges in the corpus")
    elif any(r["status"] == "failed" for r in graph.get("registry", [])):
        status = "partial"
        uncertainty.append("some corpus files failed to parse (see sources registry); "
                           "graph may be incomplete")
    else:
        status = "ok"

    restored_used = sum(1 for e in trace_edges if e.get("direction_restored"))
    if restored_used:
        uncertainty.append(
            "%d forward edge(s) were restored from the corpus-wide reverse index "
            "(direction_restored=true); they derive from other records' reference "
            "lists, not from a native citation index" % restored_used)
    if any(n.get("stub") for n in nodes.values() if n["id"] in included_set):
        uncertainty.append("trace contains stub node(s): referenced works absent from "
                           "the corpus; kept with locators only, no metadata fabricated")
    pruned_nodes = [p["node"] for p in pruning_log if p["action"] == "pruned"]
    if pruned_nodes:
        uncertainty.append("omission note: %d node(s) pruned (%s); see pruning_log" % (
            len(pruned_nodes),
            ", ".join(sorted({p["reason"] for p in pruning_log
                              if p["action"] == "pruned"}))))

    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "seed": seed_block,
        "candidates": candidates,
        "edges": trace_edges,
        "layers": layers,
        "pruning_log": pruning_log,
        "stop_log": stop_log,
        "sources": graph.get("registry", []),
        "evidence_records": evidence_records,
        "uncertainty": uncertainty,
        "params": {
            "max_depth": args.max_depth, "max_nodes": args.max_nodes,
            "max_branch": args.max_branch, "year_min": args.year_min,
            "classic_citedby": args.classic_citedby, "keywords": keywords,
        },
        "graph_stats": graph.get("stats", {}),
    }

    # ---- output_contract mirroring: never drop a contracted field -----------
    contract = case.get("output_contract")
    contract_fields = []
    if isinstance(contract, dict):
        contract_fields = list(contract.keys())
    elif isinstance(contract, list):
        contract_fields = [f for f in contract if isinstance(f, str)]
    for f in contract_fields:
        if f not in result:
            result[f] = None
            uncertainty.append("field_not_produced: output_contract field '%s' has no "
                               "value from this pipeline; mirrored as null" % f)

    (outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    trace = {
        "case_id": case.get("case_id"),
        "seed_node_ids": seed_ids,
        "nodes": [{
            "id": nid,
            "layer": layer_of.get(nid),
            "directions": sorted(direction_of.get(nid, set())),
            "stub": bool(nodes[nid].get("stub")),
            "classic": bool((nodes[nid].get("cited_by_count") or 0) >= args.classic_citedby),
        } for nid in included],
        "edges": trace_edges,
        "layers": layers,
        "params": result["params"],
    }
    (outdir / "trace_graph.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": status != "failed",
        "status": status,
        "seeds": seed_ids,
        "nodes": len(included),
        "edges": len(trace_edges),
        "layers": len([l for l in layers if l["n_added"] > 0]),
        "pruned": len(pruned_nodes),
        "stop": stop_log[-1]["reason"] if stop_log else None,
        "result": str(outdir / "result.json"),
        "trace": str(outdir / "trace_graph.json"),
    }, ensure_ascii=False))
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
