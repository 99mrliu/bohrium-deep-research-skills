#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kg_export.py — 图谱导出：JSON / JSONL / CSV / Markdown 邻接表 / 无依赖 SVG / 哈希清单（仅标准库）。

确定性约定：所有输出只依赖图谱内容本身，不含时间戳、不含主机信息；
manifest.json 记录每个导出文件的 sha256 与 graph_hash，第三方可复算核对。

SVG 为手写 XML（不依赖任何图形库）：按节点类型分列、列内按 id 排序，
边为带箭头直线 + 中点关系标签，含图例。节点标签 = 名称（截断）+ 类型 + id。
"""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_loader import GraphLoadError, load_graph  # noqa: E402

# 类型 → 列顺序与颜色（固定顺序，保证确定性布局）
TYPE_ORDER = ["Researcher", "Material", "Method", "Task", "Metric",
              "Sample", "Condition", "Conclusion"]
TYPE_COLORS = ["#7fb3d3", "#82c99a", "#f0b27a", "#d7bde2",
               "#f7dc6f", "#f1948a", "#a3e4d7", "#d5dbdb"]


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def export_graph_json(g):
    payload = {
        "schema_version": "1.0",
        "graph_id": g.graph_id,
        "case_id": g.case_id,
        "graph_hash": g.graph_hash(),
        "sources": [g.sources[k] for k in sorted(g.sources)],
        "nodes": [g.nodes[k] for k in sorted(g.nodes)],
        "edges": [g.edges[k] for k in sorted(g.edges)],
        "merge_decisions": sorted(g.merge_decisions, key=lambda d: d.get("id", "")),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def export_graph_jsonl(g):
    lines = []
    for k in sorted(g.nodes):
        lines.append(json.dumps(dict(g.nodes[k], kind="node"),
                                ensure_ascii=False, sort_keys=True))
    for k in sorted(g.edges):
        lines.append(json.dumps(dict(g.edges[k], kind="edge"),
                                ensure_ascii=False, sort_keys=True))
    for d in sorted(g.merge_decisions, key=lambda d: d.get("id", "")):
        lines.append(json.dumps(dict(d, kind="merge_decision"),
                                ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


def export_nodes_csv(g):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "type", "name", "aliases", "n_evidence", "sources"])
    for k in sorted(g.nodes):
        n = g.nodes[k]
        srcs = sorted({e.get("source_id") for e in n.get("evidence", [])} - {None})
        w.writerow([n["id"], n["type"], n["name"],
                    "|".join(n.get("aliases", [])), len(n.get("evidence", [])),
                    "|".join(srcs)])
    return buf.getvalue()


def export_edges_csv(g):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "src", "relation", "dst", "conditions", "n_evidence", "sources"])
    for k in sorted(g.edges):
        e = g.edges[k]
        srcs = sorted({ev.get("source_id") for ev in e.get("evidence", [])} - {None})
        w.writerow([e["id"], e["src"], e["relation"], e["dst"],
                    e.get("conditions", ""), len(e.get("evidence", [])),
                    "|".join(srcs)])
    return buf.getvalue()


def export_markdown(g):
    """人类可读邻接表：每节点一节，含证据与出/入边。"""
    out = []
    out.append("# 图谱邻接表：%s\n" % g.graph_id)
    out.append("- graph_hash: `%s`" % g.graph_hash())
    c = g.counts()
    out.append("- 节点 %d / 边 %d / 来源 %d / 合并决策 %d\n"
               % (c["nodes"], c["edges"], c["sources"], c["merge_decisions"]))
    out.append("## 来源（sources）\n")
    for k in sorted(g.sources):
        s = g.sources[k]
        out.append("- **%s** — %s（DOI: %s；角色: %s）"
                   % (k, s.get("title", "?"), s.get("doi", "?"), s.get("role", "?")))
    out.append("\n## 节点邻接表\n")
    for k in sorted(g.nodes):
        n = g.nodes[k]
        out.append("### %s（%s）`%s`" % (n["name"], n["type"], k))
        if n.get("aliases"):
            out.append("- 别名: %s" % "、".join(n["aliases"]))
        for ev in n.get("evidence", []):
            out.append("- 证据: [%s ¶%s] “%s”"
                       % (ev.get("source_id"), ev.get("paragraph_id"), ev.get("quote")))
        for eid in g.out_adj.get(k, []):
            e = g.edges[eid]
            cond = "（条件: %s）" % e["conditions"] if e.get("conditions") else ""
            evs = "; ".join("[%s ¶%s] “%s”" % (ev.get("source_id"), ev.get("paragraph_id"),
                                               ev.get("quote")) for ev in e.get("evidence", []))
            out.append("- ─%s→ **%s**（%s）`%s`%s ｜证据: %s"
                       % (e["relation"], g.nodes[e["dst"]]["name"], e["dst"], eid, cond, evs))
        for eid in g.in_adj.get(k, []):
            e = g.edges[eid]
            out.append("- ←%s─ **%s**（%s）`%s`"
                       % (e["relation"], g.nodes[e["src"]]["name"], e["src"], eid))
        out.append("")
    out.append("## 合并 / 不合并决策\n")
    for d in sorted(g.merge_decisions, key=lambda d: d.get("id", "")):
        out.append("- `%s` **%s**: %s ⟷ %s%s — 依据: %s"
                   % (d.get("id", "?"), d.get("decision"),
                      d.get("left", "?"), d.get("right", "?"),
                      (" → %s" % d["canonical_node"]) if d.get("canonical_node") else "",
                      d.get("rationale", "")))
    return "\n".join(out) + "\n"


def _layout(g):
    """确定布局：类型分列，列内按 id 排序，均匀行距。"""
    types = [t for t in TYPE_ORDER if any(n["type"] == t for n in g.nodes.values())]
    types += sorted({n["type"] for n in g.nodes.values()} - set(types))
    col_x = {t: 40 + i * 240 for i, t in enumerate(types)}
    col_count = {t: 0 for t in types}
    pos = {}
    for k in sorted(g.nodes):
        t = g.nodes[k]["type"]
        i = col_count[t]
        col_count[t] += 1
        pos[k] = (col_x[t], 90 + i * 130)
    width = max(col_x.values()) + 260
    height = 90 + max(col_count.values()) * 130 + 40
    color = {t: TYPE_COLORS[types.index(t) % len(TYPE_COLORS)] for t in types}
    return pos, width, height, types, color


def export_svg(g):
    pos, width, height, types, color = _layout(g)
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                 'viewBox="0 0 %d %d" font-family="Helvetica, Arial, sans-serif">'
                 % (width, height, width, height))
    parts.append('<defs><marker id="arr" markerWidth="10" markerHeight="8" refX="9" refY="4" '
                 'orient="auto"><path d="M0,0 L9,4 L0,8 z" fill="#666"/></marker></defs>')
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (width, height))
    parts.append('<text x="16" y="24" font-size="16" font-weight="bold" fill="#222">%s</text>'
                 % escape("图谱预览: %s（节点 %d / 边 %d）"
                          % (g.graph_id, len(g.nodes), len(g.edges))))
    # 列标题
    for t in types:
        nodes_t = [k for k in sorted(g.nodes) if g.nodes[k]["type"] == t]
        x = pos[nodes_t[0]][0]
        parts.append('<rect x="%d" y="44" width="200" height="26" rx="4" fill="%s" opacity="0.55"/>'
                     % (x, color[t]))
        parts.append('<text x="%d" y="62" font-size="13" text-anchor="middle" fill="#111">%s</text>'
                     % (x + 100, escape(t)))
    # 边（先画线，避免覆盖节点）
    for eid in sorted(g.edges):
        e = g.edges[eid]
        x1, y1 = pos[e["src"]]
        x2, y2 = pos[e["dst"]]
        x1 += 200
        y1 += 27
        y2 += 27
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#888" stroke-width="1.4" '
                     'marker-end="url(#arr)"/>' % (x1, y1, x2, y2))
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2 - 4
        label = e["relation"] + (" *" if e.get("conditions") else "")
        parts.append('<rect x="%d" y="%d" width="%d" height="14" fill="#ffffff" opacity="0.85"/>'
                     % (mx - 6 * len(label), my - 11, 12 * len(label)))
        parts.append('<text x="%d" y="%d" font-size="11" text-anchor="middle" fill="#a33">%s</text>'
                     % (mx, my, escape(label)))
    # 节点
    for k in sorted(g.nodes):
        n = g.nodes[k]
        x, y = pos[k]
        name = n["name"]
        if len(name) > 14:
            name = name[:13] + "…"
        parts.append('<rect x="%d" y="%d" width="200" height="54" rx="6" fill="%s" '
                     'stroke="#555" stroke-width="1"/>' % (x, y, color[n["type"]]))
        parts.append('<text x="%d" y="%d" font-size="13" font-weight="bold" '
                     'text-anchor="middle" fill="#111">%s</text>'
                     % (x + 100, y + 22, escape(name)))
        parts.append('<text x="%d" y="%d" font-size="10" text-anchor="middle" fill="#333">%s ｜ %s</text>'
                     % (x + 100, y + 42, escape(n["type"]), escape(k)))
    parts.append('<text x="16" y="%d" font-size="10" fill="#777">%s</text>'
                 % (height - 12, escape("graph_hash: %s ｜ 边标签带 * 表示该边附有条件约束（conditions）"
                                        % g.graph_hash()[:16])))
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def export_all(graph_path, out_dir, label=None):
    """导出全部格式 + manifest.json。返回 manifest 字典。"""
    g = load_graph(graph_path)
    os.makedirs(out_dir, exist_ok=True)
    files = {
        "graph.json": export_graph_json(g),
        "graph.jsonl": export_graph_jsonl(g),
        "nodes.csv": export_nodes_csv(g),
        "edges.csv": export_edges_csv(g),
        "graph.md": export_markdown(g),
        "graph.svg": export_svg(g),
    }
    manifest = {"graph": os.path.abspath(graph_path), "out_dir": os.path.abspath(out_dir),
                "graph_hash": g.graph_hash(), "counts": g.counts(), "files": {}}
    if label:
        manifest["label"] = label
    for name, text in files.items():
        p = os.path.join(out_dir, name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        manifest["files"][name] = {"sha256": _sha(text.encode("utf-8")),
                                   "bytes": len(text.encode("utf-8"))}
    # SVG 良构性自检（XML 解析），不合格直接失败而不产出坏文件
    ET.fromstring(files["graph.svg"])
    mtext = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(mtext)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出图谱全部格式")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--label", default=None, help="产物标签，如 SYNTHETIC")
    args = ap.parse_args(argv)
    try:
        m = export_all(args.graph, args.out_dir, label=args.label)
    except GraphLoadError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("已导出 %d 个文件到 %s；graph_hash=%s"
          % (len(m["files"]), m["out_dir"], m["graph_hash"][:16]))
    for name, meta in sorted(m["files"].items()):
        print("  %-12s %8d bytes  sha256=%s" % (name, meta["bytes"], meta["sha256"][:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
