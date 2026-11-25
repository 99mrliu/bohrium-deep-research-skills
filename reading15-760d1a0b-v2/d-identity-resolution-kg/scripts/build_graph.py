#!/usr/bin/env python3
"""build_graph.py — resolve extracted facts onto canonical entities, build the
graph, and register cross-paper numeric conflicts.

Inputs (in --work):
  entity_map.json    from adjudicate.py
  extractions.json   the model's fact artifact:
    {"nodes":  [{"surface","type","source_id","paragraph_id","quote"}],
     "edges":  [{"subject","object","relation","source_id","paragraph_id",
                 "quote","qualifiers": {...}}],
     "claims": [{"entity","metric","value","unit","conditions":[...],
                 "source_id","paragraph_id","quote"}],
     "unreported": [{"item","reason","source_id","paragraph_id","quote"}],
     "notes": [...]}

Resolution rule: a surface form + its source_id maps to the identity atom
(norm_key(surface), source_id) and then to the canonical entity; surfaces with
no candidate-derived entity become singleton entities (E-ids continue in sorted
order, so IDs stay deterministic). Numeric claims NEVER merge: claims on the
same canonical entity + same normalized metric but different values are
preserved as separate claim nodes, linked by a conflicts-with edge annotated
with the differing conditions and registered in conflict_registry.json with
resolution="preserved".

Outputs (work): graph.json, conflict_registry.json, extraction_report.json.

Usage: python3 build_graph.py --work /app/work
"""
import argparse
import os
import sys

import kgcommon as K

RELATION_VOCAB = ["uses", "measures", "improves", "suppresses",
                  "decomposes-into", "concerns", "conflicts-with", "aliases"]


