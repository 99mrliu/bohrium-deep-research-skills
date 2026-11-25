#!/usr/bin/env python3
"""kg_pipeline.py - deterministic KG pipeline stages for e-kg-delivery-studio.

Python 3 standard library only. No network. Deterministic output: sorted
keys/order everywhere; no wall-clock timestamps unless --run-meta is given
(and then only inside a "run_meta" block).

Stages (subcommands):

  discover   scan an input dir shaped like the challenge runtime contract,
             normalize the corpus            -> <work>/corpus.json
  verify     mechanically verify the model-written extractions JSONL
             (quote-substring + address existence) -> <work>/verified.json
  build      apply merges/non-merges, detect preserved numeric conflicts
                                                   -> <work>/graph.json
  query      execute case.json query_specs against the graph
                                                   -> <work>/queries.json
  render     produce the full deliverable set (delegates to render.py)
                                                   -> <output>/*
  assemble   mirror case.json output_contract      -> <output>/result.json
  all        run every stage in the order above

Usage:
  python3 kg_pipeline.py all --input /input --work /app/work \
      --extractions /app/work/extractions.jsonl --output /app/output
  python3 kg_pipeline.py <stage> --help
"""

import argparse
import hashlib
import json
import os
import sys

SCHEMA_VERSION = "e-kg-delivery-studio/1.0"

NODE_OPS = {"node"}
EDGE_OPS = {"edge"}
OTHER_OPS = {"merge", "nonmerge", "unreported", "note"}
ALL_OPS = NODE_OPS | EDGE_OPS | OTHER_OPS

