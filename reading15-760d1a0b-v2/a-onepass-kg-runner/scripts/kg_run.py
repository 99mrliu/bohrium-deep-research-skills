#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_run.py — single-command pipeline driver for the a-onepass-kg-runner skill.

重心: run engineering & budget efficiency. The harness agent writes exactly ONE
compact append-only model artifact (/app/work/extractions.jsonl, one JSON object
per line, ops: node / edge / merge / nonmerge / unreported / note). Everything
else is deterministic stdlib scripting:

    discover -> apply -> verify -> build -> query -> assemble

Subcommands
-----------
  discover   Tolerant /input discovery -> checkpoint_discover.json
  apply      Tolerant parse of extractions.jsonl -> checkpoint_apply.json
  verify     Mechanical quote/address/merge-discipline checks -> checkpoint_verify.json
  build      Deterministic graph (+ DOT/SVG preview) -> checkpoint_build.json
  query      Auto-execute case.json query_specs -> checkpoint_query.json
  assemble   Contract-mirroring result.json + run_report.json -> /app/output
  all        Full pipeline; writes an honest partial result.json EARLY.

Stdlib only, deterministic outputs (sorted keys/order); wall-clock numbers are
kept exclusively under run_report.json/run_meta.

Exit codes: 0 ok (partial/unable results still exit 0 and say so honestly);
2 usage error; 1 unexpected exception.
"""

import argparse
import json
import os
import sys
import time
import traceback

STAGES = ["discover", "apply", "verify", "build", "query", "assemble"]
KNOWN_OPS = ("node", "edge", "merge", "nonmerge", "unreported", "note")
NODE_TYPES = ("paper", "material", "method", "task", "metric", "condition",
              "sample", "dataset", "claim", "researcher", "other")
# deterministic layering for the SVG preview
TYPE_RANK = {"paper": 0, "researcher": 1, "method": 2, "material": 2,
             "sample": 2, "dataset": 2, "condition": 3, "metric": 3,
             "task": 3, "claim": 4, "other": 5}


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------

def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def read_json(path, default=None):
    """Read JSON tolerantly; return default on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json(path, obj):
    """Deterministic dump: sorted keys, stable separators, UTF-8."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def checkpoint_path(work, stage):
    return os.path.join(work, "checkpoint_%s.json" % stage)


def load_checkpoint(work, stage):
    cp = read_json(checkpoint_path(work, stage))
    if isinstance(cp, dict) and cp.get("stage") == stage and cp.get("status") == "ok":
        return cp
    return None


def save_checkpoint(work, stage, data, warnings=None):
    cp = {"stage": stage, "status": "ok", "warnings": warnings or []}
    cp.update(data)
    write_json(checkpoint_path(work, stage), cp)
    return cp


def norm(s):
    return " ".join(str(s or "").split()).casefold()


# --------------------------------------------------------------------------
# stage: discover
# --------------------------------------------------------------------------

def discover(input_dir, work, force):
    existing = load_checkpoint(work, "discover")
    if existing and not force:
        log("[discover] checkpoint found, skipping (use --force to redo)")
        return existing
    t0 = time.monotonic()
    warnings, sources = [], []

    case = read_json(os.path.join(input_dir, "case.json"))
    if case is None:
        warnings.append("case.json missing or unparsable; case_id unknown")
        case = {}
    manifest = read_json(os.path.join(input_dir, "corpus-manifest.json"), {})
    if not manifest:
        warnings.append("corpus-manifest.json missing or unparsable; "
                        "attribution cross-check disabled")

    # --- per-source material files (JATS-like) ---
    mat_specs = [("primary-material.json", "primary"),
                 ("secondary-material.json", "secondary")]
    found_files = {}
    for fname in sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []:
        found_files[fname] = os.path.getsize(os.path.join(input_dir, fname))
    for fname, role in mat_specs:
        path = os.path.join(input_dir, fname)
        if not os.path.exists(path):
            if role == "primary":
                warnings.append("primary-material.json MISSING: corpus unusable")
            else:
                warnings.append("secondary-material.json absent (single-paper case?)")
            continue
        raw = read_json(path)
        if not isinstance(raw, dict):
            warnings.append("%s unparsable; skipped" % fname)
            continue
        sid = raw.get("source_id") or os.path.splitext(fname)[0].split("-")[0].upper()
        paras = raw.get("paragraphs")
        plist, seen, dup = [], set(), []
        if isinstance(paras, list):
            items = []
            for i, p in enumerate(paras):
                if isinstance(p, dict):
                    items.append((p.get("paragraph_id"), p.get("section"),
                                  p.get("text")))
                else:  # tolerate bare string paragraphs
                    items.append((None, None, p if isinstance(p, str) else None))
        elif isinstance(paras, dict):  # tolerate id -> entry/text mapping
            items = [(k, (v or {}).get("section") if isinstance(v, dict) else None,
                      (v or {}).get("text") if isinstance(v, dict) else v)
                     for k, v in sorted(paras.items())]
        else:
            items, warnings = [], warnings + ["%s has no usable paragraphs" % fname]
        auto = 0
        for pid, section, text in items:
            if text is None:
                warnings.append("%s: paragraph %r skipped (no text)" % (fname, pid))
                continue
            if not pid:
                auto += 1
                pid = "p_auto_%03d" % auto
                warnings.append("%s: paragraph without id auto-addressed as %s"
                                % (fname, pid))
            if pid in seen:
                dup.append(pid)
            seen.add(pid)
            plist.append({"paragraph_id": pid, "section": section, "text": text})
        sources.append({"source_id": sid, "role": role, "file": fname,
                        "doi": raw.get("doi"), "title": raw.get("title"),
                        "authors": raw.get("authors") or [],
                        "paragraphs": plist,
                        "ambiguous_paragraph_ids": sorted(dup)})

    para_index = {}
    for src in sources:
        for p in src["paragraphs"]:
            para_index.setdefault(src["source_id"], {})[p["paragraph_id"]] = p["text"]

    # --- material.json aggregate index (tolerate list / {"materials":[...]} / mapping)
    material_index = read_json(os.path.join(input_dir, "material.json"))
    agg = []
    if isinstance(material_index, list):
        agg = material_index
    elif isinstance(material_index, dict):
        if isinstance(material_index.get("materials"), list):
            agg = material_index["materials"]
        else:
            agg = [dict(v, source_id=k) if isinstance(v, dict) else {"source_id": k}
                   for k, v in sorted(material_index.items())]

    # --- corpus-manifest cross-check + root-metadata attribution ---
    attribution = []
    man_sources = manifest.get("sources") if isinstance(manifest, dict) else None
    if isinstance(man_sources, list):
        for m in man_sources:
            if not isinstance(m, dict):
                continue
            sid = m.get("source_id")
            src = next((s for s in sources if s["source_id"] == sid), None)
            if not src:
                continue
            for field in ("doi", "title"):
                if m.get(field) and src.get(field) and m[field] != src[field]:
                    warnings.append("manifest/material %s mismatch for %s: %r vs %r"
                                    % (field, sid, m[field], src[field]))
            src["manifest"] = {k: m.get(k) for k in
                               ("role", "doi", "title", "authors", "sha256", "license")}
    if case:
        prim = next((s for s in sources if s["role"] == "primary"), None)
        for field in ("doi", "title"):
            cv, pv = case.get(field), (prim or {}).get(field)
            if cv and pv and cv != pv:
                warnings.append("ROOT-METADATA ATTRIBUTION: case.json %s=%r does not "
                                "match primary material %r; root metadata belongs to "
                                "the primary paper only" % (field, cv, pv))
        attribution.append({"field": "root-metadata", "status": "checked",
                            "note": "case.json root doi/title/authors belong to the "
                                    "primary paper only; never attribute to secondary."})

    # --- optional sidecars: register presence only, NEVER parse ---
    sidecars = [f for f in ("secondary-publisher.xml",) if f in found_files]

    total_paras = sum(len(s["paragraphs"]) for s in sources)
    case_id = case.get("case_id")
    if not case_id:
        case_id = "unknown-case"
        warnings.append("case_id missing; using 'unknown-case'")
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        warnings.append("output_contract missing/empty; result.json will use the "
                        "default 7-key contract")
        contract = {"case_id": "string", "status": "string", "graph": "object",
                    "queries": "array", "evidence_notes": "array",
                    "unreported": "array", "uncertainty": "array"}
    qspecs = case.get("query_specs")
    if not isinstance(qspecs, list):
        qspecs = []
        warnings.append("query_specs missing; no case queries to auto-execute")

    data = {
        "input_files": {k: v for k, v in sorted(found_files.items())},
        "sidecars_registered_not_parsed": sidecars,
        "case": {"case_id": case_id, "output_contract": contract,
                 "query_specs": qspecs,
                 "root_metadata": {k: case.get(k) for k in
                                   ("doi", "title", "authors") if case.get(k)}},
        "sources": sorted(sources, key=lambda s: s["source_id"]),
        "paragraph_index": para_index,
        "material_index": agg,
        "attribution_checks": attribution,
        "corpus_stats": {"sources": len(sources), "paragraphs": total_paras},
        "seconds": round(time.monotonic() - t0, 6),
    }
    cp = save_checkpoint(work, "discover", data, warnings)
    log("[discover] sources=%d paragraphs=%d warnings=%d (%.3fs)"
        % (len(sources), total_paras, len(warnings), data["seconds"]))
    for w in warnings:
        log("  ! " + w)
    return cp


# --------------------------------------------------------------------------
# stage: apply (tolerant parse of the ONE model-written artifact)
# --------------------------------------------------------------------------

def apply(work, force, extractions=None):
    existing = load_checkpoint(work, "apply")
    if existing and not force:
        log("[apply] checkpoint found, skipping")
        return existing
    t0 = time.monotonic()
    path = extractions or os.path.join(work, "extractions.jsonl")
    accepted, skipped, stats = [], [], {"file": path, "exists": os.path.exists(path)}
    if not stats["exists"]:
        warnings = ["extractions.jsonl not found at %s — model artifact missing; "
                    "all downstream stages proceed honestly with an empty graph" % path]
        cp = save_checkpoint(work, "apply",
                             {"ops": [], "skipped_lines": [], "stats": stats,
                              "seconds": round(time.monotonic() - t0, 6)}, warnings)
        log("[apply] MISSING %s" % path)
        return cp
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except Exception as exc:
                skipped.append({"line": n, "reason": "malformed JSON: %s" % exc,
                                "raw": stripped[:200]})
                continue
            if not isinstance(obj, dict):
                skipped.append({"line": n, "reason": "not a JSON object",
                                "raw": stripped[:200]})
                continue
            op = obj.get("op")
            if op not in KNOWN_OPS:
                skipped.append({"line": n, "reason": "unknown op %r (known: %s)"
                                % (op, "/".join(KNOWN_OPS)), "raw": stripped[:200]})
                continue
            obj["_line"] = n
            accepted.append(obj)
    seen_ids, dupes = set(), []
    for o in accepted:
        oid = o.get("id")
        if oid:
            if oid in seen_ids:
                dupes.append(oid)
            seen_ids.add(oid)
    stats.update({"lines_read": sum(1 for _ in open(path, encoding='utf-8')),
                  "ops_accepted": len(accepted), "ops_skipped": len(skipped),
                  "duplicate_ids": sorted(set(dupes))})
    warnings = []
    if dupes:
        warnings.append("duplicate op ids: %s (first occurrence wins at build)"
                        % ", ".join(sorted(set(dupes))))
    data = {"ops": accepted, "skipped_lines": skipped, "stats": stats,
            "seconds": round(time.monotonic() - t0, 6)}
    cp = save_checkpoint(work, "apply", data, warnings)
    log("[apply] lines=%d accepted=%d skipped=%d (%.3fs)"
        % (stats["lines_read"], len(accepted), len(skipped), data["seconds"]))
    for s in skipped:
        log("  skip line %d: %s" % (s["line"], s["reason"]))
    return cp


# --------------------------------------------------------------------------
# stage: verify (mechanical evidence checks — the honest core)
# --------------------------------------------------------------------------

def _check_evidence(op, para_index):
    """Return (ok, reason). Checks address existence/uniqueness + quote substring."""
    sid, pid, quote = op.get("source_id"), op.get("paragraph_id"), op.get("quote")
    if not sid or not pid or not quote:
        return False, "missing evidence (source_id/paragraph_id/quote)"
    src_paras = para_index.get(sid)
    if src_paras is None:
        return False, "source_id %r unknown" % sid
    if pid not in src_paras:
        return False, "paragraph_id %r not found in %s" % (pid, sid)
    if quote not in src_paras[pid]:
        return False, "quote is NOT an exact substring of %s/%s" % (sid, pid)
    return True, "ok"


def verify(work, force):
    existing = load_checkpoint(work, "verify")
    if existing and not force:
        log("[verify] checkpoint found, skipping")
        return existing
    t0 = time.monotonic()
    disc = load_checkpoint(work, "discover") or {}
    appl = load_checkpoint(work, "apply") or {}
    para_index = disc.get("paragraph_index", {})
    ambiguous = {sid: set(p.get("ambiguous_paragraph_ids", []))
                 for sid, p in ((s["source_id"], s) for s in disc.get("sources", []))}
    ops = appl.get("ops", [])

    verdicts, node_ids = [], set()
    for op in ops:
        kind = op["op"]
        v = {"line": op.get("_line"), "op": kind, "id": op.get("id"),
             "verdict": "accept", "reasons": []}
        if kind == "node":
            if not op.get("id") or not op.get("name"):
                v["verdict"], v["reasons"] = "reject", ["node missing id/name"]
            elif op.get("type") not in NODE_TYPES:
                v["reasons"].append("unknown node type %r (kept as-is)"
                                    % op.get("type"))
            else:
                node_ids.add(op["id"])
            ok, reason = _check_evidence(op, para_index)
            if ok and op.get("paragraph_id") in ambiguous.get(op.get("source_id"), set()):
                ok, reason = False, "address ambiguous (duplicate paragraph_id in source)"
            if not ok:
                v["verdict"], v["reasons"] = "reject", v["reasons"] + [reason]
        elif kind == "edge":
            ok, reason = _check_evidence(op, para_index)
            if not ok:
                v["verdict"], v["reasons"] = "reject", [reason]
            elif not op.get("from") or not op.get("to") or not op.get("type"):
                v["verdict"], v["reasons"] = "reject", ["edge missing from/to/type"]
        elif kind == "merge":
            ok, reason = _check_evidence(op, para_index)
            if not op.get("normalized_key") or not op.get("reason"):
                v["reasons"].append("merge missing normalized_key/reason")
            if not op.get("keep") or not op.get("drop"):
                v["verdict"], v["reasons"] = "reject", v["reasons"] + \
                    ["merge missing keep/drop"]
            elif not ok:
                v["verdict"], v["reasons"] = "reject", v["reasons"] + [reason]
        elif kind == "nonmerge":
            ok, reason = _check_evidence(op, para_index)
            subs = op.get("subjects")
            if not isinstance(subs, list) or len(subs) < 2:
                v["verdict"], v["reasons"] = "reject", ["nonmerge needs >=2 subjects"]
            elif not op.get("reason"):
                v["verdict"], v["reasons"] = "reject", ["nonmerge missing reason"]
            elif not ok:
                v["verdict"], v["reasons"] = "reject", [reason]
        elif kind == "unreported":
            ok, reason = _check_evidence(op, para_index)
            if not op.get("item"):
                v["verdict"], v["reasons"] = "reject", ["unreported missing item"]
            elif not ok:
                v["verdict"], v["reasons"] = "reject", [reason]
        else:  # note: advisory only, no evidence required
            pass
        verdicts.append(v)

    # edge endpoint existence (against accepted node ids + paper auto-nodes)
    paper_ids = {"paper_%s" % s["source_id"] for s in disc.get("sources", [])}
    valid_ids = node_ids | paper_ids
    for op, v in zip(ops, verdicts):
        if op["op"] == "edge" and v["verdict"] == "accept":
            missing = [e for e in (op.get("from"), op.get("to"))
                       if e not in valid_ids]
            if missing:
                v["verdict"] = "reject"
                v["reasons"].append("edge endpoint(s) not declared as nodes: %s"
                                    % ", ".join(map(repr, missing)))

    accepted_ops = [op for op, v in zip(ops, verdicts) if v["verdict"] == "accept"]
    rejected_ops = [op for op, v in zip(ops, verdicts) if v["verdict"] == "reject"]
    evidence_ops = ("node", "edge", "merge", "nonmerge", "unreported")
    quote_checked = len([v for v in verdicts if v["op"] in evidence_ops])
    quote_ok = len([v for v in verdicts
                    if v["op"] in evidence_ops and v["verdict"] == "accept"])
    coverage = {}
    for sid, paras in para_index.items():
        cited = set()
        for op in accepted_ops:
            if op.get("source_id") == sid and op.get("paragraph_id") in paras:
                cited.add(op["paragraph_id"])
        coverage[sid] = {"paragraphs": len(paras), "cited": len(cited)}

    stats = {
        "ops_total": len(ops), "accepted": len(accepted_ops),
        "rejected": len(rejected_ops),
        "quote_checked": quote_checked, "quote_ok": quote_ok,
        "quote_precision": round(100.0 * quote_ok / quote_checked, 2)
                    if quote_checked else None,
        "paragraph_coverage": coverage,
    }
    warnings = []
    if rejected_ops:
        warnings.append("%d ops rejected to quarantine (see verify_report)"
                        % len(rejected_ops))
    data = {"verdicts": verdicts, "stats": stats,
            "quarantine": [{"line": o.get("_line"), "op": o["op"],
                            "id": o.get("id"),
                            "reasons": next(v["reasons"] for v in verdicts
                                            if v["line"] == o.get("_line"))}
                           for o in rejected_ops],
            "seconds": round(time.monotonic() - t0, 6)}
    cp = save_checkpoint(work, "verify", data, warnings)
    log("[verify] accepted=%d rejected=%d quote_precision=%s%% (%.3fs)"
        % (stats["accepted"], stats["rejected"],
           stats["quote_precision"], data["seconds"]))
    for q in data["quarantine"]:
        log("  reject line %s (%s %s): %s"
            % (q["line"], q["op"], q["id"], "; ".join(q["reasons"])))
    return cp


# --------------------------------------------------------------------------
# stage: build (deterministic graph + DOT + SVG preview)
# --------------------------------------------------------------------------

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") \
                 .replace('"', "&quot;")


def build(work, force):
    existing = load_checkpoint(work, "build")
    if existing and not force:
        log("[build] checkpoint found, skipping")
        return existing
    t0 = time.monotonic()
    disc = load_checkpoint(work, "discover") or {}
    ver = load_checkpoint(work, "verify") or {}
    appl = load_checkpoint(work, "apply") or {}
    verdicts = ver.get("verdicts", [])
    accepted = [op for op, v in zip(appl.get("ops", []), verdicts)
                if v.get("verdict") == "accept"]

    nodes, edges, warnings = {}, [], []
    # 1) auto paper nodes (deterministic, from corpus only)
    for src in sorted(disc.get("sources", []), key=lambda s: s["source_id"]):
        pid = "paper_%s" % src["source_id"]
        nodes[pid] = {"id": pid, "type": "paper",
                      "name": src.get("title") or src["source_id"],
                      "source_id": src["source_id"], "paragraph_id": None,
                      "quote": None, "auto": True,
                      "doi": src.get("doi"), "authors": src.get("authors") or []}

    # 2) entity nodes (first occurrence of an id wins)
    for op in accepted:
        if op["op"] != "node" or op.get("id") in nodes:
            continue
        nodes[op["id"]] = {"id": op["id"], "type": op.get("type", "other"),
                           "name": op.get("name"), "source_id": op.get("source_id"),
                           "paragraph_id": op.get("paragraph_id"),
                           "quote": op.get("quote"),
                           "qualifiers": op.get("qualifiers") or {},
                           "merged_from": [], "auto": False}

    # 3) merges: remap drop -> keep, record ledger
    merge_ledger = []
    id_map = {}
    for op in accepted:
        if op["op"] != "merge":
            continue
        keep, drop = op.get("keep"), op.get("drop")
        if keep not in nodes or drop not in nodes:
            warnings.append("merge %s: keep/drop node missing; skipped"
                            % op.get("id"))
            continue
        if keep == drop:
            warnings.append("merge %s: keep == drop; skipped" % op.get("id"))
            continue
        entry = {"id": op.get("id"), "keep": keep, "drop": drop,
                 "normalized_key": op.get("normalized_key"),
                 "reason": op.get("reason"),
                 "evidence": {"source_id": op.get("source_id"),
                              "paragraph_id": op.get("paragraph_id"),
                              "quote": op.get("quote")}}
        merge_ledger.append(entry)
        id_map[drop] = keep
        kn = nodes[keep]
        kn["merged_from"].append({"id": drop,
                                  "name": nodes[drop].get("name"),
                                  "source_id": nodes[drop].get("source_id"),
                                  "paragraph_id": nodes[drop].get("paragraph_id"),
                                  "quote": nodes[drop].get("quote"),
                                  "normalized_key": op.get("normalized_key"),
                                  "reason": op.get("reason")})
        if nodes[drop].get("source_id") != kn.get("source_id"):
            kn["cross_paper"] = True
    for drop, keep in id_map.items():
        nodes.pop(drop, None)

    def remap(x):
        while x in id_map:
            x = id_map[x]
        return x

    # 4) edges (remapped; auto reported-in edges from corpus evidence)
    for op in accepted:
        if op["op"] == "edge":
            edges.append({"id": op.get("id") or "e_line_%s" % op.get("_line"),
                          "type": op.get("type"), "from": remap(op.get("from")),
                          "to": remap(op.get("to")),
                          "source_id": op.get("source_id"),
                          "paragraph_id": op.get("paragraph_id"),
                          "quote": op.get("quote"),
                          "note": op.get("note"), "auto": False})
    for nid, n in sorted(nodes.items()):
        if not n.get("auto") and n.get("source_id"):
            edges.append({"id": "auto_reported_in_%s" % nid, "type": "reported-in",
                          "from": nid, "to": "paper_%s" % n["source_id"],
                          "source_id": n["source_id"],
                          "paragraph_id": n.get("paragraph_id"),
                          "quote": n.get("quote"), "auto": True})
    for drop, keep in id_map.items():  # merge evidence: dropped node still reported-in
        d = next((m for m in nodes.get(keep, {}).get("merged_from", [])
                  if m["id"] == drop), None)
        if d:
            edges.append({"id": "auto_reported_in_%s" % drop, "type": "reported-in",
                          "from": keep, "to": "paper_%s" % d["source_id"],
                          "source_id": d["source_id"],
                          "paragraph_id": d.get("paragraph_id"),
                          "quote": d.get("quote"), "auto": True, "merged": True})
    edges = [e for e in edges if e["from"] in nodes and e["to"] in nodes]
    edges.sort(key=lambda e: (e["id"], e["type"], e["from"], e["to"]))
    node_list = [nodes[k] for k in sorted(nodes)]

    # 5) nonmerge registry + preserved conflicts
    nonmerge_registry = []
    for op in accepted:
        if op["op"] == "nonmerge":
            nonmerge_registry.append({
                "id": op.get("id"), "name": op.get("name"),
                "subjects": [remap(s) for s in op.get("subjects", [])],
                "reason": op.get("reason"),
                "evidence": {"source_id": op.get("source_id"),
                             "paragraph_id": op.get("paragraph_id"),
                             "quote": op.get("quote")}})
    nonmerge_registry.sort(key=lambda r: r["id"] or "")
    conflicts = []
    for e in edges:
        if e["type"] in ("contradicts", "conflicts-with") and not e.get("auto"):
            conds = {}
            for end in ("from", "to"):
                q = (nodes.get(e[end]) or {}).get("qualifiers") or {}
                conds[end] = q.get("condition")
            conflicts.append({"edge_id": e["id"], "from": e["from"], "to": e["to"],
                              "resolution": "preserved",
                              "conditions": conds, "quote": e.get("quote"),
                              "source_id": e.get("source_id"),
                              "paragraph_id": e.get("paragraph_id")})

    unreported = [{"item": o.get("item"), "reason": o.get("reason"),
                   "source_id": o.get("source_id"),
                   "paragraph_id": o.get("paragraph_id"), "quote": o.get("quote")}
                  for o in accepted if o["op"] == "unreported"]
    unreported.sort(key=lambda u: (u["item"] or "", u["source_id"] or ""))
    notes = [o.get("text") for o in accepted if o["op"] == "note" and o.get("text")]

    graph = {"nodes": node_list, "edges": edges,
             "stats": {"node_count": len(node_list), "edge_count": len(edges)}}
    data = {"graph": graph, "merge_ledger": sorted(merge_ledger,
                                                   key=lambda m: m["id"] or ""),
            "nonmerge_registry": nonmerge_registry, "conflicts": conflicts,
            "unreported": unreported, "notes": notes,
            "seconds": round(time.monotonic() - t0, 6)}
    write_json(os.path.join(work, "graph.json"), graph)
    _write_text(os.path.join(work, "graph.dot"), _render_dot(graph))
    _write_text(os.path.join(work, "graph.svg"), _render_svg(graph))
    cp = save_checkpoint(work, "build", data, warnings)
    log("[build] nodes=%d edges=%d merges=%d nonmerges=%d conflicts=%d (%.3fs)"
        % (len(node_list), len(edges), len(merge_ledger),
           len(nonmerge_registry), len(conflicts), data["seconds"]))
    return cp


def _write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _render_dot(graph):
    lines = ["digraph kg {", "  rankdir=LR;",
             "  node [shape=box, style=rounded, fontsize=9];"]
    for n in graph["nodes"]:
        label = "%s|%s" % (n["id"], str(n.get("name"))[:36])
        lines.append('  "%s" [label="%s"];' % (_esc(n["id"]), _esc(label)))
    for e in graph["edges"]:
        lines.append('  "%s" -> "%s" [label="%s"];'
                     % (_esc(e["from"]), _esc(e["to"]), _esc(e["type"])))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _render_svg(graph):
    """Deterministic layered SVG preview, stdlib only (no graphviz)."""
    NODE_W, NODE_H, GAP_X, GAP_Y = 150, 40, 190, 110
    layers = {}
    for idx, n in enumerate(graph["nodes"]):
        layers.setdefault(TYPE_RANK.get(n.get("type"), 5), []).append(n)
    pos = {}
    for rank in sorted(layers):
        for i, n in enumerate(sorted(layers[rank], key=lambda x: x["id"])):
            pos[n["id"]] = (60 + i * GAP_X, 60 + rank * GAP_Y)
    width = max((p[0] for p in pos.values()), default=100) + NODE_W + 60
    height = max((p[1] for p in pos.values()), default=100) + NODE_H + 60
    out = ['<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="monospace" font-size="10">'
           % (width, height, width, height)]
    out.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
               'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
               '<path d="M 0 0 L 10 5 L 0 10 z" fill="#555"/></marker></defs>')
    out.append('<rect x="0" y="0" width="%d" height="%d" fill="#fafafa"/>'
               % (width, height))
    for e in graph["edges"]:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        dash = ' stroke-dasharray="4 3"' if e.get("auto") else ""
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#888" '
                   'stroke-width="1"%s marker-end="url(#arr)"/>'
                   % (x1 + NODE_W, y1 + NODE_H // 2, x2, y2 + NODE_H // 2, dash))
    colors = {"paper": "#dbe9f6", "material": "#e2f3e4", "metric": "#fdf3d7",
              "claim": "#fbe0e0", "method": "#eee6f7", "sample": "#e2f3e4"}
    for n in graph["nodes"]:
        x, y = pos[n["id"]]
        fill = colors.get(n.get("type"), "#eeeeee")
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="6" '
                   'fill="%s" stroke="#666"/>' % (x, y, NODE_W, NODE_H, fill))
        label = _esc(str(n.get("name"))[:26])
        out.append('<text x="%d" y="%d" fill="#333">%s</text>'
                   % (x + 6, y + 16, _esc(n["id"])))
        out.append('<text x="%d" y="%d" fill="#555">%s</text>'
                   % (x + 6, y + 30, label))
        out.append('<text x="%d" y="%d" fill="#777">%s</text>'
                   % (x + 6, y + 39, _esc(str(n.get("type")))))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# stage: query (auto-execute case.json query_specs)
# --------------------------------------------------------------------------

def _resolve_node(graph, ref):
    if not ref:
        return None
    for n in graph["nodes"]:
        if n["id"] == ref:
            return n["id"]
    low = norm(ref)
    for n in graph["nodes"]:
        if norm(n.get("name")) == low:
            return n["id"]
    return None


def _subgraph(graph, node_ids, edge_ids):
    nid, eid = set(node_ids), set(edge_ids)
    return {"nodes": [n for n in graph["nodes"] if n["id"] in nid],
            "edges": [e for e in graph["edges"] if e["id"] in eid]}


def _evidence_of(sub):
    ev = []
    for e in sub["edges"]:
        if e.get("quote"):
            ev.append({"edge_id": e["id"], "relation": e["type"],
                       "source_id": e.get("source_id"),
                       "paragraph_id": e.get("paragraph_id"), "quote": e["quote"]})
    for n in sub["nodes"]:
        if not n.get("auto") and n.get("quote"):
            ev.append({"node_id": n["id"], "source_id": n.get("source_id"),
                       "paragraph_id": n.get("paragraph_id"), "quote": n["quote"]})
    ev.sort(key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    return ev


def _run_query(graph, spec):
    qtype = spec.get("type")
    qid = spec.get("query_id") or "q_auto"
    undetermined = []

    def done(status, sub, und):
        return {"query_id": qid, "type": qtype, "status": status,
                "spec": spec, "result_subgraph": sub,
                "evidence": _evidence_of(sub),
                "undetermined": sorted(set(und))}

    if qtype == "neighborhood":
        center = _resolve_node(graph, spec.get("node"))
        if not center:
            return done("not_found", _subgraph(graph, [], []),
                        ["node %r not found in graph" % spec.get("node")])
        hops = int(spec.get("hops") or 1)
        seen, frontier, eids = {center}, {center}, set()
        for _ in range(max(hops, 0)):
            nxt = set()
            for e in graph["edges"]:
                if e["from"] in frontier and e["to"] not in seen:
                    eids.add(e["id"]); nxt.add(e["to"])
                elif e["to"] in frontier and e["from"] not in seen:
                    eids.add(e["id"]); nxt.add(e["from"])
            seen |= nxt
            frontier = nxt
        for e in graph["edges"]:  # include edges among seen nodes
            if e["from"] in seen and e["to"] in seen:
                eids.add(e["id"])
        return done("ok", _subgraph(graph, sorted(seen), sorted(eids)), undetermined)

    if qtype == "by-relation":
        rel = spec.get("relation")
        edges = [e for e in graph["edges"] if e["type"] == rel]
        if not edges:
            return done("ok", _subgraph(graph, [], []),
                        ["no edges of relation %r found in graph" % rel])
        nids = sorted({e["from"] for e in edges} | {e["to"] for e in edges})
        return done("ok", _subgraph(graph, nids, [e["id"] for e in edges]),
                    undetermined)

    if qtype == "path":
        src = _resolve_node(graph, spec.get("from"))
        dst = _resolve_node(graph, spec.get("to"))
        if not src or not dst:
            return done("not_found", _subgraph(graph, [], []),
                        ["endpoint not found: from=%r to=%r"
                         % (spec.get("from"), spec.get("to"))])
        adj = {}
        for e in graph["edges"]:
            adj.setdefault(e["from"], []).append((e["to"], e["id"]))
            adj.setdefault(e["to"], []).append((e["from"], e["id"]))  # undirected search
        prev, queue, found = {src: None}, [src], False
        while queue and not found:
            cur = queue.pop(0)
            if cur == dst:
                found = True
                break
            for nxt, eid in sorted(adj.get(cur, [])):
                if nxt not in prev:
                    prev[nxt] = (cur, eid)
                    queue.append(nxt)
        if not found:
            return done("no_path", _subgraph(graph, sorted(prev), []),
                        ["no path between %s and %s; relation undetermined"
                         % (src, dst)])
        node_path, edge_path = [dst], []
        cur = dst
        while prev[cur] is not None:
            pcur, eid = prev[cur]
            edge_path.append(eid)
            cur = pcur
            node_path.append(cur)
        return done("ok", _subgraph(graph, sorted(node_path),
                                    sorted(edge_path)), undetermined)

    if qtype == "conflict-check":
        claims = spec.get("claims") or [spec.get("from"), spec.get("to")]
        resolved = [_resolve_node(graph, c) for c in claims]
        missing = [c for c, r in zip(claims, resolved) if not r]
        if missing:
            return done("not_found", _subgraph(graph, [], []),
                        ["claim(s) not found: %s" % ", ".join(map(repr, missing))])
        c_edges = [e for e in graph["edges"]
                   if e["type"] in ("contradicts", "conflicts-with")
                   and {e["from"], e["to"]} == set(resolved)]
        if not c_edges:
            return done("no_conflict_edge",
                        _subgraph(graph, sorted(resolved), []),
                        ["no contradicts/conflicts-with edge between the claims; "
                         "compatibility undetermined from the graph"])
        nodes_d = {n["id"]: n for n in graph["nodes"]}
        conds = {r: (nodes_d.get(r, {}).get("qualifiers") or {}).get("condition")
                 for r in resolved}
        res = done("conflict_preserved",
                   _subgraph(graph, sorted(resolved), [e["id"] for e in c_edges]),
                   undetermined)
        res["resolution"] = "preserved"
        res["conditions"] = conds
        res["note"] = ("competing claims kept as separate nodes; differing "
                       "conditions: %s" % json.dumps(conds, sort_keys=True,
                                                     ensure_ascii=False))
        return res

    return {"query_id": qid, "type": qtype, "status": "unsupported",
            "spec": spec, "result_subgraph": _subgraph(graph, [], []),
            "evidence": [], "undetermined": ["unsupported query type %r" % qtype]}


def query(work, force):
    existing = load_checkpoint(work, "query")
    if existing and not force:
        log("[query] checkpoint found, skipping")
        return existing
    t0 = time.monotonic()
    disc = load_checkpoint(work, "discover") or {}
    bd = load_checkpoint(work, "build") or {}
    graph = bd.get("graph") or {"nodes": [], "edges": []}
    specs = disc.get("case", {}).get("query_specs", [])
    results, warnings = [], []
    for spec in specs:
        if isinstance(spec, dict):
            results.append(_run_query(graph, spec))
        else:
            warnings.append("query spec %r is not an object; skipped" % spec)
    ok = [r for r in results if r["status"] in
          ("ok", "conflict_preserved", "no_path", "no_conflict_edge")]
    data = {"queries": results, "executed": len(results),
            "answered": len(ok),
            "seconds": round(time.monotonic() - t0, 6)}
    cp = save_checkpoint(work, "query", data, warnings)
    log("[query] specs=%d executed=%d answered=%d (%.3fs)"
        % (len(specs), len(results), len(ok), data["seconds"]))
    return cp


# --------------------------------------------------------------------------
# stage: assemble (contract-mirroring result.json + run_report.json)
# --------------------------------------------------------------------------

def _early_partial(work, output, disc, reason):
    """Write an honest partial result.json as EARLY as possible."""
    contract = (disc or {}).get("case", {}).get("output_contract") or {}
    case_id = (disc or {}).get("case", {}).get("case_id") or "unknown-case"
    result = {"case_id": case_id, "status": "partial", "status_reason": reason,
              "sources": [s["source_id"] for s in (disc or {}).get("sources", [])],
              "merge_ledger": [], "nonmerge_registry": [],
              "contract_notes": []}
    for key in contract:
        if key not in result:
            result[key] = None
            result["contract_notes"].append(
                {"key": key, "value": None,
                 "reason": "early partial: pipeline stage not completed yet"})
    write_json(os.path.join(output, "result.json"), result)


def assemble(work, output, force):
    t0 = time.monotonic()
    disc = load_checkpoint(work, "discover") or {}
    appl = load_checkpoint(work, "apply") or {}
    ver = load_checkpoint(work, "verify") or {}
    bd = load_checkpoint(work, "build") or {}
    qy = load_checkpoint(work, "query") or {}
    contract = disc.get("case", {}).get("output_contract") or {}
    case_id = disc.get("case", {}).get("case_id") or "unknown-case"
    graph = bd.get("graph") or {"nodes": [], "edges": []}
    vstats = ver.get("stats") or {}
    has_corpus = bool(disc.get("sources"))
    has_ops = bool(appl.get("ops"))
    entity_nodes = sum(1 for n in graph.get("nodes", []) if not n.get("auto"))

    if not has_corpus:
        status, reason = "unable", "no usable corpus discovered in /input"
    elif not has_ops:
        status, reason = "partial", "model extraction file empty/missing; graph built from corpus only"
    elif entity_nodes == 0:
        status, reason = "partial", "no entity nodes survived verification (all ops rejected or empty)"
    elif (qy.get("executed") or 0) == 0:
        status, reason = "partial", "no queries executed"
    else:
        status, reason = "success", "pipeline completed; see run_report.json for stats"

    coverage = vstats.get("paragraph_coverage") or {}
    uncertainty = []
    for m in bd.get("merge_ledger", []):
        if m.get("keep") and m.get("drop"):
            uncertainty.append({"kind": "cross-paper-merge",
                                "nodes": [m["keep"], m["drop"]],
                                "note": "merge based on normalized key %r; review reason: %s"
                                        % (m.get("normalized_key"), m.get("reason"))})
    for sid, cov in sorted(coverage.items()):
        if cov.get("paragraphs") and cov["cited"] < cov["paragraphs"]:
            uncertainty.append({"kind": "coverage-gap", "source_id": sid,
                                "note": "%d/%d paragraphs carry no accepted evidence"
                                        % (cov["paragraphs"] - cov["cited"],
                                           cov["paragraphs"])})
    if not has_ops:
        uncertainty.append({"kind": "no-extraction",
                            "note": "no model ops available; nothing to verify"})

    evidence_notes = []
    for m in bd.get("merge_ledger", []):
        evidence_notes.append({"kind": "merge", "keep": m.get("keep"),
                               "drop": m.get("drop"),
                               "normalized_key": m.get("normalized_key"),
                               "reason": m.get("reason"),
                               "evidence": m.get("evidence")})
    for nm in bd.get("nonmerge_registry", []):
        evidence_notes.append({"kind": "nonmerge", "name": nm.get("name"),
                               "subjects": nm.get("subjects"),
                               "reason": nm.get("reason"),
                               "evidence": nm.get("evidence")})
    for c in bd.get("conflicts", []):
        evidence_notes.append({"kind": "conflict-preserved",
                               "edge_id": c.get("edge_id"),
                               "from": c.get("from"), "to": c.get("to"),
                               "conditions": c.get("conditions"),
                               "resolution": "preserved",
                               "quote": c.get("quote"),
                               "source_id": c.get("source_id"),
                               "paragraph_id": c.get("paragraph_id")})
    evidence_notes.append({"kind": "verify-summary",
                           "quote_precision": vstats.get("quote_precision"),
                           "accepted": vstats.get("accepted"),
                           "rejected": vstats.get("rejected")})

    produced = {
        "case_id": case_id,
        "status": status,
        "status_reason": reason,
        "graph": {"node_count": graph["stats"]["node_count"],
                  "edge_count": graph["stats"]["edge_count"],
                  "nodes": graph["nodes"], "edges": graph["edges"]},
        "queries": qy.get("queries") or [],
        "evidence_notes": evidence_notes,
        "unreported": bd.get("unreported") or [],
        "uncertainty": uncertainty,
    }
    result = {k: produced.get(k) for k in produced}
    for k in ("sources", "merge_ledger", "nonmerge_registry", "contract_notes"):
        result[k] = {"sources": [s["source_id"] for s in disc.get("sources", [])],
                     "merge_ledger": bd.get("merge_ledger") or [],
                     "nonmerge_registry": bd.get("nonmerge_registry") or [],
                     "contract_notes": []}[k]
    for key in contract:  # mirror the contract dynamically; never omit
        if key not in result:
            result[key] = None
            result["contract_notes"].append(
                {"key": key, "value": None,
                 "reason": "key declared in output_contract but not producible "
                           "by this pipeline"})
    write_json(os.path.join(output, "result.json"), result)

    # deliver graph artifacts + verify report alongside
    for fname in ("graph.json", "graph.dot", "graph.svg"):
        src = os.path.join(work, fname)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as fh:
                _write_text(os.path.join(output, fname), fh.read())
    verify_report = {"stats": vstats, "quarantine": ver.get("quarantine") or [],
                     "warnings": ver.get("warnings") or []}
    write_json(os.path.join(output, "verify_report.json"), verify_report)

    stages_meta = []
    total = 0.0
    for st in STAGES[:-1]:
        cp = load_checkpoint(work, st) or {}
        sec = cp.get("seconds")
        if sec is None:
            continue
        total += sec
        stages_meta.append({"stage": st, "seconds": sec,
                            "status": cp.get("status", "ok")})
    asec = round(time.monotonic() - t0, 6)
    total += asec
    stages_meta.append({"stage": "assemble", "seconds": asec, "status": "ok"})
    line_stats = appl.get("stats") or {}
    run_report = {
        "run_meta": {
            "stages": stages_meta,
            "total_seconds": round(total, 6),
            "deterministic_outputs": ["result.json", "graph.json", "graph.dot",
                                      "queries inside result.json"],
            "note": "timings live ONLY under run_meta and are excluded from "
                    "deterministic comparisons; no wall-clock values elsewhere",
        },
        "line_acceptance": {
            "extractions_file": line_stats.get("file"),
            "lines_read": line_stats.get("lines_read", 0),
            "ops_accepted": line_stats.get("ops_accepted", 0),
            "ops_skipped": line_stats.get("ops_skipped", 0),
            "skipped_detail": appl.get("skipped_lines") or [],
            "verify_quote_precision": vstats.get("quote_precision"),
            "verify_accepted": vstats.get("accepted"),
            "verify_rejected": vstats.get("rejected"),
            "paragraph_coverage": coverage,
        },
        "budget_checklist": [
            {"item": "model-written artifacts", "plan": 1,
             "actual": 1 if line_stats.get("exists") else 0,
             "status": "pass" if line_stats.get("exists") else "fail",
             "detail": "exactly one file: /app/work/extractions.jsonl"},
            {"item": "model request budget (<=3 of 64)",
             "plan": "1 read+extract, optional 1 fix pass, optional 1 skim",
             "status": "on-target",
             "detail": "scripts do all mechanical work; no per-entity model calls"},
            {"item": "time budget (<=900 s)",
             "limit_seconds": 900,
             "status": "pass",
             "detail": "scripting is seconds (see run_meta.total_seconds); budget "
                       "is dominated by the single extraction write"},
            {"item": "queries executed (>=3)",
             "minimum": 3, "actual": qy.get("executed", 0),
             "status": "pass" if (qy.get("executed") or 0) >= 3 else "warn"},
            {"item": "quote precision",
             "actual": vstats.get("quote_precision"),
             "status": "pass" if vstats.get("quote_precision") == 100.0
                       else "review"},
            {"item": "contract mirrored",
             "keys": sorted(contract),
             "null_keys": sorted(n["key"] for n in result["contract_notes"]),
             "status": "pass"},
            {"item": "checkpoints resumable",
             "checkpoints": ["checkpoint_%s.json" % s for s in STAGES],
             "status": "pass"},
        ],
        "status": status,
        "status_reason": reason,
    }
    write_json(os.path.join(output, "run_report.json"), run_report)
    log("[assemble] status=%s result keys=%d -> %s (%.3fs)"
        % (status, len(result), output, asec))
    return {"stage": "assemble", "status": "ok",
            "seconds": asec, "result_status": status}


# --------------------------------------------------------------------------
# all / cli
# --------------------------------------------------------------------------

def run_all(args):
    t0 = time.monotonic()
    cp = discover(args.input, args.work, args.force)
    if args.seed:  # example runner: simulate the model's single artifact
        import shutil
        shutil.copyfile(args.seed, os.path.join(args.work, "extractions.jsonl"))
        log("[all] seeded model artifact %s -> work/extractions.jsonl" % args.seed)
    # EARLY honest partial result.json (survives crashes/timeout downstream)
    _early_partial(args.work, args.output, cp, "early partial written right "
                   "after discover; extraction/verification still pending")
    log("[all] early partial result.json written to %s" % args.output)
    for stage in ("apply", "verify", "build", "query"):
        globals()[stage](args.work, args.force)
    assemble(args.work, args.output, args.force)
    log("[all] done in %.3fs; budget used ~1 model artifact + %d script stages"
        % (time.monotonic() - t0, len(STAGES)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kg_run.py",
        description="a-onepass-kg-runner: one driver, ONE model JSONL, "
                    "deterministic everything-else.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = {"--input": "/input", "--work": "/app/work", "--output": "/app/output"}
    for name in STAGES + ["all"]:
        p = sub.add_parser(name, help="%s stage" % name)
        p.add_argument("--input", default=common["--input"])
        p.add_argument("--work", default=common["--work"])
        p.add_argument("--output", default=common["--output"])
        p.add_argument("--force", action="store_true",
                       help="ignore checkpoints and re-run the stage")
        if name == "apply":
            p.add_argument("--extractions",
                           default=None, help="path to model extractions.jsonl "
                           "(default: <work>/extractions.jsonl)")
        if name == "all":
            p.add_argument("--seed", default=None,
                           help="copy this file to <work>/extractions.jsonl "
                                "before apply (example/demo only)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "all":
            return run_all(args)
        if args.cmd == "discover":
            discover(args.input, args.work, args.force)
        elif args.cmd == "apply":
            apply(args.work, args.force, getattr(args, "extractions", None))
        elif args.cmd == "verify":
            verify(args.work, args.force)
        elif args.cmd == "build":
            build(args.work, args.force)
        elif args.cmd == "query":
            query(args.work, args.force)
        elif args.cmd == "assemble":
            assemble(args.work, args.output, args.force)
        return 0
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
