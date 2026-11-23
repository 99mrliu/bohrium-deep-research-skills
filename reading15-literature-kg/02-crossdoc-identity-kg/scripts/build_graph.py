# -*- coding: utf-8 -*-
"""图谱构建：在身份裁决完成后分配稳定节点 ID，输出带证据的图（仅标准库）。

流程：证据核验 → 簇节点化（稳定 ID E-XXXX 在裁决之后分配）→ 边构建
（引用被剔除提及的边一并剔除并记录）→ 跨篇测量冲突记录。
输出 graph 字典及 DOT / SVG / 文本预览。
"""
import math

from normalize import normalize_surface
from quote_verify import check_evidence_dict, check_quote, verify_mentions


def build_graph(mentions, relations, decisions, clusters, store):
    """返回 (graph, verification_report, conflicts)。

    graph: {"meta":..., "nodes":[...], "edges":[...]}；
    核验失败的提及及其关联边被剔除，原因记入 verification_report。
    """
    valid_mentions, report = verify_mentions(store, mentions)

    # ---- 节点：每个有效簇一个节点；稳定 ID 仅在裁决之后分配 ----
    dec_by_id = {d["decision_id"]: d for d in decisions}
    nodes, mention_to_node = [], {}
    ordered = []
    for cl in clusters:
        members = [m for m in cl["members"] if m in valid_mentions]
        if members:
            ordered.append((min(members), members, cl))
    ordered.sort(key=lambda t: t[0])
    for idx, (_, members, cl) in enumerate(ordered, start=1):
        node_id = "E-%04d" % idx
        ms = [valid_mentions[m] for m in members]
        surfaces = sorted({m.get("surface", "") for m in ms})
        name = min(surfaces, key=lambda s: (len(s), s)) if surfaces else node_id
        aliases = sorted({a for m in ms for a in (m.get("aliases") or [])}
                         | set(surfaces)) 
        aliases = [a for a in aliases if a != name]
        etypes = sorted({m.get("entity_type", "unknown") for m in ms})
        sources = [{
            "mention_id": m["mention_id"],
            "source_id": m.get("source_id"),
            "paragraph_id": m.get("paragraph_id"),
            "quote": m.get("quote"),
        } for m in ms]
        for m in members:
            mention_to_node[m] = node_id
        nodes.append({
            "id": node_id,
            "kind": "entity",
            "entity_type": etypes[0] if len(etypes) == 1 else etypes,
            "name": name,
            "aliases": aliases,
            "merged_from": members if len(members) > 1 else [],
            "decision_refs": [r for r in cl.get("decision_refs", [])
                              if r in dec_by_id],
            "identity_status": "MERGED" if len(members) > 1 else "SINGLETON",
            "sources": sources,
        })

    # ---- 边：证据核验；object_literal 生成来源作用域辅助节点 ----
    edges = []
    aux_nodes = {}
    rejected_edges = []
    aux_count = 0
    for k, rel in enumerate(relations, start=1):
        rid = rel.get("edge_id") or "G-%04d" % k
        sub, obj = rel.get("subject"), rel.get("object")
        if sub not in mention_to_node:
            rejected_edges.append({"edge_id": rid,
                                   "reason": "subject_rejected_or_unknown"})
            continue
        if obj is not None and obj not in mention_to_node:
            rejected_edges.append({"edge_id": rid,
                                   "reason": "object_rejected_or_unknown"})
            continue
        ev = rel.get("evidence") or {}
        ok, reason = check_evidence_dict(store, ev)
        if not ok:
            rejected_edges.append({"edge_id": rid, "reason": reason})
            continue
        if obj is not None:
            target = mention_to_node[obj]
        else:
            lit = rel.get("object_literal") or {}
            label = lit.get("label") or "literal"
            scope = ev.get("source_id") or "unknown"
            aux_key = (scope, normalize_surface(label))
            if aux_key not in aux_nodes:
                aux_count += 1
                aid = "AUX-%04d" % aux_count
                aux_nodes[aux_key] = {
                    "id": aid, "kind": "aux",
                    "entity_type": lit.get("node_kind", "literal"),
                    "name": label, "aliases": [], "merged_from": [],
                    "decision_refs": [],
                    "identity_status": "SOURCE_SCOPED",
                    "sources": [{
                        "mention_id": None, "source_id": scope,
                        "paragraph_id": ev.get("paragraph_id"),
                        "quote": ev.get("quote"),
                    }],
                }
            target = aux_nodes[aux_key]["id"]
        edges.append({
            "id": rid,
            "subject": mention_to_node[sub],
            "predicate": rel.get("predicate", "related_to"),
            "object": target,
            "attributes": rel.get("attributes") or {},
            "evidence": [{
                "source_id": ev.get("source_id"),
                "paragraph_id": ev.get("paragraph_id"),
                "quote": ev.get("quote"),
            }],
        })
    report["rejected_edges"] = rejected_edges
    report["edges_verified"] = len(edges)

    nodes.extend(sorted(aux_nodes.values(), key=lambda n: n["id"]))
    graph = {
        "meta": {
            "format": "crossdoc-identity-kg/graph@1",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "id_policy": "稳定节点 ID 在身份裁决完成后按簇最小 mention_id 顺序分配",
        },
        "nodes": nodes,
        "edges": edges,
    }
    conflicts = measurement_conflicts(graph)
    return graph, report, conflicts


