#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_pack.py — 读 result.json，渲染人读交付包

产物（写入 --out，默认与 result.json 同目录）：
  * evidence_table.md   逐候选人读证据表：标题/年/层/来源/关联依据/locator
  * nodes.csv           节点表（id,doi,title,year,layer,stub）
  * edges.csv           边表（source,target,kind,direction_restored,locator）
  * preview_data.json   预览图数据源（坐标与边），供复核与重绘
  * network_preview.png matplotlib 可用时的引用网络预览（节点按层着色、
                        reference 实线 / 恢复的 citation 虚线）
    或 network_preview.svg  matplotlib 缺失（或 --svg-only）时由标准库手写

用法：
    python3 render_pack.py --result /app/output/result.json
    python3 render_pack.py --result ../examples/run_out/output/result.json --svg-only
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

LAYER_COLORS = {0: "#c0392b", 1: "#1f77b4", 2: "#2ca02c"}
STUB_COLOR = "#8c8c8c"


def short_label(text, limit=26):
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def radial_layout(seed_id, node_layers):
    """以种子为中心的放射布局：layer 1 内圈、layer 2 外圈，均匀分布。"""
    pos = {}
    if seed_id:
        pos[seed_id] = (0.0, 0.0)
    by_layer = {}
    for nid, lay in node_layers.items():
        if lay > 0:
            by_layer.setdefault(lay, []).append(nid)
    for lay in sorted(by_layer):
        nodes = sorted(by_layer[lay])
        radius = 1.0 * lay
        n = len(nodes)
        for i, nid in enumerate(nodes):
            ang = 2 * math.pi * i / max(1, n) - math.pi / 2
            pos[nid] = (radius * math.cos(ang), radius * math.sin(ang))
    return pos


