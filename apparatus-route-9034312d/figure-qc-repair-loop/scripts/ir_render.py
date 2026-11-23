#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ir_render.py — 轻量 Figure IR → 可编辑 SVG 渲染器（纯标准库，无第三方依赖）。

刻意简单的分层左→右布局：本 bundle 的核心是质检闭环（qc_figure.py），
渲染器只要求稳健、确定、可机检：
  - 每个节点一组 <g data-node-id="...">，含 <rect> + 真实 <text>；
  - 每条边一组 <g data-eid="..." data-kind="...">，含 <path> + 可选 <text>；
  - 有序节点（order 字段）自动加 S1..Sn 编号徽章；
  - 图例：IR 提供 legend 则按原文渲染（含可选 color/dash 覆盖字段，
    渲染器信任原文、不自动纠正——不一致由 QC 的 LEGEND_MISMATCH 检出）；
    IR 不提供则按实际用到的边类型自动生成；
  - 边端点指向不存在的节点 id 时，画到画布角落占位点并标 data-dangling，
    供 QC 的几何 DANGLING_EDGE 检出；
  - 坐标单位 = mm（viewBox 与 width/height 一致），字体走 CJK 回退链；
  - 确定性：同一 IR 两次渲染字节级一致（无时间戳、无随机、无集合序）。