def measurement_conflicts(graph):
    """合并节点上来自不同论文的同名测量值若不同，记录冲突并保持各自来源
    （绝不把不同论文的数值合成一个结论）。"""
    by_id = {n["id"]: n for n in graph["nodes"]}
    conflicts = []
    for node in graph["nodes"]:
        if node.get("identity_status") != "MERGED":
            continue
        srcs = {s.get("source_id") for s in node.get("sources", [])}
        if len(srcs) < 2:
            continue
        per_metric = {}
        for e in graph["edges"]:
            if e["subject"] != node["id"] or e["predicate"] != "has_measurement":
                continue
            metric = normalize_surface(
                by_id.get(e["object"], {}).get("name", ""))
            ev = e["evidence"][0] if e["evidence"] else {}
            per_metric.setdefault(metric, []).append({
                "source_id": ev.get("source_id"),
                "value": (e.get("attributes") or {}).get("value"),
                "unit": (e.get("attributes") or {}).get("unit"),
                "conditions": (e.get("attributes") or {}).get("conditions"),
                "edge_id": e["id"],
            })
        for metric in sorted(per_metric):
            vals = per_metric[metric]
            uniq = {str(v["value"]) + "|" + str(v["unit"]) for v in vals}
            if len(vals) > 1 and len(uniq) > 1:
                conflicts.append({
                    "kind": "measurement_conflict_kept_separate",
                    "node_id": node["id"],
                    "node_name": node.get("name"),
                    "metric": metric,
                    "values": vals,
                    "policy": "各来源数值分别保留并附条件，不合并为单一结论",
                })
    return conflicts


def to_jsonl(graph):
    lines = []
    for n in graph["nodes"]:
        rec = {"type": "node"}
        rec.update(n)
        lines.append(_json_line(rec))
    for e in graph["edges"]:
        rec = {"type": "edge"}
        rec.update(e)
        lines.append(_json_line(rec))
    return "\n".join(lines) + "\n"


def _json_line(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


def to_dot(graph, label="crossdoc-identity-kg"):
    out = ["digraph G {", "  rankdir=LR;",
           '  labelloc="t"; label="%s";' % _esc(label),
           '  node [fontname="Helvetica"];']
    for n in graph["nodes"]:
        shape = "box" if n["kind"] == "aux" else "ellipse"
        color = {"MERGED": "green4", "SINGLETON": "gray40",
                 "SOURCE_SCOPED": "gray70"}.get(n["identity_status"], "black")
        out.append('  "%s" [label="%s\\n(%s)", shape=%s, color=%s];'
                   % (n["id"], _esc(n["name"]),
                      _esc(str(n["entity_type"])), shape, color))
    for e in graph["edges"]:
        out.append('  "%s" -> "%s" [label="%s"];'
                   % (e["subject"], e["object"], _esc(e["predicate"])))
    out.append("}")
    return "\n".join(out) + "\n"


def to_svg(graph, title="crossdoc-identity-kg preview"):
    """无依赖圆形布局 SVG 预览（文本文件）。"""
    nodes, edges = graph["nodes"], graph["edges"]
    n = max(1, len(nodes))
    size = max(720, 90 * n)
    cx = cy = size / 2.0
    radius = size / 2.0 - 120.0
    pos = {}
    for i, node in enumerate(nodes):
        ang = 2.0 * math.pi * i / n
        pos[node["id"]] = (cx + radius * math.cos(ang),
                           cy + radius * math.sin(ang))
    colors = {"MERGED": "#1a7f37", "SINGLETON": "#57606a",
              "SOURCE_SCOPED": "#9a6700"}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">'
             % (size, size),
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="20" y="30" font-size="18" font-family="sans-serif">%s</text>'
             % _esc(title)]
    for e in edges:
        x1, y1 = pos[e["subject"]]
        x2, y2 = pos[e["object"]]
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="#8c959f" stroke-width="1.5"/>' % (x1, y1, x2, y2))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="#6e7781" '
                     'font-family="sans-serif">%s</text>'
                     % ((x1 + x2) / 2, (y1 + y2) / 2, _esc(e["predicate"])))
    for node in nodes:
        x, y = pos[node["id"]]
        color = colors.get(node["identity_status"], "#333")
        parts.append('<circle cx="%.1f" cy="%.1f" r="26" fill="#ddf4e4" '
                     'stroke="%s" stroke-width="2"/>' % (x, y, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="11" text-anchor="middle" '
                     'font-family="sans-serif">%s</text>' % (x, y + 4, _esc(node["name"])))
        parts.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle" '
                     'fill="%s" font-family="sans-serif">%s %s</text>'
                     % (x, y + 40, color, node["id"], node["identity_status"]))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def to_text_preview(graph):
    lines = ["图谱文本预览（节点 %d，边 %d）"
             % (len(graph["nodes"]), len(graph["edges"])), ""]
    for n in graph["nodes"]:
        srcs = ",".join(sorted({str(s.get("source_id"))
                                for s in n.get("sources", [])}))
        lines.append("[%s] %s (%s) <%s> sources=%s merged_from=%s"
                     % (n["id"], n["name"], n["entity_type"],
                        n["identity_status"], srcs,
                        ",".join(n.get("merged_from", [])) or "-"))
    lines.append("")
    for e in graph["edges"]:
        ev = e["evidence"][0] if e["evidence"] else {}
        lines.append("%s --%s--> %s  @%s#%s \"%s\""
                     % (e["subject"], e["predicate"], e["object"],
                        ev.get("source_id"), ev.get("paragraph_id"),
                        (ev.get("quote") or "")[:60]))
    return "\n".join(lines) + "\n"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