def _resolve(surface, source_id, entity_map, singletons):
    key = K.norm_key(surface)
    atom_id = "%s|%s" % (key, source_id)
    eid = entity_map["atom_index"].get(atom_id)
    if eid:
        return eid, False
    if (key, source_id) not in singletons:
        singletons[(key, source_id)] = {
            "surface": surface, "source_id": source_id, "key": key}
    return None, True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True, help="work directory")
    args = ap.parse_args(argv)
    work = args.work
    try:
        entity_map = K.load_json(os.path.join(work, "entity_map.json"))
        corpus = K.load_json(os.path.join(work, "corpus.json"))
    except Exception as exc:
        print("ERROR: %s; run discover/candidates/adjudicate first" % exc,
              file=sys.stderr)
        return 2
    ext_path = os.path.join(work, "extractions.json")
    if not os.path.isfile(ext_path):
        print("ERROR: extractions.json missing in %s" % work, file=sys.stderr)
        return 2
    try:
        ext = K.load_json(ext_path)
    except Exception as exc:
        print("ERROR: extractions.json unparsable: %s" % exc, file=sys.stderr)
        return 2

    warnings = []
    entities = {e["entity_id"]: dict(e) for e in entity_map["entities"]}
    singletons = {}

    def resolve_or_make(surface, source_id):
        eid, is_new = _resolve(surface, source_id, entity_map, singletons)
        if is_new:
            info = singletons[(K.norm_key(surface), source_id)]
            return info, True
        return entities[eid], False

    # --- pass 1: register every surface the model used (nodes, edge
    # endpoints, claim entities) so singletons are created for all of them ---
    node_specs = {}
    for item in ext.get("nodes", []):
        if not isinstance(item, dict) or not item.get("surface"):
            warnings.append("malformed node skipped: %r" % (item,))
            continue
        holder, is_singleton = resolve_or_make(item["surface"], item.get("source_id"))
        key = holder["entity_id"] if not is_singleton else \
            (K.norm_key(item["surface"]), item.get("source_id"))
        node_specs[key] = item
    for item in ext.get("edges", []):
        if not isinstance(item, dict):
            continue
        for end in ("subject", "object"):
            if item.get(end) and item.get("source_id"):
                resolve_or_make(item[end], item["source_id"])
    for item in ext.get("claims", []):
        if isinstance(item, dict) and item.get("entity") and item.get("source_id"):
            resolve_or_make(item["entity"], item["source_id"])

    # --- create singleton entities (deterministic order) --------------------
    next_num = max(int(eid[1:]) for eid in entities) + 1 if entities else 1
    for (key, sid) in sorted(singletons):
        info = singletons[(key, sid)]
        eid = "E%04d" % next_num
        next_num += 1
        spec = node_specs.get((key, sid), {})
        entities[eid] = {
            "entity_id": eid,
            "type": spec.get("type") or K.guess_type(info["surface"]),
            "canonical_surface": info["surface"],
            "aliases": [info["surface"]],
            "member_keys": [key],
            "source_ids": [sid],
            "cross_paper": False,
            "singleton": True,
            "mentions": [],
        }
        singletons[(key, sid)]["entity_id"] = eid

    def eid_of(surface, source_id):
        key = K.norm_key(surface)
        eid = entity_map["atom_index"].get("%s|%s" % (key, source_id))
        if eid:
            return eid
        return singletons.get((key, source_id), {}).get("entity_id")

    # apply model-provided types / extra mentions to resolved entities
    for key, spec in sorted(node_specs.items(), key=lambda kv: str(kv[0])):
        target_eid = eid_of(spec["surface"], spec.get("source_id"))
        if not target_eid:
            continue
        ent = entities[target_eid]
        if spec.get("type") and ent.get("type") in (None, "unknown"):
            ent["type"] = spec["type"]
        if spec.get("paragraph_id") and spec.get("quote"):
            mention = {"surface": spec["surface"],
                       "source_id": spec.get("source_id"),
                       "paragraph_id": spec["paragraph_id"],
                       "quote": spec["quote"]}
            if mention not in ent["mentions"]:
                ent["mentions"].append(mention)
                ent["mentions"].sort(key=lambda m: (m["source_id"] or "",
                                                    m["paragraph_id"] or "",
                                                    m["surface"]))

    # --- edges ---------------------------------------------------------------
    edges = []
    for item in ext.get("edges", []):
        try:
            sub = eid_of(item["subject"], item["source_id"])
            obj = eid_of(item["object"], item["source_id"])
        except (KeyError, TypeError) as exc:
            warnings.append("malformed edge skipped: %s" % exc)
            continue
        if not sub or not obj:
            warnings.append("edge with unresolvable endpoint skipped: %r" % (item,))
            continue
        rel = item.get("relation")
        if rel not in RELATION_VOCAB:
            warnings.append("relation %r not in documented vocabulary" % rel)
        edges.append({
            "relation": rel, "subject": sub, "object": obj,
            "source_id": item.get("source_id"),
            "paragraph_id": item.get("paragraph_id"),
            "quote": item.get("quote"),
            "qualifiers": item.get("qualifiers") or {},
        })
    edges.sort(key=lambda e: (e["subject"], str(e["relation"]), e["object"],
                              str(e["source_id"]), str(e["paragraph_id"])))

    # --- claims (never merged; conflicts preserved) ---------------------------
    claims = []
    for item in ext.get("claims", []):
        if not isinstance(item, dict) or "value" not in item:
            warnings.append("malformed claim skipped: %r" % (item,))
            continue
        eid = eid_of(item.get("entity", ""), item.get("source_id"))
        if not eid:
            warnings.append("claim with unresolvable entity skipped: %r" % (item,))
            continue
        claims.append({
            "entity_id": eid,
            "metric": str(item.get("metric")),
            "metric_key": K.norm_key(item.get("metric")),
            "value": item["value"],
            "unit": item.get("unit"),
            "conditions": sorted(str(c) for c in (item.get("conditions") or [])),
            "source_id": item.get("source_id"),
            "paragraph_id": item.get("paragraph_id"),
            "quote": item.get("quote"),
        })
    claims.sort(key=lambda c: (c["entity_id"], c["metric_key"],
                               str(c["value"]), str(c["source_id"])))
    claim_nodes = []
    for idx, c in enumerate(claims, 1):
        cid = "C%04d" % idx
        c["claim_id"] = cid
        claim_nodes.append({
            "claim_id": cid, "type": "claim", "entity_id": c["entity_id"],
            "metric": c["metric"], "metric_key": c["metric_key"],
            "value": c["value"], "unit": c["unit"],
            "conditions": c["conditions"], "source_id": c["source_id"],
            "paragraph_id": c["paragraph_id"], "quote": c["quote"],
        })

    # --- conflict detection ----------------------------------------------------
    groups = {}
    for c in claims:
        groups.setdefault((c["entity_id"], c["metric_key"]), []).append(c)
    conflicts = []
    conflict_edges = []
    for (eid, mkey) in sorted(groups):
        members = groups[(eid, mkey)]
        values = sorted({str(c["value"]) for c in members})
        if len(members) < 2 or len(values) < 2:
            continue
        kids = "K%04d" % (len(conflicts) + 1)
        members_sorted = sorted(members, key=lambda c: (str(c["value"]),
                                                        str(c["source_id"])))
        all_conditions = sorted({cond for c in members_sorted
                                 for cond in c["conditions"]})
        per_claim_conditions = {c["claim_id"]: c["conditions"]
                                for c in members_sorted}
        shared = set(all_conditions)
        for conds in per_claim_conditions.values():
            shared &= set(conds)
        differing = sorted(set(all_conditions) - shared)
        conflicts.append({
            "conflict_id": kids,
            "entity_id": eid,
            "entity": entities[eid]["canonical_surface"],
            "metric": members_sorted[0]["metric"],
            "claims": [{
                "claim_id": c["claim_id"], "value": c["value"], "unit": c["unit"],
                "conditions": c["conditions"], "source_id": c["source_id"],
                "paragraph_id": c["paragraph_id"], "quote": c["quote"],
            } for c in members_sorted],
            "differing_conditions": differing,
            "shared_conditions": sorted(shared),
            "resolution": "preserved",
            "note": "competing numeric claims kept as separate nodes; not merged",
        })
        ca, cb = members_sorted[0], members_sorted[-1]
        conflict_edges.append({
            "relation": "conflicts-with",
            "subject": ca["claim_id"], "object": cb["claim_id"],
            "source_id": None, "paragraph_id": None,
            "quote": None,
            "qualifiers": {"conflict_id": kids,
                           "differing_conditions": differing},
        })

    # --- assemble graph ---------------------------------------------------------
    n_extracted_edges = len(edges)
    all_edges = list(edges)
    for c in claim_nodes:
        all_edges.append({
            "relation": "concerns", "subject": c["claim_id"],
            "object": c["entity_id"], "source_id": c["source_id"],
            "paragraph_id": c["paragraph_id"], "quote": c["quote"],
            "qualifiers": {"metric": c["metric"], "value": c["value"],
                           "unit": c["unit"]},
        })
    all_edges.extend(conflict_edges)
    all_edges.sort(key=lambda e: (str(e["subject"]), str(e["relation"]),
                                  str(e["object"])))
    for idx, e in enumerate(all_edges, 1):
        e_sorted = {"edge_id": "R%04d" % idx}
        e_sorted.update(e)
        all_edges[idx - 1] = e_sorted

    nodes = []
    for eid in sorted(entities):
        nodes.append(entities[eid])
    nodes.extend(sorted(claim_nodes, key=lambda c: c["claim_id"]))

    graph = {
        "notice": K.NOTICE,
        "node_count": len(nodes),
        "edge_count": len(all_edges),
        "nodes": nodes,
        "edges": all_edges,
        "relation_vocabulary": RELATION_VOCAB,
    }
    K.dump_json(graph, os.path.join(work, "graph.json"))
    K.dump_json({"notice": K.NOTICE, "conflict_count": len(conflicts),
                 "conflicts": conflicts},
                os.path.join(work, "conflict_registry.json"))
    K.dump_json({"notice": K.NOTICE,
                 "accepted_nodes": len(ext.get("nodes", [])),
                 "accepted_edges": n_extracted_edges,
                 "accepted_claims": len(claims),
                 "unreported": ext.get("unreported", []),
                 "notes": ext.get("notes", []),
                 "warnings": sorted(warnings)},
                os.path.join(work, "extraction_report.json"))
    print("build_graph: %d node(s), %d edge(s), %d claim(s), %d conflict(s), %d warning(s)"
          % (len(nodes), len(all_edges), len(claims), len(conflicts), len(warnings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
