#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_render.py — 台账 → SVG 的通用、确定性节点-边绘图器（纯标准库）。

用法:
    python3 ledger_render.py <ledger.json> --out figure.svg [--title 标题]

设计原则（本技能的主角是台账，渲染器刻意保持简单、通用、健壮）:
  * 分层从左到右：元素带 order 字段时按 order 分列；否则按 connects_to 做
    分层拓扑（无前驱者入第 0 列，环回退到数组顺序），全程确定。
  * 每种 kind 一种外形：apparatus-unit=圆角矩形，step=矩形+序号徽章，
    stage=箭头形(chevron)，data-item=平行四边形，flow=六边形小节点，
    note=虚线框。 waived 元素统一琥珀色虚线描边并加 [waived] 角标。
  * connects_to 画带箭头连线（前向直线三次贝塞尔，回边绕下方）。
  * 每个元素一个 <g id="el-<eid>" data-eid="<eid>">，组内 <title> 含
    证据 quote（悬停可见，保证 SVG 本身可溯源、可编辑）。
  * 顶部标题块 + 底部图例（元素数、已验证数、豁免数、连线数）。
  * 输出不含时间戳/随机数，同一台账两次运行字节一致。
"""
import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

FONT = "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, sans-serif"
KIND_STYLE = {
    "apparatus-unit": {"fill": "#e8f0fe", "stroke": "#3b5bdb", "name": "装置单元"},
    "step":           {"fill": "#e6fcf5", "stroke": "#0ca678", "name": "步骤"},
    "stage":          {"fill": "#fff3bf", "stroke": "#f08c00", "name": "阶段"},
    "data-item":      {"fill": "#f3e8ff", "stroke": "#9c36b5", "name": "数据项"},
    "flow":           {"fill": "#ffe8e8", "stroke": "#e03131", "name": "流/物流"},
    "note":           {"fill": "#f8f9fa", "stroke": "#868e96", "name": "注记"},
}
WAIVED_STYLE = {"fill": "#fff9db", "stroke": "#fab005"}
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 40, 84, 92
COL_GAP, ROW_GAP = 110, 26
BADGE_R = 11


def disp_units(s: str) -> int:
    """显示宽度单位：CJK 记 2，其余记 1。"""
    return sum(2 if re.match(r"[　-鿿豈-﫿＀-￯]", ch) else 1 for ch in s)


def wrap_text(s: str, cap: int = 22):
    """按显示宽度折行（优先在空格处断开，避免拆散数字/单词），返回行列表。"""
    lines, cur, w = [], "", 0
    for ch in s:
        u = 2 if re.match(r"[　-鿿豈-﫿＀-￯]", ch) else 1
        if w + u > cap and cur:
            sp = cur.rfind(" ")
            if 0 < sp < len(cur) - 1:  # 在最后一个空格处断行
                lines.append(cur[:sp])
                cur = cur[sp + 1:]
                w = disp_units(cur)
            else:
                lines.append(cur)
                cur, w = "", 0
        cur += ch
        w += u
    if cur or not lines:
        lines.append(cur)
    return lines


def load_ledger(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data, data.get("elements", [])
    return {}, data


def assign_layers(elements):
    """返回 {index: layer}。优先 order 字段；否则 connects_to 分层拓扑。"""
    if elements and all("order" in e for e in elements):
        uniq = sorted({e["order"] for e in elements})
        rank = {v: i for i, v in enumerate(uniq)}
        return {i: rank[e["order"]] for i, e in enumerate(elements)}
    id2idx = {e.get("id"): i for i, e in enumerate(elements)}
    preds = {i: set() for i in range(len(elements))}
    for i, e in enumerate(elements):
        for t in e.get("connects_to", []) or []:
            j = id2idx.get(t)
            if j is not None and j != i:
                preds[j].add(i)
    layer = {}
    for _ in range(len(elements) + 1):
        progressed = False
        for i in range(len(elements)):
            if i in layer:
                continue
            pl = [layer[p] for p in preds[i] if p in layer]
            if len(pl) == len(preds[i]):
                layer[i] = (max(pl) + 1) if pl else 0
                progressed = True
        if not progressed:
            break
    for i in range(len(elements)):  # 环：按数组顺序收尾
        layer.setdefault(i, max(layer.values(), default=-1) + 1)
    return layer


def layout(elements):
    """计算每个元素的列、几何尺寸与坐标；返回 (boxes, edges, canvas_w, body_h)。"""
    layers = assign_layers(elements)
    n_cols = max(layers.values(), default=0) + 1
    cols = [[] for _ in range(n_cols)]
    for i, e in enumerate(elements):
        cols[layers[i]].append(i)

    boxes = []
    for i, e in enumerate(elements):
        label = str(e.get("label", e.get("id", f"el{i}")))
        lab_lines = wrap_text(label)
        src = e.get("source") or {}
        loc = src.get("locator") or src.get("file") or ""
        loc = str(loc)
        loc_lines = wrap_text("⟪" + loc + "⟫", cap=30) if loc else []
        text_w = max([disp_units(x) for x in lab_lines] + [10])
        w = max(120, min(260, text_w * 6.4 + 30))
        h = 20 + 18 * len(lab_lines) + (14 * len(loc_lines) + 6 if loc_lines else 0)
        if e.get("kind") == "step":
            h += 6
        boxes.append({"i": i, "layer": layers[i], "w": w, "h": h,
                      "lab_lines": lab_lines, "loc_lines": loc_lines,
                      "x": 0.0, "y": 0.0})

    col_w = [max((boxes[i]["w"] for i in cols[c]), default=160) for c in range(n_cols)]
    col_x, x = [], MARGIN_X
    for c in range(n_cols):
        col_x.append(x)
        x += col_w[c] + COL_GAP
    col_h = []
    for c in range(n_cols):
        hsum = sum(boxes[i]["h"] for i in cols[c]) + ROW_GAP * max(0, len(cols[c]) - 1)
        col_h.append(hsum)
    body_h = max(col_h, default=60)
    for c in range(n_cols):
        y = MARGIN_TOP + (body_h - col_h[c]) / 2.0
        for i in cols[c]:
            boxes[i]["x"] = col_x[c] + (col_w[c] - boxes[i]["w"]) / 2.0
            boxes[i]["y"] = y
            y += boxes[i]["h"] + ROW_GAP

    id2box = {elements[i].get("id"): boxes[i] for i in range(len(elements))}
    edges = []
    for i, e in enumerate(elements):
        for t in e.get("connects_to", []) or []:
            if t in id2box and t != e.get("id"):
                edges.append((boxes[i], id2box[t]))
    canvas_w = (col_x[-1] + col_w[-1] + MARGIN_X) if n_cols else 2 * MARGIN_X + 200
    return boxes, edges, canvas_w, body_h


def shape_svg(e, b):
    """按 kind 返回外形 SVG 片段（不含文本）。"""
    kind = e.get("kind", "note")
    st = KIND_STYLE.get(kind, KIND_STYLE["note"])
    if e.get("waived") is True:
        st = WAIVED_STYLE
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    dash = ' stroke-dasharray="6 4"' if (kind == "note" or e.get("waived") is True) else ""
    if kind == "apparatus-unit":
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="12" ry="12" fill="{st["fill"]}" stroke="{st["stroke"]}" '
                f'stroke-width="1.6"{dash}/>')
    if kind == "stage":  # chevron 箭头带
        cut = 16.0
        pts = (f"{x:.1f},{y:.1f} {x + w - cut:.1f},{y:.1f} {x + w:.1f},{y + h / 2:.1f} "
               f"{x + w - cut:.1f},{y + h:.1f} {x:.1f},{y + h:.1f} "
               f"{x + cut:.1f},{y + h / 2:.1f}")
        return (f'<polygon points="{pts}" fill="{st["fill"]}" '
                f'stroke="{st["stroke"]}" stroke-width="1.6"{dash}/>')
    if kind == "data-item":  # 平行四边形
        sk = 12.0
        pts = (f"{x + sk:.1f},{y:.1f} {x + w:.1f},{y:.1f} {x + w - sk:.1f},{y + h:.1f} "
               f"{x:.1f},{y + h:.1f}")
        return (f'<polygon points="{pts}" fill="{st["fill"]}" '
                f'stroke="{st["stroke"]}" stroke-width="1.6"{dash}/>')
    if kind == "flow":  # 六边形小节点
        k = 14.0
        pts = (f"{x + k:.1f},{y:.1f} {x + w - k:.1f},{y:.1f} {x + w:.1f},{y + h / 2:.1f} "
               f"{x + w - k:.1f},{y + h:.1f} {x + k:.1f},{y + h:.1f} {x:.1f},{y + h / 2:.1f}")
        return (f'<polygon points="{pts}" fill="{st["fill"]}" '
                f'stroke="{st["stroke"]}" stroke-width="1.6"{dash}/>')
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{st["fill"]}" stroke="{st["stroke"]}" stroke-width="1.6"{dash}/>')


def text_svg(e, b, step_no):
    cx = b["x"] + b["w"] / 2.0
    parts = []
    y = b["y"] + 16.0
    if e.get("kind") == "step":
        n = step_no
        bx = b["x"] + 8.0
        parts.append(f'<circle cx="{bx + BADGE_R:.1f}" cy="{b["y"] + 16:.1f}" r="{BADGE_R}" '
                     f'fill="#0ca678"/>')
        parts.append(f'<text x="{bx + BADGE_R:.1f}" y="{b["y"] + 20.5:.1f}" font-size="12" '
                     f'fill="#ffffff" text-anchor="middle" font-weight="bold">'
                     f'{escape(str(n))}</text>')
        y += 4.0
    for ln in b["lab_lines"]:
        y += 14.0
        parts.append(f'<text x="{cx:.1f}" y="{y:.1f}" font-size="13" fill="#212529" '
                     f'text-anchor="middle" font-weight="bold">{escape(ln)}</text>')
        y += 4.0
    if b["loc_lines"]:
        y += 2.0
        for ln in b["loc_lines"]:
            y += 12.0
            parts.append(f'<text x="{cx:.1f}" y="{y:.1f}" font-size="9.5" fill="#868e96" '
                         f'text-anchor="middle">{escape(ln)}</text>')
    if e.get("waived") is True:
        parts.append(f'<text x="{b["x"] + b["w"] - 4:.1f}" y="{b["y"] + 12:.1f}" '
                     f'font-size="9" fill="#f08c00" text-anchor="end">[waived]</text>')
    return "\n    ".join(parts)


def edge_svg(a, b, body_bottom):
    x1, y1 = a["x"] + a["w"], a["y"] + a["h"] / 2.0
    x2, y2 = b["x"], b["y"] + b["h"] / 2.0
    if x2 >= x1 - 4:  # 前向边
        m = (x1 + x2) / 2.0
        d = f"M {x1:.1f} {y1:.1f} C {m:.1f} {y1:.1f}, {m:.1f} {y2:.1f}, {x2 - 2:.1f} {y2:.1f}"
    else:  # 回边：绕下方
        x2, y2 = b["x"] + b["w"], b["y"] + b["h"] / 2.0
        yb = body_bottom + 30.0
        d = (f"M {x1:.1f} {y1:.1f} C {x1 + 40:.1f} {y1:.1f}, {x1 + 40:.1f} {yb:.1f}, "
             f"{x1 + 4:.1f} {yb:.1f} L {x2 + 4:.1f} {yb:.1f} "
             f"C {x2 + 40:.1f} {yb:.1f}, {x2 + 40:.1f} {y2:.1f}, {x2 + 2:.1f} {y2:.1f}")
    return f'<path d="{d}" fill="none" stroke="#495057" stroke-width="1.4" marker-end="url(#arrow)"/>'


def legend_svg(x, y, counts, n_edges):
    parts = [f'<text x="{x:.1f}" y="{y:.1f}" font-size="12" font-weight="bold" '
             f'fill="#343a40">图例</text>']
    lx = x + 44
    for kind in ("apparatus-unit", "step", "stage", "data-item", "flow", "note"):
        st = KIND_STYLE[kind]
        dash = ' stroke-dasharray="4 3"' if kind == "note" else ""
        parts.append(f'<rect x="{lx:.1f}" y="{y - 10:.1f}" width="14" height="11" '
                     f'rx="3" fill="{st["fill"]}" stroke="{st["stroke"]}"{dash}/>')
        parts.append(f'<text x="{lx + 18:.1f}" y="{y:.1f}" font-size="11" '
                     f'fill="#495057">{st["name"]}</text>')
        lx += 18 + disp_units(st["name"]) * 6.2 + 22
    parts.append(f'<line x1="{lx:.1f}" y1="{y - 4:.1f}" x2="{lx + 20:.1f}" y2="{y - 4:.1f}" '
                 f'stroke="#495057" stroke-width="1.4" marker-end="url(#arrow)"/>')
    parts.append(f'<text x="{lx + 26:.1f}" y="{y:.1f}" font-size="11" fill="#495057">连接</text>')
    summary = (f'元素 {counts["total"]} · 已验证 {counts["verified"]} · '
               f'豁免 {counts["waived"]} · 连线 {n_edges}')
    parts.append(f'<text x="{x:.1f}" y="{y + 22:.1f}" font-size="11" '
                 f'fill="#868e96">{escape(summary)}</text>')
    return "\n  ".join(parts)


def render(ledger, elements, title):
    boxes, edges, canvas_w, body_h = layout(elements)
    body_bottom = MARGIN_TOP + body_h
    canvas_h = body_bottom + MARGIN_BOTTOM + (34 if any(b1["layer"] >= b2["layer"]
                                             for b1, b2 in edges) else 0)
    counts = {"total": len(elements),
              "verified": sum(1 for e in elements if not e.get("waived")),
              "waived": sum(1 for e in elements if e.get("waived") is True)}

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{canvas_w:.0f}" height="{canvas_h:.0f}" '
           f'viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}" font-family="{FONT}">',
           '  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
           'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           '<path d="M 0 0 L 10 5 L 0 10 z" fill="#495057"/></marker></defs>',
           f'  <rect x="0" y="0" width="{canvas_w:.0f}" height="{canvas_h:.0f}" fill="#ffffff"/>']
    out.append(f'  <g id="title-block"><text x="{MARGIN_X}" y="34" font-size="18" '
               f'font-weight="bold" fill="#212529">{escape(title)}</text>')
    case_id = ledger.get("case_id", "") if isinstance(ledger, dict) else ""
    sub = f"case: {case_id} · 由 ledger.json 确定性渲染 · 每个图元携带 data-eid 可回查证据"
    out.append(f'  <text x="{MARGIN_X}" y="56" font-size="11" fill="#868e96">'
               f'{escape(sub)}</text></g>')

    out.append('  <g id="edges">')
    for a, b in edges:
        out.append("    " + edge_svg(a, b, body_bottom))
    out.append("  </g>")

    step_no = 0
    for i, e in enumerate(elements):
        b = boxes[i]
        if e.get("kind") == "step":
            step_no += 1
        eid = str(e.get("id", f"el{i}"))
        a_eid = escape(eid, {'"': "&quot;"})
        quote = str((e.get("source") or {}).get("quote", ""))[:160]
        out.append(f'  <g id="el-{a_eid}" data-eid="{a_eid}" '
                   f'class="kind-{escape(str(e.get("kind", "note")), {chr(34): "&quot;"})}">')
        if quote:
            out.append(f"    <title>{escape(quote)}</title>")
        out.append("    " + shape_svg(e, b))
        out.append("    " + text_svg(e, b, step_no))
        out.append("  </g>")

    out.append('  <g id="legend">')
    out.append("    " + legend_svg(MARGIN_X, canvas_h - 44, counts, len(edges)))
    out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="台账 → SVG 确定性渲染器")
    ap.add_argument("ledger", help="ledger.json 路径")
    ap.add_argument("--out", default="figure.svg", help="SVG 输出路径")
    ap.add_argument("--title", default=None, help="图标题（默认取 ledger meta.title）")
    args = ap.parse_args(argv)
    try:
        ledger, elements = load_ledger(Path(args.ledger))
    except Exception as exc:
        print(f"[ledger_render] 读取台账失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not elements:
        print("[ledger_render] 台账无元素，拒绝渲染空图", file=sys.stderr)
        return 1
    meta = ledger.get("meta", {}) if isinstance(ledger, dict) else {}
    title = args.title or meta.get("title") or "证据可溯源图"
    svg = render(ledger, elements, title)
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(svg)
    except Exception as exc:
        print(f"[ledger_render] 写入失败: {exc}", file=sys.stderr)
        return 2
    print(f"[ledger_render] {len(elements)} 元素 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