用法: python3 ir_render.py figure_ir.json [-o figure.svg]
"""
import argparse
import json
import sys
from xml.sax.saxutils import escape

FONT_SIZE = 4.2          # mm（约 12pt）
EDGE_FS = 3.4
BADGE_FS = 3.0
TITLE_FS = 5.2
PAD_X = 3.0
BOX_H = 12.0
MIN_W = 18.0
MAX_W = 46.0             # 盒子最大宽度；超出即溢出（由 TEXT_OVERFLOW 检出）
MARGIN = 8.0
GAP_X = 26.0
GAP_Y = 9.0
TITLE_H = 10.0
LEGEND_ITEM_H = 7.0
DANGLING_X = 4.0         # 缺失端点的占位坐标
DANGLING_Y = 4.0

PALETTE = {
    "material":    {"color": "#1f77b4", "dash": None,  "label": "物料流"},
    "energy":      {"color": "#d62728", "dash": "4,2", "label": "能量流"},
    "information": {"color": "#2ca02c", "dash": "1,3", "label": "信息流"},
    "sequence":    {"color": "#666666", "dash": None,  "label": "步骤顺序"},
}
KIND_ORDER = ["material", "energy", "information", "sequence"]
NODE_FILL = {
    "equipment": "#eef3fb", "step": "#fff7e6", "material": "#f4fbf0",
    "input": "#f7f7f7", "output": "#f7f7f7",
}
NODE_STROKE = "#333333"
FONT_FAMILY = ("PingFang SC, Noto Sans CJK SC, Source Han Sans SC, "
               "WenQuanYi Micro Hei, Microsoft YaHei, sans-serif")


def F(v):
    """确定性数字格式化。"""
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def est_w(text, fs=FONT_SIZE):
    """估算文本宽度：CJK/全角 ≈ 1.0em，其余 ≈ 0.55em。"""
    return sum(fs if ord(c) >= 0x2E80 else fs * 0.55 for c in text)


def attr_escape(s):
    return escape(str(s), {'"': "&quot;"})


def compute_layers(nodes, edges):
    """order 显式指定层（order-1）；其余按有向边最长路径分层。"""
    idset = {n["id"] for n in nodes}
    explicit = set()
    layer = {}
    for n in nodes:
        o = n.get("order")
        if isinstance(o, (int, float)) and not isinstance(o, bool):
            layer[n["id"]] = max(0, int(o) - 1)
            explicit.add(n["id"])
    for n in nodes:
        layer.setdefault(n["id"], 0)
    for _ in range(64):
        changed = False
        for e in edges:
            a, b = e.get("from"), e.get("to")
            if a in idset and b in idset and b not in explicit:
                if layer[b] < layer[a] + 1:
                    layer[b] = layer[a] + 1
                    changed = True
        if not changed:
            break
    return layer


def build_legend(ir, edges):
    """返回 [{kind,label,color,dash}]；IR 有 legend 用原文，否则自动按用到的边类型生成。"""
    if isinstance(ir.get("legend"), list) and ir["legend"]:
        out = []
        for ent in ir["legend"]:
            kind = ent.get("kind", "")
            canon = PALETTE.get(kind, {"color": "#999999", "dash": "3,3", "label": kind})
            out.append({
                "kind": kind,
                "label": ent.get("label", canon["label"]),
                "color": ent.get("color", canon["color"]),
                "dash": ent.get("dash", canon["dash"]),
            })
        return out
    used = {e.get("kind") for e in edges}
    out = []
    for kind in KIND_ORDER:
        if kind in used:
            c = PALETTE[kind]
            out.append({"kind": kind, "label": c["label"],
                        "color": c["color"], "dash": c["dash"]})
    for kind in sorted(used):  # 未知类型兜底
        if kind not in PALETTE:
            out.append({"kind": kind, "label": kind,
                        "color": "#999999", "dash": "3,3"})
    return out


def render(ir):
    nodes = ir.get("nodes", [])
    edges = ir.get("edges", [])
    idset = {n["id"] for n in nodes}
    layer = compute_layers(nodes, edges)

    # 盒子尺寸
    geom = {}
    for n in nodes:
        label = str(n.get("label", n["id"]))
        w = min(max(est_w(label) + 2 * PAD_X, MIN_W), MAX_W)
        geom[n["id"]] = {"w": w, "h": BOX_H, "label": label}

    # 列（层）布局
    layers = {}
    for n in nodes:
        layers.setdefault(layer[n["id"]], []).append(n)
    for lv in layers.values():
        lv.sort(key=lambda n: (n.get("order") if isinstance(n.get("order"), (int, float)) else 9999,
                               str(n["id"])))
    col_x = {}
    x = MARGIN
    for lv in sorted(layers):
        col_w = max(geom[n["id"]]["w"] for n in layers[lv])
        col_x[lv] = x
        x += col_w + GAP_X
    content_w = x - GAP_X + MARGIN
    y0 = MARGIN + TITLE_H
    content_bottom = y0
    for lv in sorted(layers):
        for i, n in enumerate(layers[lv]):
            g = geom[n["id"]]
            g["x"] = col_x[lv]
            g["y"] = y0 + i * (BOX_H + GAP_Y)
            content_bottom = max(content_bottom, g["y"] + BOX_H)

    legend = build_legend(ir, edges)
    legend_h = (len(legend) * LEGEND_ITEM_H + 6.0) if legend else 0.0

    # 画布
    cv = ir.get("canvas")
    if isinstance(cv, dict) and cv.get("width_mm") and cv.get("height_mm"):
        W, H = float(cv["width_mm"]), float(cv["height_mm"])
    else:
        W = content_w
        H = content_bottom + legend_h + MARGIN

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
               f'width="{F(W)}mm" height="{F(H)}mm" viewBox="0 0 {F(W)} {F(H)}">')
    out.append(f'<title>{escape(str(ir.get("title", "figure")))}</title>')

    # 箭头 marker（仅实际用到的边类型，按规范调色板）
    used_kinds = []
    for e in edges:
        k = e.get("kind")
        if k not in used_kinds:
            used_kinds.append(k)
    out.append("<defs>")
    for k in used_kinds:
        color = PALETTE.get(k, {"color": "#999999"})["color"]
        out.append(f'<marker id="arr-{attr_escape(k)}" viewBox="0 0 10 10" refX="9" refY="5" '
                   f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path d="M 0 1 L 9 5 L 0 9 z" fill="{color}"/></marker>')
    out.append("</defs>")

    out.append(f'<rect x="0" y="0" width="{F(W)}" height="{F(H)}" fill="#ffffff" stroke="none"/>')
    title = str(ir.get("title", ""))
    if title:
        out.append(f'<text x="{F(MARGIN)}" y="{F(MARGIN + TITLE_FS * 0.4)}" '
                   f'font-size="{F(TITLE_FS)}" font-weight="bold" '
                   f'font-family="{FONT_FAMILY}" fill="#111111">{escape(title)}</text>')

    # 边
    dangling_i = 0
    for i, e in enumerate(edges):
        eid = str(e.get("id") or f"e{i + 1}")
        kind = e.get("kind", "sequence")
        canon = PALETTE.get(kind, {"color": "#999999", "dash": "3,3"})
        color, dash = canon["color"], canon["dash"]
        a, b = e.get("from"), e.get("to")
        dangling = []
        if a in geom:
            ga = geom[a]
            p0 = (ga["x"] + ga["w"], ga["y"] + ga["h"] / 2)
        else:
            p0 = (DANGLING_X, DANGLING_Y + dangling_i * 6.0)
            dangling.append("from")
        if b in geom:
            gb = geom[b]
            p1 = (gb["x"], gb["y"] + gb["h"] / 2)
        else:
            p1 = (DANGLING_X, DANGLING_Y + dangling_i * 6.0)
            dangling.append("to")
        if dangling:
            dangling_i += 1
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        dang_attr = f' data-dangling="{",".join(dangling)}"' if dangling else ""
        out.append(f'<g data-eid="{attr_escape(eid)}" data-kind="{attr_escape(kind)}"{dang_attr}>')
        out.append(f'<path d="M {F(p0[0])} {F(p0[1])} L {F(p1[0])} {F(p1[1])}" '
                   f'fill="none" stroke="{color}" stroke-width="0.9"{dash_attr} '
                   f'marker-end="url(#arr-{attr_escape(kind)})"/>')
        if e.get("label"):
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - 1.6
            out.append(f'<text x="{F(mx)}" y="{F(my)}" font-size="{F(EDGE_FS)}" '
                       f'text-anchor="middle" font-family="{FONT_FAMILY}" '
                       f'fill="{color}">{escape(str(e["label"]))}</text>')
        out.append("</g>")

    # 节点
    for n in nodes:
        nid = str(n["id"])
        g = geom[n["id"]]
        fill = NODE_FILL.get(n.get("kind", ""), "#f7f7f7")
        out.append(f'<g data-node-id="{attr_escape(nid)}">')
        out.append(f'<rect x="{F(g["x"])}" y="{F(g["y"])}" width="{F(g["w"])}" '
                   f'height="{F(g["h"])}" rx="1.5" fill="{fill}" stroke="{NODE_STROKE}" '
                   f'stroke-width="0.5"/>')
        cx, cy = g["x"] + g["w"] / 2, g["y"] + g["h"] / 2
        out.append(f'<text x="{F(cx)}" y="{F(cy)}" font-size="{F(FONT_SIZE)}" '
                   f'text-anchor="middle" dominant-baseline="central" '
                   f'font-family="{FONT_FAMILY}" fill="#111111">'
                   f'{escape(g["label"])}</text>')
        o = n.get("order")
        if isinstance(o, (int, float)) and not isinstance(o, bool):
            bx, by = g["x"], g["y"]
            out.append(f'<circle cx="{F(bx)}" cy="{F(by)}" r="3.2" fill="#ffffff" '
                       f'stroke="{NODE_STROKE}" stroke-width="0.5"/>')
            out.append(f'<text data-badge="1" x="{F(bx)}" y="{F(by)}" '
                       f'font-size="{F(BADGE_FS)}" text-anchor="middle" '
                       f'dominant-baseline="central" font-family="{FONT_FAMILY}" '
                       f'fill="#111111">S{int(o)}</text>')
        out.append("</g>")

    # 图例
    if legend:
        ly = content_bottom + 5.0
        out.append('<g data-legend="1">')
        for i, ent in enumerate(legend):
            ey = ly + i * LEGEND_ITEM_H + 3.0
            dash_attr = f' stroke-dasharray="{ent["dash"]}"' if ent["dash"] else ""
            out.append(f'<g data-legend-entry="1" data-kind="{attr_escape(ent["kind"])}">')
            out.append(f'<line x1="{F(MARGIN)}" y1="{F(ey)}" x2="{F(MARGIN + 12)}" '
                       f'y2="{F(ey)}" stroke="{ent["color"]}" stroke-width="0.9"{dash_attr}/>')
            out.append(f'<text x="{F(MARGIN + 15)}" y="{F(ey)}" font-size="{F(EDGE_FS)}" '
                       f'dominant-baseline="central" font-family="{FONT_FAMILY}" '
                       f'fill="#333333">{escape(str(ent["label"]))}</text>')
            out.append("</g>")
        out.append("</g>")

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("ir")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args(argv[1:])
    try:
        with open(args.ir, "r", encoding="utf-8") as f:
            ir = json.load(f)
    except Exception as exc:
        print(f"[ir_render] IR 读取失败: {exc}", file=sys.stderr)
        return 1
    for i, n in enumerate(ir.get("nodes", [])):
        if "id" not in n:
            print(f"[ir_render] 节点缺少 id（第 {i} 个）", file=sys.stderr)
            return 1
    svg = render(ir)
    out_path = args.out or (args.ir.rsplit(".", 1)[0] + ".svg")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[ir_render] {args.ir} -> {out_path} "
          f"({len(ir.get('nodes', []))} nodes, {len(ir.get('edges', []))} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
