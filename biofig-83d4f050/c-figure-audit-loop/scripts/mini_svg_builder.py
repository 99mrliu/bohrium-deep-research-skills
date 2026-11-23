#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mini_svg_builder.py — convenience claims.json -> SVG builder.

This is deliberately minimal: a simple compartment-band grid layout that
produces SVG obeying scripts/svg_conventions.py so the audit battery can
re-parse it. It is a CONVENIENCE, not the point of the skill — the agent
may draw the figure by any means (hand-written SVG, matplotlib+svg, a
diagram program) as long as the output follows the conventions and passes
the auditors. The intellectual core of the skill is the audit loop.

Layout:
  * one horizontal band per compartment (order of first appearance in
    claims; entities without a compartment go to an "unassigned" band);
  * entities laid out left-to-right inside their band, wrapping every
    `per_row` nodes;
  * edges are straight clipped lines between node boxes with the
    conventional marker (arrow for activates, T-bar for inhibits, none for
    binds) and dashed stroke for evidence="uncertain";
  * P / Ub badges at edge midpoints for phosphorylates / ubiquitinates;
  * a legend box (bottom-right) generated from claims.legend, with swatch
    colors taken from the item's "color" field or derived from the fill
    encoding scale (items named "<field>_low|_mid|_high").

Fill encoding: an encoding with channel="fill" maps entity.encodings[field]
through a scale string "diverging:<neg>-<zero>-<pos>;min=<v>;max=<v>".

Usage:
  python3 mini_svg_builder.py --claims claims.json --out figure.svg
