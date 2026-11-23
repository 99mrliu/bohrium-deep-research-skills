#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可读预览导出：graph.dot（Graphviz DOT）、graph.svg（纯 stdlib 生成）、
graph_preview.md（中文可读文本预览）。不依赖 graphviz 二进制。
用法：
  python3 graph_preview.py --graph graph.json --outdir <dir>
"""
import argparse
import math
import sys

from relation_common import load_json, dump_json

TYPE_COLOR = {"model": "#4C78A8", "dataset": "#F58518", "metric": "#54A24B",
              "condition": "#B279A2", "task": "#E45756", "method": "#72B7B2"}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_dot(graph):
    lines = ["digraph G {", "  rankdir=LR;",
             '  node [shape=ellipse, style=filled, fillcolor="#EEE"];']
    labels = {n["node_id"]: n.get("label", n["node_id"]) for n in graph["nodes"]}
    for n in graph["nodes"]:
        color = TYPE_COLOR.get(n.get("type"), "#999999")
        lines.append('  "%s" [label="%s\\n(%s)", fillcolor="%s"];'
                     % (n["node_id"], labels[n["node_id"]], n.get("type", "?"), color))
    for e in graph["edges"]:
        tag = e.get("relation", "?")
        if e.get("in_conflict"):
            tag += " ⚠conflict"
        if e.get("voice") == "cited-background":
            tag += " [cited]"
        lines.append('  "%s" -> "%s" [label="%s"];'
                     % (e.get("subject"), e.get("object"), tag))
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_svg(graph):
    nodes = graph["nodes"]
    n = max(len(nodes), 1)
    W, H, R = 960, 560, 190
    cx, cy = W / 2, H / 2
    pos = {}
    for i, nd in enumerate(nodes):
        ang = 2 * math.pi * i / n - math.pi / 2
        pos[nd["node_id"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang) * 0.8)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'font-family="sans-serif">' % (W, H),
             '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" '
             'refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#555"/>'
             '</marker></defs>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="12" y="22" font-size="13" fill="#a00">'
             'SYNTHETIC 示例图谱预览（非正式案例结果）</text>']
    for e in graph["edges"]:
        x1, y1 = pos.get(e.get("subject"), (cx, cy))
        x2, y2 = pos.get(e.get("object"), (cx, cy))
        color = "#c00" if e.get("in_conflict") else "#555"
        dash = ' stroke-dasharray="5,4"' if e.get("voice") == "cited-background" else ""
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="1.4"%s marker-end="url(#arr)"/>'
                     % (x1, y1, x2, y2, color, dash))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append('<text x="%.1f" y="%.1f" font-size="9" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (mx, my - 3, color, esc(e.get("relation", ""))))
    for nd in nodes:
        x, y = pos[nd["node_id"]]
        color = TYPE_COLOR.get(nd.get("type"), "#999")
        parts.append('<circle cx="%.1f" cy="%.1f" r="26" fill="%s" '
                     'fill-opacity="0.85" stroke="#333"/>' % (x, y, color))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="white" '
                     'text-anchor="middle">%s</text>' % (x, y + 3, esc(nd.get("label", nd["node_id"]))))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def to_markdown(graph):
    lines = ["# 图谱可读预览（SYNTHETIC 示例）", ""]
    mr = graph.get("merge_report", {})
    lines.append("## 节点（%d）" % len(graph["nodes"]))
    for nd in graph["nodes"]:
        ev = (nd.get("evidence") or [{}])[0]
        lines.append("- `%s` [%s] %s —— 证据 %s/%s: “%s”"
                     % (nd["node_id"], nd.get("type"), nd.get("label"),
                        ev.get("source_id", "?"), ev.get("paragraph_id", "?"),
                        ev.get("quote", "")[:80]))
    lines.append("")
    lines.append("## 边（%d）" % len(graph["edges"]))
    for e in graph["edges"]:
        cond = e.get("conditions") or {}
        cond_s = ", ".join("%s=%s" % kv for kv in sorted(cond.items())) or "（无）"
        meas = e.get("measurement") or {}
        meas_s = ("；测量 %s=%s %s" % (meas.get("kind", "value"),
                  meas.get("value"), meas.get("unit"))) if meas else ""
        flags = []
        if e.get("in_conflict"):
            flags.append("⚠冲突保留")
        if e.get("voice") == "cited-background":
            flags.append("背景转述·非一手证据")
        flag_s = (" 【" + "；".join(flags) + "】") if flags else ""
        lines.append("- `%s` %s → `%s`（voice=%s；条件：%s%s）%s"
                     % (e.get("subject"), e.get("relation"), e.get("object"),
                        e.get("voice"), cond_s, meas_s, flag_s))
    lines.append("")
    lines.append("## 合并/不合并")
    for m in mr.get("merges", []):
        lines.append("- 合并：%s（依据：%s）" % (" ↔ ".join(m.get("nodes", [])),
                                                 m.get("rationale", "")))
    for m in mr.get("non_merges", []):
        lines.append("- 不合并：%s（理由：%s）" % (" ≠ ".join(m.get("nodes", [])),
                                                  m.get("rationale", "")))
    cooc = graph.get("cooccurrence_notes", [])
    if cooc:
        lines.append("")
        lines.append("## 共现记录（共现≠直接关系，不建边）")
        for c in cooc:
            lines.append("- %s：%s" % ("、".join(c.get("nodes", [])),
                                       c.get("decision", "")))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="图谱可读预览导出")
    ap.add_argument("--graph", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)
    graph = load_json(args.graph)
    out = args.outdir.rstrip("/")
    with open(out + "/graph.dot", "w", encoding="utf-8") as fh:
        fh.write(to_dot(graph))
    with open(out + "/graph.svg", "w", encoding="utf-8") as fh:
        fh.write(to_svg(graph))
    with open(out + "/graph_preview.md", "w", encoding="utf-8") as fh:
        fh.write(to_markdown(graph))
    print("preview: graph.dot / graph.svg / graph_preview.md -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