def write_svg(path, nodes, edges, pos):
    """标准库手写 SVG 预览：节点按层着色、reference 实线 / citation 虚线。"""
    width, height, scale = 960, 720, 150
    cx, cy = width / 2, height / 2

    def xy(nid):
        x, y = pos.get(nid, (0.0, 0.0))
        return cx + x * scale, cy + y * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="16" y="28" font-size="18" font-family="sans-serif" fill="#333">'
        'citation network preview (seed-centered)</text>',
        '<text x="16" y="50" font-size="12" font-family="sans-serif" fill="#777">'
        'solid = reference (citing→cited) · dashed = citation restored from reverse index '
        '(cited→citing) · red = seed · blue = layer 1 · green = layer 2 · gray = stub</text>',
    ]
    for e in edges:
        x1, y1 = xy(e["source"])
        x2, y2 = xy(e["target"])
        dashed = bool(e.get("direction_restored") or e.get("kind") == "citation")
        if dashed:
            # 恢复的 citation 边画成二次曲线并加虚线，避免与反向 reference 边重叠
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            ox, oy = -dy / length * 28.0, dx / length * 28.0
            qx, qy = mx + ox, my + oy
            parts.append(f'<path d="M {x1:.1f} {y1:.1f} Q {qx:.1f} {qy:.1f} {x2:.1f} {y2:.1f}" '
                         f'fill="none" stroke="#555" stroke-width="1.4" stroke-dasharray="6,4"/>')
            parts.append(f'<text x="{qx:.1f}" y="{qy:.1f}" font-size="11" fill="#888" '
                         f'font-family="sans-serif" text-anchor="middle">⇢</text>')
        else:
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                         f'stroke="#555" stroke-width="1.4"/>')
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            parts.append(f'<text x="{mx:.1f}" y="{my:.1f}" font-size="11" fill="#888" '
                         f'font-family="sans-serif" text-anchor="middle">→</text>')
    for node in nodes:
        x, y = xy(node["id"])
        color = STUB_COLOR if node.get("stub") else LAYER_COLORS.get(node.get("layer", 1), "#9467bd")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="{color}" '
                     f'stroke="#222" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" fill="#fff" '
                     f'font-family="sans-serif" text-anchor="middle">{escape(node["id"])}</text>')
        label = escape(short_label(node.get("title") or node.get("unresolved_ref") or node["id"]))
        parts.append(f'<text x="{x:.1f}" y="{y + 32:.1f}" font-size="11" fill="#333" '
                     f'font-family="sans-serif" text-anchor="middle">{label}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_png(path, nodes, edges, pos):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9.6, 7.2))
    for e in edges:
        x1, y1 = pos.get(e["source"], (0, 0))
        x2, y2 = pos.get(e["target"], (0, 0))
        dashed = bool(e.get("direction_restored") or e.get("kind") == "citation")
        # 恢复的 citation 边弯曲并虚线化，避免与反向 reference 边重叠
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#555555", lw=1.2,
                                    linestyle="--" if dashed else "-",
                                    connectionstyle="arc3,rad=0.18" if dashed else "arc3,rad=0"),
                    zorder=1)
    for node in nodes:
        x, y = pos.get(node["id"], (0, 0))
        color = STUB_COLOR if node.get("stub") else LAYER_COLORS.get(node.get("layer", 1), "#9467bd")
        ax.scatter([x], [y], s=640, c=color, edgecolors="#222222", zorder=2)
        ax.text(x, y, node["id"], color="white", ha="center", va="center",
                fontsize=9, zorder=3)
        ax.text(x, y - 0.22, short_label(node.get("title") or node.get("unresolved_ref") or node["id"]),
                ha="center", va="top", fontsize=8, color="#333333", zorder=3)
    ax.set_title("citation network preview (seed-centered)\n"
                 "solid = reference, dashed = citation restored from reverse index")
    ax.axis("off")
    xs = [p[0] for p in pos.values()] or [0]
    ys = [p[1] for p in pos.values()] or [0]
    ax.set_xlim(min(xs) - 0.9, max(xs) + 0.9)
    ax.set_ylim(min(ys) - 0.9, max(ys) + 0.9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染 result.json 的人读交付包")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default=None, help="交付目录（默认与 result.json 同目录）")
    ap.add_argument("--svg-only", action="store_true",
                    help="强制标准库 SVG 预览（即使 matplotlib 可用；用于无二进制交付场景）")
    args = ap.parse_args()

    result_path = Path(args.result).resolve()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out).resolve() if args.out else result_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = result.get("seed") or result.get("seed_paper") or {}
    seed_id = seed.get("id", "")
    candidates = result.get("candidates") or []
    edges = result.get("edges") or []

    # ---- nodes.csv
    node_rows = []
    if seed_id:
        node_rows.append({"id": seed_id, "doi": seed.get("doi", ""), "title": seed.get("title", ""),
                          "year": seed.get("year", ""), "layer": 0, "stub": ""})
    for c in candidates:
        node_rows.append({"id": c["id"], "doi": c.get("doi", ""), "title": c.get("title", ""),
                          "year": c.get("year") or "", "layer": c.get("layer", ""),
                          "stub": "true" if c.get("stub") else ""})
    with (out_dir / "nodes.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "doi", "title", "year", "layer", "stub"])
        w.writeheader()
        w.writerows(node_rows)

    # ---- edges.csv
    with (out_dir / "edges.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["source", "target", "kind", "direction_restored",
                                           "locator_file", "locator_pointer"])
        w.writeheader()
        for e in edges:
            loc = e.get("locator") or {}
            w.writerow({"source": e["source"], "target": e["target"], "kind": e.get("kind", ""),
                        "direction_restored": "true" if e.get("direction_restored") else "false",
                        "locator_file": loc.get("file", ""), "locator_pointer": loc.get("pointer", "")})

    # ---- evidence_table.md
    lines = [
        "# 证据表（evidence table）",
        "",
        f"- case_id: `{result.get('case_id', '')}`  status: `{result.get('status', '')}`",
        f"- 种子: {seed.get('title', '')}（{seed.get('doi', '')}，id={seed_id}）",
        f"- 候选 {len(candidates)} 条 / 扩展边 {len(edges)} 条",
        "",
        "| # | 标题 | 年份 | 层 | stub | 关联依据 | locator |",
        "|---|------|------|----|------|----------|---------|",
    ]
    for i, c in enumerate(candidates, start=1):
        loc = c.get("source") or {}
        locator = f"{Path(loc.get('file', '')).name} :: {loc.get('pointer', '')}"
        title = c.get("title") or c.get("unresolved_ref") or "(未解析 stub)"
        lines.append(f"| {i} | {title} | {c.get('year') or ''} | {c.get('layer', '')} "
                     f"| {'是' if c.get('stub') else ''} | {c.get('relation', '')} | `{locator}` |")
    lines += ["", "## 引用边", "",
              "| source | target | kind | direction_restored | locator |",
              "|--------|--------|------|--------------------|---------|"]
    for e in edges:
        loc = e.get("locator") or {}
        locator = f"{Path(loc.get('file', '')).name} :: {loc.get('pointer', '')}"
        lines.append(f"| {e['source']} | {e['target']} | {e.get('kind', '')} "
                     f"| {'true' if e.get('direction_restored') else 'false'} | `{locator}` |")
    if result.get("uncertainty"):
        lines += ["", "## uncertainty", ""]
        lines += [f"- {u}" for u in result["uncertainty"]]
    (out_dir / "evidence_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 预览：布局 + 数据源 + PNG 或 SVG
    node_layers = {seed_id: 0} if seed_id else {}
    for c in candidates:
        node_layers[c["id"]] = int(c.get("layer") or 1)
    pos = radial_layout(seed_id, node_layers)
    node_meta = {}
    if seed_id:
        node_meta[seed_id] = {"id": seed_id, "title": seed.get("title", ""), "layer": 0, "stub": False}
    for c in candidates:
        node_meta[c["id"]] = {"id": c["id"], "title": c.get("title", ""),
                              "unresolved_ref": c.get("unresolved_ref", ""),
                              "layer": int(c.get("layer") or 1), "stub": bool(c.get("stub"))}
    preview_nodes = []
    for nid in sorted(node_layers, key=lambda n: (node_layers[n], n)):
        meta = node_meta.get(nid, {"id": nid, "title": "", "layer": node_layers[nid], "stub": False})
        x, y = pos.get(nid, (0.0, 0.0))
        preview_nodes.append({**meta, "x": round(x, 4), "y": round(y, 4)})
    preview_edges = [{"source": e["source"], "target": e["target"], "kind": e.get("kind", ""),
                      "direction_restored": bool(e.get("direction_restored"))} for e in edges]
    (out_dir / "preview_data.json").write_text(json.dumps(
        {"layout": "seed-centered radial", "nodes": preview_nodes, "edges": preview_edges},
        ensure_ascii=False, indent=2), encoding="utf-8")

    png_ok = False
    if not args.svg_only:
        try:
            write_png(out_dir / "network_preview.png", preview_nodes, preview_edges, pos)
            png_ok = True
        except ImportError:
            print("[render] matplotlib 不可用，降级为标准库 SVG 预览", file=sys.stderr)
    if not png_ok:
        write_svg(out_dir / "network_preview.svg", preview_nodes, preview_edges, pos)

    print(f"[render] deliverables written to {out_dir}:")
    for name in ("evidence_table.md", "nodes.csv", "edges.csv", "preview_data.json",
                 "network_preview.png" if png_ok else "network_preview.svg"):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