"""

import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402

CANVAS_W, CANVAS_H = 1000, 720
NODE_W, NODE_H = 132, 46
PER_ROW = 3
BAND_TOP = 90          # first band starts here (title space)
BAND_PAD = 24
LEGEND_ITEM_H = 26
LEGEND_W = 300

TYPE_FILLS = {
    "gene": "#fde9d9",
    "protein": "#dceaf7",
    "complex": "#e6e0f2",
    "small_molecule": "#e7f4e4",
    "cell_type": "#f9e6ef",
    "other": "#eeeeee",
}


def load_claims(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# encoding scales
# --------------------------------------------------------------------------

def parse_scale(scale_str):
    """'diverging:#2166ac-#f7f7f7-#b2182b;min=-2;max=2' ->
    {'kind':'diverging','neg':'#..','zero':'#..','pos':'#..','min':-2,'max':2}"""
    out = {"kind": "diverging", "min": -1.0, "max": 1.0}
    if not scale_str:
        return out
    parts = scale_str.split(";")
    head = parts[0]
    if ":" in head:
        kind, colors = head.split(":", 1)
        out["kind"] = kind.strip()
        cols = [c.strip() for c in colors.split("-") if c.strip().startswith("#")]
        if kind.strip() == "diverging" and len(cols) >= 3:
            out["neg"], out["zero"], out["pos"] = cols[0], cols[1], cols[2]
        elif len(cols) >= 2:
            out["zero"], out["pos"] = cols[0], cols[1]
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


def scale_color(scale, value):
    """Map a numeric value through the parsed scale to a hex color."""
    if value is None:
        return scale.get("zero", "#f7f7f7")
    v = float(value)
    lo, hi = scale.get("min", -1.0), scale.get("max", 1.0)
    zero = scale.get("zero", "#f7f7f7")
    if scale.get("kind") == "diverging" and "neg" in scale:
        if v >= 0:
            t = v / hi if hi else 0.0
            return C.lerp_color(zero, scale["pos"], t)
        t = v / lo if lo else 0.0  # lo is negative
        return C.lerp_color(zero, scale["neg"], t)
    t = (v - lo) / (hi - lo) if hi != lo else 0.5
    return C.lerp_color(zero, scale.get("pos", "#b2182b"), t)


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

def compute_layout(claims):
    """Return a plain dict describing everything to draw. Shared with
    scripts/export_with_mpl.py so both render the SAME primitives."""
    entities = claims.get("entities", [])
    edges = claims.get("edges", [])

    comps = []
    for e in entities:
        comps.append(e.get("compartment") or "unassigned")
    band_order = []
    for c in comps:
        if c not in band_order:
            band_order.append(c)
    avail_h = CANVAS_H - BAND_TOP - BAND_PAD
    band_h = avail_h / max(1, len(band_order))

    nodes = {}
    band_counts = {}
    for e in entities:
        comp = e.get("compartment") or "unassigned"
        bi = band_order.index(comp)
        idx = band_counts.get(comp, 0)
        band_counts[comp] = idx + 1
        row, col = divmod(idx, PER_ROW)
        x = 60 + col * ((CANVAS_W - 120) / max(1, PER_ROW)) + NODE_W / 2 + 30
        y = BAND_TOP + bi * band_h + BAND_PAD + 20 + row * (NODE_H + 34)
        nodes[e["id"]] = {
            "id": e["id"], "label": e.get("label", e["id"]),
            "type": e.get("type", "other"),
            "compartment": comp,
            "source": e.get("source", ""),
            "cx": x, "cy": y, "w": NODE_W, "h": NODE_H,
            "fill": entity_fill(e, claims),
        }

    bands = []
    for bi, comp in enumerate(band_order):
        bands.append({
            "name": comp,
            "x": 30, "y": BAND_TOP + bi * band_h,
            "w": CANVAS_W - 60, "h": band_h - 8,
        })

    def clip(a, b):
        """Line from box-center a to box-center b, clipped to box borders."""
        ax, ay, bx, by = a["cx"], a["cy"], b["cx"], b["cy"]
        dx, dy = bx - ax, by - ay

        def t_exit(node, dx, dy):
            tx = (node["w"] / 2.0) / abs(dx) if dx else math.inf
            ty = (node["h"] / 2.0) / abs(dy) if dy else math.inf
            return min(tx, ty)

        t1 = t_exit(a, dx, dy)
        t2 = t_exit(b, -dx, -dy)
        return (ax + dx * t1, ay + dy * t1, bx - dx * t2, by - dy * t2)

    edge_list = []
    for e in edges:
        a, b = nodes.get(e.get("from")), nodes.get(e.get("to"))
        if not a or not b:
            continue
        x1, y1, x2, y2 = clip(a, b)
        edge_list.append({
            "id": e["id"], "kind": e.get("kind", "activates"),
            "from": e.get("from"), "to": e.get("to"),
            "evidence": e.get("evidence", "confirmed"),
            "source": e.get("source", ""),
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "badge": C.EDGE_BADGES.get(e.get("kind"), ""),
        })

    legend_items = []
    for i, item in enumerate(claims.get("legend", [])):
        legend_items.append({
            "item": item.get("item", "item%d" % i),
            "meaning": item.get("meaning", ""),
            "color": legend_color(item, claims),
        })
    leg_h = 18 + LEGEND_ITEM_H * max(1, len(legend_items))
    legend_box = {
        "x": CANVAS_W - LEGEND_W - 20, "y": CANVAS_H - leg_h - 14,
        "w": LEGEND_W, "h": leg_h,
    }
    for i, li in enumerate(legend_items):
        li["x"] = legend_box["x"] + 12
        li["y"] = legend_box["y"] + 14 + i * LEGEND_ITEM_H

    return {
        "canvas": {"w": CANVAS_W, "h": CANVAS_H},
        "title": claims.get("title", "mechanism diagram"),
        "nodes": nodes, "edges": edge_list,
        "bands": bands, "legend_items": legend_items,
        "legend_box": legend_box,
    }


def entity_fill(entity, claims):
    enc = entity.get("encodings") or {}
    for e in claims.get("encodings", []):
        if e.get("channel") == "fill" and e.get("field") in enc:
            return scale_color(parse_scale(e.get("scale")), enc[e["field"]])
    return TYPE_FILLS.get(entity.get("type", "other"), TYPE_FILLS["other"])


def legend_color(item, claims):
    if item.get("color"):
        return item["color"]
    name = item.get("item", "")
    for e in claims.get("encodings", []):
        if e.get("channel") != "fill":
            continue
        field = e.get("field", "")
        s = parse_scale(e.get("scale"))
        if name == field + "_low":
            return scale_color(s, s.get("min"))
        if name == field + "_high":
            return scale_color(s, s.get("max"))
        if name == field + "_mid":
            return s.get("zero", "#f7f7f7")
    return "#cccccc"


# --------------------------------------------------------------------------
# SVG emission
# --------------------------------------------------------------------------

def _sub(parent, tag, **attrs):
    """Add a sub-element; underscores in kwarg names become hyphens so
    Python-friendly names map to SVG attributes (stroke_width ->
    stroke-width, data_edge_kind -> data-edge-kind). CamelCase SVG attrs
    (refX, markerWidth, viewBox) contain no underscores and pass through."""
    el = ET.SubElement(parent, tag)
    for k, v in attrs.items():
        if v is not None:
            el.set(k.replace("_", "-"), str(v))
    return el


def build_svg(claims):
    lay = compute_layout(claims)
    C.register_ns()
    root = ET.Element("svg", {
        "xmlns": C.SVG_NS,
        "width": str(lay["canvas"]["w"]), "height": str(lay["canvas"]["h"]),
        "viewBox": "0 0 %d %d" % (lay["canvas"]["w"], lay["canvas"]["h"]),
        "font-family": "sans-serif",
    })
    _sub(root, "rect", x=0, y=0, width=lay["canvas"]["w"],
         height=lay["canvas"]["h"], fill="#ffffff", id="background")
    t = _sub(root, "text", x=30, y=44, font_size=22, id="title")
    t.text = lay["title"]

    defs = _sub(root, "defs")
    m = _sub(defs, "marker", id="marker-activates", markerWidth=10,
             markerHeight=10, refX=8, refY=3, orient="auto")
    _sub(m, "path", d="M0,0 L8,3 L0,6 Z", fill="#333333")
    m = _sub(defs, "marker", id="marker-arrow", markerWidth=10,
             markerHeight=10, refX=8, refY=3, orient="auto")
    _sub(m, "path", d="M0,0 L8,3 L0,6 Z", fill="#333333")
    m = _sub(defs, "marker", id="marker-inhibits", markerWidth=12,
             markerHeight=12, refX=8, refY=5, orient="auto")
    _sub(m, "path", d="M8,0 L8,10 Z", stroke="#c0392b", stroke_width=3,
         fill="none")

    # compartments
    gl = _sub(root, "g", id="layer-compartments")
    for b in lay["bands"]:
        _sub(gl, "rect", id=C.COMPARTMENT_PREFIX + b["name"],
             **{"class": "compartment-band", "x": b["x"], "y": b["y"],
                "width": b["w"], "height": b["h"], "fill": "#f4f6f8",
                "stroke": "#c8ced4", "stroke-dasharray": "2,3"})
        bt = _sub(gl, "text", x=b["x"] + 8, y=b["y"] + 16, font_size=12,
                  fill="#66707a", **{"class": "compartment-label"})
        bt.text = b["name"]

    # edges (under entities so boxes occlude line ends)
    gl = _sub(root, "g", id="layer-edges")
    for e in lay["edges"]:
        g = _sub(gl, "g", id=C.EDGE_PREFIX + e["id"], **{
            "class": "edge",
            "data_edge_kind": e["kind"],
            "data_from": e["from"], "data_to": e["to"],
            "data_evidence": e["evidence"],
            "data_source": e["source"] or None,
        })
        marker = C.EDGE_MARKERS.get(e["kind"])
        attrs = {"class": "edge-line", "x1": round(e["x1"], 1),
                 "y1": round(e["y1"], 1), "x2": round(e["x2"], 1),
                 "y2": round(e["y2"], 1), "stroke": "#333333",
                 "stroke_width": 2}
        if marker:
            attrs["marker_end"] = "url(#%s)" % marker
        if e["kind"] == "inhibits":
            attrs["stroke"] = "#c0392b"
        if e["evidence"] == "uncertain":
            attrs["stroke_dasharray"] = C.UNCERTAIN_DASH
        _sub(g, "line", **attrs)
        if e["badge"]:
            mx, my = (e["x1"] + e["x2"]) / 2.0, (e["y1"] + e["y2"]) / 2.0
            _sub(g, "circle", cx=round(mx, 1), cy=round(my, 1), r=10,
                 fill="#ffffff", stroke="#333333",
                 **{"class": "edge-badge-bg"})
            bt = _sub(g, "text", x=round(mx, 1), y=round(my + 4, 1),
                      font_size=11, text_anchor="middle",
                      **{"class": "edge-badge"})
            bt.text = e["badge"]

    # entities
    gl = _sub(root, "g", id="layer-entities")
    for n in lay["nodes"].values():
        g = _sub(gl, "g", id=C.ENTITY_PREFIX + n["id"], **{
            "class": "entity",
            "data_entity_type": n["type"],
            "data_compartment": n["compartment"],
            "data_source": n["source"] or None,
        })
        _sub(g, "rect", x=round(n["cx"] - n["w"] / 2, 1),
             y=round(n["cy"] - n["h"] / 2, 1), width=n["w"], height=n["h"],
             rx=8, fill=n["fill"], stroke="#45505a", stroke_width=1.2,
             **{"class": "entity-box"})
        attrs = {"x": round(n["cx"], 1), "y": round(n["cy"] + 4, 1),
                 "font_size": 13, "text_anchor": "middle",
                 "class": "entity-label"}
        if n["type"] == "gene":
            attrs["font_style"] = "italic"  # genes italic, proteins upright
        lt = _sub(g, "text", **attrs)
        lt.text = n["label"]

    # legend
    gl = _sub(root, "g", id="layer-legend")
    lb = lay["legend_box"]
    leg = _sub(gl, "g", id=C.LEGEND_ID)
    _sub(leg, "rect", x=lb["x"], y=lb["y"], width=lb["w"], height=lb["h"],
         fill="#ffffff", stroke="#9aa4ad", **{"class": "legend-frame"})
    for li in lay["legend_items"]:
        g = _sub(leg, "g", id=C.SWATCH_PREFIX + li["item"],
                 **{"class": "legend-item"})
        _sub(g, "rect", x=li["x"], y=li["y"], width=18, height=14,
             fill=li["color"], stroke="#555555", **{"class": "swatch"})
        lt = _sub(g, "text", x=li["x"] + 26, y=li["y"] + 12, font_size=11,
                  **{"class": "legend-label"})
        lt.text = "%s: %s" % (li["item"], li["meaning"]) if li["meaning"] \
            else li["item"]

    return ET.ElementTree(root)


def main():
    ap = argparse.ArgumentParser(description="claims.json -> convention SVG")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    claims = load_claims(args.claims)
    tree = build_svg(claims)
    C.register_ns()
    tree.write(args.out, encoding="utf-8", xml_declaration=True)
    print("wrote %s (%d entities, %d edges, %d legend items)" % (
        args.out, len(claims.get("entities", [])),
        len(claims.get("edges", [])), len(claims.get("legend", []))))


if __name__ == "__main__":
    main()