REQUIRED_FIELDS = {
    "node": ("id", "type", "label"),
    "edge": ("id", "source", "target", "relation"),
    "merge": ("keep", "drop", "key", "reason"),
    "nonmerge": ("a", "b", "reason"),
    "unreported": ("item",),
    "note": ("text",),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_key(text):
    """Normalization key for labels/aliases: casefold + strip spaces/hyphens."""
    return "".join(ch for ch in text.casefold() if ch not in " -_./()")


# ---------------------------------------------------------------------------
# stage: discover
# ---------------------------------------------------------------------------

def _materials_index_entries(obj):
    """Tolerate list / {'materials': [...]} / mapping shapes of material.json."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("materials"), list):
            return obj["materials"]
        # mapping shape: {source_id: {...}}
        out = []
        for key in sorted(obj):
            if isinstance(obj[key], dict):
                entry = dict(obj[key])
                entry.setdefault("source_id", key)
                out.append(entry)
        return out
    return []


def stage_discover(input_dir, work_dir):
    if not os.path.isdir(input_dir):
        raise SystemExit("discover: input dir not found: %s" % input_dir)
    files = sorted(os.listdir(input_dir))
    found = {"input_dir": os.path.abspath(input_dir), "files": files}
    warnings = []

    case = {}
    case_path = os.path.join(input_dir, "case.json")
    if os.path.isfile(case_path):
        case = read_json(case_path)
    else:
        warnings.append("case.json missing; case_id unknown, no output_contract")

    manifest_sources = {}
    man_path = os.path.join(input_dir, "corpus-manifest.json")
    if os.path.isfile(man_path):
        man = read_json(man_path)
        entries = man.get("sources", man if isinstance(man, list) else [])
        for entry in entries:
            if isinstance(entry, dict) and entry.get("source_id"):
                manifest_sources[entry["source_id"]] = entry
    else:
        warnings.append("corpus-manifest.json missing; role/doi cross-check skipped")

    if os.path.isfile(os.path.join(input_dir, "secondary-publisher.xml")):
        # Register presence only; never parse it (runtime contract).
        found["secondary_publisher_xml"] = "present (registered, not parsed)"

    index_entries = []
    mat_path = os.path.join(input_dir, "material.json")
    if os.path.isfile(mat_path):
        index_entries = _materials_index_entries(read_json(mat_path))
    else:
        warnings.append("material.json aggregate index missing (tolerated)")

    sources = []
    for name in files:
        if not name.endswith("-material.json"):
            continue
        path = os.path.join(input_dir, name)
        try:
            doc = read_json(path)
        except Exception as exc:  # unparsable input -> honest warning
            warnings.append("cannot parse %s: %s" % (name, exc))
            continue
        sid = doc.get("source_id") or name.replace("-material.json", "")
        paras = doc.get("paragraphs") or []
        norm_paras = []
        for i, p in enumerate(paras):
            if not isinstance(p, dict):
                warnings.append("%s: paragraph %d not an object, skipped" % (sid, i))
                continue
            norm_paras.append({
                "paragraph_id": str(p.get("paragraph_id", "%s-p%03d" % (sid, i + 1))),
                "section": str(p.get("section", "")),
                "text": str(p.get("text", "")),
            })
        role = "unknown"
        if sid in manifest_sources and manifest_sources[sid].get("role"):
            role = manifest_sources[sid]["role"]
        elif "primary" in name:
            role = "primary"
        elif "secondary" in name:
            role = "secondary"
        src = {
            "source_id": sid,
            "file": name,
            "role": role,
            "doi": doc.get("doi"),
            "title": doc.get("title"),
            "authors": doc.get("authors") or [],
            "paragraphs": norm_paras,
        }
        # Cross-check attribution against the manifest.
        man = manifest_sources.get(sid)
        if man:
            for field in ("doi", "title"):
                if man.get(field) and doc.get(field) and man[field] != doc[field]:
                    warnings.append("%s: manifest %s != material %s" % (sid, field, field))
            if man.get("sha256"):
                actual = sha256_of(path)
                if actual != man["sha256"]:
                    warnings.append("%s: sha256 mismatch with manifest (recorded, not fatal)" % sid)
        sources.append(src)

    sources.sort(key=lambda s: (s["role"] != "primary", s["source_id"]))
    roles = [s["role"] for s in sources]
    if "secondary" not in roles:
        warnings.append("no secondary material found; single-source corpus (tolerated)")

    corpus = {
        "schema": SCHEMA_VERSION,
        "case_id": case.get("case_id", "unknown-case"),
        "case": case,
        "synthetic": bool(case.get("synthetic", False)),
        "sources": sources,
        "materials_index": index_entries,
        "warnings": sorted(warnings),
        "found_files": found,
    }
    write_json(os.path.join(work_dir, "corpus.json"), corpus)
    print("discover: %d source(s), %d paragraph(s), %d warning(s)" % (
        len(sources), sum(len(s["paragraphs"]) for s in sources), len(warnings)))
    return corpus


# ---------------------------------------------------------------------------
# stage: verify
# ---------------------------------------------------------------------------

def _check_evidence(ev_list, para_index, require_nonempty):
    """Return list of (reason_code, reason) problems for one evidence list."""
    problems = []
    if require_nonempty and not ev_list:
        problems.append(("EMPTY_EVIDENCE", "node/edge requires >=1 evidence item"))
        return problems
    for j, ev in enumerate(ev_list or []):
        if not isinstance(ev, dict):
            problems.append(("MISSING_FIELD", "evidence[%d] not an object" % j))
            continue
        sid, pid, quote = ev.get("source_id"), ev.get("paragraph_id"), ev.get("quote")
        if not sid or not pid or quote is None:
            problems.append(("MISSING_FIELD",
                             "evidence[%d] needs source_id+paragraph_id+quote" % j))
            continue
        para = para_index.get((sid, pid))
        if para is None:
            problems.append(("ADDRESS_NOT_FOUND",
                             "no paragraph %s/%s in corpus" % (sid, pid)))
            continue
        if not quote or quote not in para["text"]:
            problems.append(("QUOTE_NOT_SUBSTRING",
                             "quote is not an exact substring of %s/%s" % (sid, pid)))
    return problems


def stage_verify(work_dir, extractions_path):
    corpus = read_json(os.path.join(work_dir, "corpus.json"))
    para_index = {}
    for src in corpus["sources"]:
        for p in src["paragraphs"]:
            para_index[(src["source_id"], p["paragraph_id"])] = p

    accepted, rejected = [], []
    stats = {"total_lines": 0, "comment_or_blank": 0, "accepted": 0,
             "rejected": 0, "by_op": {}, "by_reason": {}}

    def reject(line_no, op, code, reason, raw):
        rejected.append({"line_no": line_no, "op": op, "reason_code": code,
                         "reason": reason, "raw": raw[:160]})
        stats["by_reason"][code] = stats["by_reason"].get(code, 0) + 1

    if not os.path.isfile(extractions_path):
        # Missing model artifact is tolerated: empty graph, honest report.
        print("verify: extractions file missing (%s); empty extraction accepted"
              % extractions_path)
    else:
        pending = []
        with open(extractions_path, "r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, 1):
                stats["total_lines"] += 1
                line = raw.strip()
                if not line or line.startswith("#"):
                    stats["comment_or_blank"] += 1
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    reject(line_no, None, "MALFORMED_JSON", str(exc), line)
                    continue
                pending.append((line_no, item, line))

        # Pass 1: nodes (so edge/merge endpoints can be checked in pass 2).
        node_ids = set()
        for line_no, item, raw in pending:
            op = item.get("op") if isinstance(item, dict) else None
            if op != "node":
                continue
            problems = _required(item, op)
            if item.get("id") in node_ids:
                problems.append(("DUPLICATE_ID", "node id %r already defined"
                                 % item.get("id")))
            problems += _check_evidence(item.get("evidence"), para_index, True)
            if problems:
                for code, reason in problems:
                    reject(line_no, op, code, reason, raw)
            else:
                node_ids.add(item["id"])
                accepted.append(_with_line(line_no, item))
                stats["by_op"][op] = stats["by_op"].get(op, 0) + 1

        # Pass 2: everything else.
        for line_no, item, raw in pending:
            op = item.get("op") if isinstance(item, dict) else None
            if op == "node":
                continue
            if op not in ALL_OPS:
                reject(line_no, op, "UNKNOWN_OP", "op %r not in %s"
                       % (op, sorted(ALL_OPS)), raw)
                continue
            problems = _required(item, op)
            if op == "edge":
                for ep in (item.get("source"), item.get("target")):
                    if ep not in node_ids:
                        problems.append(("DANGLING_ENDPOINT",
                                         "node %r not defined" % ep))
                problems += _check_evidence(item.get("evidence"), para_index, True)
            elif op in ("merge", "nonmerge"):
                keys = ("keep", "drop") if op == "merge" else ("a", "b")
                for k in keys:
                    if item.get(k) not in node_ids:
                        problems.append(("DANGLING_ENDPOINT",
                                         "node %r not defined" % item.get(k)))
                problems += _check_evidence(item.get("evidence"), para_index, False)
            else:
                problems += _check_evidence(item.get("evidence"), para_index, False)
            if problems:
                for code, reason in problems:
                    reject(line_no, op, code, reason, raw)
            else:
                accepted.append(_with_line(line_no, item))
                stats["by_op"][op] = stats["by_op"].get(op, 0) + 1

    stats["accepted"] = len(accepted)
    stats["rejected"] = len(rejected)
    verified = {"schema": SCHEMA_VERSION, "extractions_file": extractions_path,
                "accepted": accepted, "rejected": rejected, "stats": stats}
    write_json(os.path.join(work_dir, "verified.json"), verified)
    print("verify: %d/%d line(s) accepted, %d rejected (%s)"
          % (stats["accepted"], stats["total_lines"], stats["rejected"],
             ", ".join("%s=%d" % (k, stats["by_reason"][k])
                       for k in sorted(stats["by_reason"])) or "no failures"))
    return verified


def _required(item, op):
    out = []
    for field in REQUIRED_FIELDS[op]:
        if not isinstance(item, dict) or item.get(field) in (None, ""):
            out.append(("MISSING_FIELD", "op %s requires field %r" % (op, field)))
    return out


def _with_line(line_no, item):
    item = dict(item)
    item["line_no"] = line_no
    return item


# ---------------------------------------------------------------------------
# stage: build
# ---------------------------------------------------------------------------

def _enrich_evidence(ev_list, corpus):
    sections = {}
    for src in corpus["sources"]:
        for p in src["paragraphs"]:
            sections[(src["source_id"], p["paragraph_id"])] = p["section"]
    out = []
    for ev in ev_list or []:
        e = {"source_id": ev["source_id"], "paragraph_id": ev["paragraph_id"],
             "quote": ev["quote"]}
        e["section"] = sections.get((e["source_id"], e["paragraph_id"]), "")
        out.append(e)
    return out


def stage_build(work_dir):
    corpus = read_json(os.path.join(work_dir, "corpus.json"))
    verified = read_json(os.path.join(work_dir, "verified.json"))
    warnings = []

    nodes, edges = {}, {}
    merges, nonmerges, unreported, notes = [], [], [], []

    for item in verified["accepted"]:
        op = item["op"]
        if op == "node":
            nodes[item["id"]] = {
                "id": item["id"], "type": item["type"], "label": item["label"],
                "aliases": sorted(set(item.get("aliases") or [])),
                "qualifiers": item.get("qualifiers") or {},
                "evidence": _enrich_evidence(item.get("evidence"), corpus),
                "merged_from": [],
            }
        elif op == "edge":
            edges[item["id"]] = {
                "id": item["id"], "source": item["source"],
                "target": item["target"], "relation": item["relation"],
                "qualifiers": item.get("qualifiers") or {},
                "evidence": _enrich_evidence(item.get("evidence"), corpus),
            }
        elif op == "merge":
            merges.append(item)
        elif op == "nonmerge":
            nonmerges.append({
                "a": item["a"], "b": item["b"], "reason": item["reason"],
                "normalized_key": item.get("key") or norm_key(
                    nodes.get(item["a"], {}).get("label", "")),
                "evidence": _enrich_evidence(item.get("evidence"), corpus),
            })
        elif op == "unreported":
            unreported.append({
                "item": item["item"], "context": item.get("context", ""),
                "evidence": _enrich_evidence(item.get("evidence"), corpus),
            })
        elif op == "note":
            notes.append({"text": item["text"],
                          "evidence": _enrich_evidence(item.get("evidence"), corpus)})

    # Apply merges in acceptance order: rewire edges, fold evidence/aliases.
    applied_merges = []
    for m in merges:
        keep, drop = m["keep"], m["drop"]
        if keep not in nodes or drop not in nodes:
            warnings.append("merge line %d skipped: endpoint missing" % m["line_no"])
            continue
        kn, dn = nodes[keep], nodes[drop]
        kn["aliases"] = sorted((set(kn["aliases"]) | {dn["label"]} | set(dn["aliases"]))
                               - {kn["label"]})
        seen = {(e["source_id"], e["paragraph_id"], e["quote"]) for e in kn["evidence"]}
        for ev in dn["evidence"]:
            k = (ev["source_id"], ev["paragraph_id"], ev["quote"])
            if k not in seen:
                kn["evidence"].append(ev)
                seen.add(k)
        kn["merged_from"].append(drop)
        dead_edges = []
        for eid, e in edges.items():
            if e["source"] == drop:
                e["source"] = keep
            if e["target"] == drop:
                e["target"] = keep
            if e["source"] == e["target"]:
                dead_edges.append(eid)
        for eid in dead_edges:
            warnings.append("edge %s became self-loop after merge of %s->%s; dropped"
                            % (eid, drop, keep))
            del edges[eid]
        del nodes[drop]
        applied_merges.append({
            "keep": keep, "drop": drop, "key": m["key"], "reason": m["reason"],
            "evidence": _enrich_evidence(m.get("evidence"), corpus),
        })

    # Deduplicate edges that became identical after rewiring.
    seen_edges = {}
    for eid in sorted(edges):
        e = edges[eid]
        sig = (e["source"], e["target"], e["relation"],
               json.dumps(e["qualifiers"], sort_keys=True))
        if sig in seen_edges:
            keep_e = edges[seen_edges[sig]]
            have = {(x["source_id"], x["paragraph_id"], x["quote"])
                    for x in keep_e["evidence"]}
            for ev in e["evidence"]:
                k = (ev["source_id"], ev["paragraph_id"], ev["quote"])
                if k not in have:
                    keep_e["evidence"].append(ev)
                    have.add(k)
            warnings.append("edge %s merged into %s (identical after node merge)"
                            % (eid, keep_e["id"]))
            del edges[eid]
        else:
            seen_edges[sig] = eid

    # Preserved conflicts: claims about the same metric with different values.
    conflicts = _detect_conflicts(nodes, edges)

    node_list = [nodes[k] for k in sorted(nodes)]
    edge_list = [edges[k] for k in sorted(edges)]
    graph = {
        "schema": SCHEMA_VERSION,
        "case_id": corpus["case_id"],
        "synthetic": corpus["synthetic"],
        "nodes": node_list,
        "edges": edge_list,
        "merges": applied_merges,
        "nonmerges": sorted(nonmerges, key=lambda x: (x["a"], x["b"])),
        "unreported": sorted(unreported, key=lambda x: x["item"]),
        "notes": notes,
        "conflicts": conflicts,
        "warnings": sorted(warnings),
        "stats": {"nodes": len(node_list), "edges": len(edge_list),
                  "merges": len(applied_merges), "nonmerges": len(nonmerges),
                  "unreported": len(unreported), "conflicts": len(conflicts)},
    }
    write_json(os.path.join(work_dir, "graph.json"), graph)
    print("build: %d node(s), %d edge(s), %d merge(s), %d non-merge(s), "
          "%d preserved conflict(s)" % (len(node_list), len(edge_list),
                                        len(applied_merges), len(nonmerges),
                                        len(conflicts)))
    return graph


def _detect_conflicts(nodes, edges):
    claims_of_metric = {}
    conditions_of = {}
    for e in edges.values():
        if e["relation"] == "concerns" and e["source"] in nodes:
            claims_of_metric.setdefault(e["target"], []).append(e["source"])
        if e["relation"] == "under" and e["source"] in nodes:
            tgt = nodes.get(e["target"], {})
            conditions_of.setdefault(e["source"], []).append(
                (e["target"], tgt.get("label", e["target"])))
    conflicts = []
    for metric_id in sorted(claims_of_metric):
        members = []
        for cid in sorted(set(claims_of_metric[metric_id])):
            node = nodes.get(cid)
            if not node or node.get("type") != "claim":
                continue
            value = (node.get("qualifiers") or {}).get("value")
            if value is None:
                continue
            members.append({"claim_id": cid, "label": node["label"], "value": value,
                            "conditions": sorted(l for _, l in conditions_of.get(cid, [])),
                            "condition_ids": sorted(i for i, _ in conditions_of.get(cid, []))})
        values = sorted({m["value"] for m in members})
        if len(values) > 1:
            conflicts.append({
                "metric_id": metric_id,
                "metric_label": nodes.get(metric_id, {}).get("label", metric_id),
                "claims": members,
                "distinct_values": values,
                "resolution": "preserved",
                "note": "Competing numeric values kept as separate claim nodes; "
                        "conditions differ and are never merged into one conclusion.",
            })
    return conflicts


# ---------------------------------------------------------------------------
# stage: query
# ---------------------------------------------------------------------------

def _resolve_node(ref, nodes):
    if ref in nodes:
        return nodes[ref]["id"], None
    key = norm_key(str(ref))
    hits = [n["id"] for n in nodes.values()
            if norm_key(n["label"]) == key or key in {norm_key(a) for a in n["aliases"]}]
    hits.sort()
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, "ambiguous reference %r matches %s" % (ref, hits)
    return None, "no node matches %r" % ref


def _adjacency(edges):
    adj = {}
    for e in edges.values():
        adj.setdefault(e["source"], []).append((e["target"], e["id"]))
        adj.setdefault(e["target"], []).append((e["source"], e["id"]))
    for k in adj:
        adj[k].sort()
    return adj


def _collect_evidence(node_ids, edge_ids, nodes, edges):
    seen, out = set(), []
    for nid in sorted(node_ids):
        for ev in nodes[nid]["evidence"]:
            k = (ev["source_id"], ev["paragraph_id"], ev["quote"])
            if k not in seen:
                seen.add(k)
                out.append(dict(ev, item_kind="node", item_id=nid))
    for eid in sorted(edge_ids):
        for ev in edges[eid]["evidence"]:
            k = (ev["source_id"], ev["paragraph_id"], ev["quote"])
            if k not in seen:
                seen.add(k)
                out.append(dict(ev, item_kind="edge", item_id=eid))
    out.sort(key=lambda x: (x["source_id"], x["paragraph_id"], x["quote"]))
    return out


def stage_query(work_dir):
    corpus = read_json(os.path.join(work_dir, "corpus.json"))
    graph = read_json(os.path.join(work_dir, "graph.json"))
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    adj = _adjacency(edges)

    specs = (corpus["case"].get("query_specs") or [])[:8]  # budget guard
    global_undetermined = [
        {"item": u["item"],
         "reason": "unreported in the corpus%s" % (
             ": " + u["context"] if u.get("context") else ""),
         "evidence": u["evidence"]}
        for u in graph["unreported"]
    ]

    results = []
    for spec in specs:
        qid = str(spec.get("id", "q%d" % (len(results) + 1)))
        qtype = spec.get("type", "")
        params = spec.get("params") or {}
        res = {"id": qid, "type": qtype, "params": params,
               "description": spec.get("description", ""),
               "status": "ok", "messages": [], "nodes": [], "edges": [],
               "paths": [], "conflict_check": [], "evidence": [],
               "undetermined": list(global_undetermined)}
        try:
            if qtype == "neighborhood":
                _query_neighborhood(res, params, nodes, edges, adj)
            elif qtype == "relation":
                _query_relation(res, params, nodes, edges)
            elif qtype == "path":
                _query_path(res, params, nodes, edges, adj, graph)
            else:
                res["status"] = "unsupported"
                res["messages"].append("query type %r not supported "
                                       "(neighborhood|relation|path)" % qtype)
        except Exception as exc:  # never let one query kill the run
            res["status"] = "error"
            res["messages"].append("internal error: %s" % exc)
        res["nodes"].sort()
        res["edges"].sort()
        if res["status"] == "ok" and not res["edges"] and not res["nodes"]:
            res["status"] = "empty"
            res["messages"].append("no matching graph content (honest empty result)")
        res["evidence"] = _collect_evidence(res["nodes"], res["edges"], nodes, edges)
        results.append(res)

    out = {"schema": SCHEMA_VERSION, "queries": results,
           "stats": {"executed": len(results),
                     "ok": sum(1 for r in results if r["status"] == "ok"),
                     "empty": sum(1 for r in results if r["status"] == "empty"),
                     "failed": sum(1 for r in results
                                   if r["status"] in ("error", "unsupported",
                                                      "no_match", "ambiguous"))}}
    write_json(os.path.join(work_dir, "queries.json"), out)
    print("query: %d executed (%d ok, %d empty, %d failed)" % (
        out["stats"]["executed"], out["stats"]["ok"], out["stats"]["empty"],
        out["stats"]["failed"]))
    return out


def _query_neighborhood(res, params, nodes, edges, adj):
    ref = params.get("node", "")
    nid, err = _resolve_node(ref, nodes)
    if err:
        res["status"] = "ambiguous" if err.startswith("ambiguous") else "no_match"
        res["messages"].append(err)
        return
    depth = int(params.get("depth", 1))
    seen, frontier = {nid}, {nid}
    for _ in range(max(depth, 0)):
        nxt = set()
        for cur in frontier:
            for nb, _eid in adj.get(cur, []):
                if nb not in seen:
                    seen.add(nb)
                    nxt.add(nb)
        frontier = nxt
    res["nodes"] = list(seen)
    res["edges"] = [e["id"] for e in edges.values()
                    if e["source"] in seen and e["target"] in seen]


def _query_relation(res, params, nodes, edges):
    rel = str(params.get("relation", "")).casefold()
    matched = [e for e in edges.values() if e["relation"].casefold() == rel]
    res["edges"] = [e["id"] for e in matched]
    res["nodes"] = sorted({e["source"] for e in matched} |
                          {e["target"] for e in matched})
    if not matched:
        res["undetermined"].append({
            "item": "relation %r" % params.get("relation", ""),
            "reason": "no edges of this relation type; no evidence in corpus",
            "evidence": []})


def _query_path(res, params, nodes, edges, adj, graph):
    src, err = _resolve_node(params.get("from", ""), nodes)
    if err:
        res["status"] = "ambiguous" if err.startswith("ambiguous") else "no_match"
        res["messages"].append("from: " + err)
        return
    dst, err = _resolve_node(params.get("to", ""), nodes)
    if err:
        res["status"] = "ambiguous" if err.startswith("ambiguous") else "no_match"
        res["messages"].append("to: " + err)
        return
    max_len = int(params.get("max_len", 3))
    paths, cap = [], 20
    stack = [(src, [src], [])]
    while stack and len(paths) < cap:
        cur, pnodes, pedges = stack.pop()
        if cur == dst and pedges:
            paths.append({"nodes": pnodes, "edges": pedges})
            continue
        if len(pedges) >= max_len:
            continue
        for nb, eid in reversed(adj.get(cur, [])):
            if nb not in pnodes:
                stack.append((nb, pnodes + [nb], pedges + [eid]))
    paths.sort(key=lambda p: (len(p["edges"]), p["edges"]))
    res["paths"] = paths
    used_n, used_e = {src, dst}, set()
    for p in paths:
        used_n.update(p["nodes"])
        used_e.update(p["edges"])
    if params.get("check_conflicts"):
        # Attach every preserved conflict touching the path subgraph; if none
        # touches it, still list all conflicts so nothing is silently dropped.
        touching = [c for c in graph.get("conflicts", [])
                    if {m["claim_id"] for m in c["claims"]} & used_n]
        res["conflict_check"] = touching if touching else list(graph.get("conflicts", []))
        for c in res["conflict_check"]:
            used_n.add(c["metric_id"])
            for m in c["claims"]:
                used_n.add(m["claim_id"])
                used_n.update(m.get("condition_ids", []))
        if not res["conflict_check"]:
            res["undetermined"].append({
                "item": "contradiction check",
                "reason": "no conflicting numeric claims detected on this metric",
                "evidence": []})
        # Show the induced subgraph over the final node set so conflict
        # claims stay connected to their samples/metrics/conditions.
        used_e = {e["id"] for e in edges.values()
                  if e["source"] in used_n and e["target"] in used_n}
    res["nodes"] = list(used_n)
    res["edges"] = list(used_e)
    if not paths:
        res["undetermined"].append({
            "item": "path %s -> %s" % (params.get("from"), params.get("to")),
            "reason": "no path of length <= %d found in the graph" % max_len,
            "evidence": []})


# ---------------------------------------------------------------------------
# stage: render  (delegates to render.py)
# ---------------------------------------------------------------------------

def stage_render(work_dir, output_dir):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render as render_mod  # same-bundle import
    written = render_mod.render_all(work_dir, output_dir)
    print("render: %d artifact(s) written to %s" % (len(written), output_dir))
    return written


# ---------------------------------------------------------------------------
# stage: assemble
# ---------------------------------------------------------------------------

def stage_assemble(work_dir, output_dir, run_meta=False):
    corpus = read_json(os.path.join(work_dir, "corpus.json"))
    graph = read_json(os.path.join(work_dir, "graph.json"))
    queries = read_json(os.path.join(work_dir, "queries.json"))
    verified = read_json(os.path.join(work_dir, "verified.json"))
    case = corpus["case"]
    contract = case.get("output_contract") or {}

    uncertainty = []
    for c in graph.get("conflicts", []):
        uncertainty.append(
            "metric %s has competing values %s under different conditions; "
            "preserved as separate claims (resolution=preserved)"
            % (c["metric_label"], ", ".join(c["distinct_values"])))
    for r in queries["queries"]:
        if r["status"] in ("ambiguous", "no_match"):
            uncertainty.append("query %s: %s" % (r["id"], "; ".join(r["messages"])))
    for w in corpus["warnings"] + graph["warnings"]:
        uncertainty.append("warning: " + w)

    evidence_notes = [n["text"] for n in graph["notes"]]
    evidence_notes.append(
        "verification: %d/%d extraction lines accepted, %d rejected (%s)" % (
            verified["stats"]["accepted"], verified["stats"]["total_lines"],
            verified["stats"]["rejected"],
            ", ".join("%s=%d" % (k, verified["stats"]["by_reason"][k])
                      for k in sorted(verified["stats"]["by_reason"])) or "none"))
    for r in verified["rejected"]:
        evidence_notes.append("rejected line %d [%s]: %s"
                              % (r["line_no"], r["reason_code"], r["reason"]))

    artifacts = sorted(f for f in os.listdir(output_dir)
                       if f != "result.json"
                       and os.path.isfile(os.path.join(output_dir, f))) \
        if os.path.isdir(output_dir) else []

    key_values = {
        "case_id": corpus["case_id"],
        "graph": {"nodes": graph["nodes"], "edges": graph["edges"],
                  "merges": graph["merges"], "nonmerges": graph["nonmerges"],
                  "conflicts": graph["conflicts"], "stats": graph["stats"]},
        "queries": queries["queries"],
        "evidence_notes": evidence_notes,
        "unreported": graph["unreported"],
        "uncertainty": uncertainty,
        "status": None,  # computed below
    }
    contract_notes = {}
    result = {}
    for key in sorted(contract):
        if key in key_values and key_values[key] is not None:
            result[key] = key_values[key]
        elif key == "status":
            continue
        else:
            result[key] = None
            contract_notes[key] = ("no producer for contract key %r; set to null "
                                   "honestly instead of omitting it" % key)
    if not contract:  # no contract declared: still give a useful result
        result = {k: v for k, v in key_values.items() if v is not None}

    unproduced = [k for k, v in result.items() if v is None]
    failed_q = [r for r in queries["queries"]
                if r["status"] in ("error", "unsupported")]
    status = "success"
    if unproduced or failed_q:
        status = "partial"
    if not graph["nodes"]:
        status = "unable"
    result["status"] = status

    result.update({
        "schema": SCHEMA_VERSION,
        "case_id": corpus["case_id"],
        "synthetic": corpus["synthetic"],
        "sources": [{"source_id": s["source_id"], "role": s["role"],
                     "doi": s["doi"], "title": s["title"], "authors": s["authors"],
                     "paragraph_count": len(s["paragraphs"])}
                    for s in corpus["sources"]],
        "artifacts": artifacts,
        "contract_notes": contract_notes,
        "change_records": [
            "discover: corpus normalized from input dir",
            "verify: %d accepted / %d rejected extraction lines" % (
                verified["stats"]["accepted"], verified["stats"]["rejected"]),
            "build: %d merges applied, %d non-merges recorded, %d conflicts preserved"
            % (graph["stats"]["merges"], graph["stats"]["nonmerges"],
               graph["stats"]["conflicts"]),
            "query: %d query specs executed" % queries["stats"]["executed"],
            "render: %d artifacts written" % len(artifacts),
            "assemble: result.json mirrored against output_contract",
        ],
    })
    if run_meta:
        import datetime
        result["run_meta"] = {
            "generated_at": datetime.datetime.now().astimezone().isoformat(),
            "note": "wall-clock data lives ONLY in this block and is excluded "
                    "from deterministic comparisons",
        }
    write_json(os.path.join(output_dir, "result.json"), result)
    print("assemble: result.json status=%s, contract keys=%d, null keys=%s"
          % (status, len(contract), unproduced or "none"))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kg_pipeline.py",
        description="Deterministic KG pipeline (stdlib only): discover / verify "
                    "/ build / query / render / assemble / all.")
    sub = ap.add_subparsers(dest="stage", required=True)

    def add_io(p, need_input=False, need_output=False, need_extractions=False):
        if need_input:
            p.add_argument("--input", required=True, help="input dir (/input)")
        p.add_argument("--work", required=True, help="work dir (/app/work)")
        if need_extractions:
            p.add_argument("--extractions", required=True,
                           help="model-written extractions.jsonl")
        if need_output:
            p.add_argument("--output", required=True, help="output dir (/app/output)")

    p = sub.add_parser("discover", help="scan input dir -> <work>/corpus.json")
    add_io(p, need_input=True)
    p = sub.add_parser("verify", help="verify extractions JSONL -> <work>/verified.json")
    add_io(p, need_extractions=True)
    p = sub.add_parser("build", help="build graph -> <work>/graph.json")
    add_io(p)
    p = sub.add_parser("query", help="execute query_specs -> <work>/queries.json")
    add_io(p)
    p = sub.add_parser("render", help="render deliverables -> <output>/")
    add_io(p, need_output=True)
    p = sub.add_parser("assemble", help="mirror output_contract -> <output>/result.json")
    add_io(p, need_output=True)
    p.add_argument("--run-meta", action="store_true",
                   help="include a wall-clock run_meta block (off by default)")
    p = sub.add_parser("all", help="run all stages in order")
    add_io(p, need_input=True, need_output=True, need_extractions=True)
    p.add_argument("--run-meta", action="store_true")

    args = ap.parse_args(argv)
    if hasattr(args, "work"):
        os.makedirs(args.work, exist_ok=True)
    if hasattr(args, "output") and args.output:
        os.makedirs(args.output, exist_ok=True)

    if args.stage == "discover":
        stage_discover(args.input, args.work)
    elif args.stage == "verify":
        stage_verify(args.work, args.extractions)
    elif args.stage == "build":
        stage_build(args.work)
    elif args.stage == "query":
        stage_query(args.work)
    elif args.stage == "render":
        stage_render(args.work, args.output)
    elif args.stage == "assemble":
        stage_assemble(args.work, args.output, run_meta=args.run_meta)
    elif args.stage == "all":
        stage_discover(args.input, args.work)
        stage_verify(args.work, args.extractions)
        stage_build(args.work)
        stage_query(args.work)
        stage_render(args.work, args.output)
        stage_assemble(args.work, args.output, run_meta=args.run_meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
