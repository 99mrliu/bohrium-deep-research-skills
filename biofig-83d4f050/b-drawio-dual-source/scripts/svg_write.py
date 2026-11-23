#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg_write.py -- emit a layered, hand-editable SVG from drawing primitives.

Layers (top-level groups, in paint order):
  <g id="layer-compartments">, <g id="layer-edges">,
  <g id="layer-entities">,   <g id="layer-legend">
Element ids are stable ("entity:<id>", "edge:<id>", ...) so a human can find and
edit any node in a text editor. All text is real <text> (never paths). Data-source
locators ride along as data-source attributes. The full geometry JSON is embedded
in <metadata> so the SVG alone can regenerate the model.

write_primitives(path, prims, width, height, metadata) is the low-level entry used
by build_chart.py; write_svg(model, path) is the pathway entry point.
CLI: python3 svg_write.py --geometry FILE --out FILE
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import geometry as G  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

LAYERS = ["compartments", "edges", "entities", "legend", "chart"]


def _markers(defs):
    """Arrowhead markers: classic (filled), open (hollow), bar (T / inhibition)."""
    for mid, fill, path_d, refx in (
        ("arrow-classic", "context-stroke", "M 0 0 L 10 4 L 0 8 z", 9),
        ("arrow-open", "none", "M 1 1 L 10 4 L 1 7", 9),
        ("arrow-bar", "context-stroke", "M 7 0 L 7 8", 6),
    ):
        m = ET.SubElement(defs, "marker", {
            "id": mid, "viewBox": "0 0 10 8" if mid != "arrow-bar" else "0 0 8 8",
            "refX": str(refx), "refY": "4",
            "markerWidth": "8", "markerHeight": "8",
            "orient": "auto-start-reverse"})
        st = {"fill": fill, "stroke": "context-stroke", "stroke-width": "1.2"}
        ET.SubElement(m, "path", {"d": path_d, **st})


def _prim_el(parent, p):
    data = {}
    if p.get("source"):
        data["data-source"] = str(p["source"])
    if p.get("role"):
        data["data-role"] = str(p["role"])
    for extra in ("etype", "ekind", "band"):
        if p.get(extra):
            data["data-%s" % extra] = str(p[extra])
    if p["kind"] == "rect":
        a = {"id": p["id"], "x": "%.1f" % p["x"], "y": "%.1f" % p["y"],
             "width": "%.1f" % p["w"], "height": "%.1f" % p["h"],
             "fill": p.get("fill", "#ffffff"), "stroke": p.get("stroke", "#000000"),
             "stroke-width": str(p.get("stroke_w", 1.5))}
        if p.get("rounded"):
            a["rx"] = "9"
        el = ET.SubElement(parent, "rect", {**a, **data})
        if p.get("double"):  # complex: inner border
            ET.SubElement(parent, "rect", {
                "id": p["id"] + ":inner",
                "x": "%.1f" % (p["x"] + 5), "y": "%.1f" % (p["y"] + 5),
                "width": "%.1f" % (p["w"] - 10), "height": "%.1f" % (p["h"] - 10),
                "fill": "none", "stroke": p.get("stroke", "#000000"),
                "stroke-width": "1.1", **data})
        return el
    if p["kind"] == "ellipse":
        return ET.SubElement(parent, "ellipse", {
            "id": p["id"], "cx": "%.1f" % p["cx"], "cy": "%.1f" % p["cy"],
            "rx": "%.1f" % p["rx"], "ry": "%.1f" % p["ry"],
            "fill": p.get("fill", "#ffffff"), "stroke": p.get("stroke", "#000000"),
            "stroke-width": str(p.get("stroke_w", 1.5)), **data})
    if p["kind"] == "polyline":
        pts = " ".join("%.1f,%.1f" % (x, y) for x, y in p["points"])
        a = {"id": p["id"], "points": pts, "fill": "none",
             "stroke": p.get("stroke", "#000000"),
             "stroke-width": str(p.get("stroke_w", 2.0)),
             "stroke-linejoin": "round", "stroke-linecap": "round"}
        if p.get("dashed"):
            a["stroke-dasharray"] = "6 4"
        arrow = p.get("arrow", "none")
        if arrow and arrow != "none":
            a["marker-end"] = "url(#arrow-%s)" % arrow
        return ET.SubElement(parent, "polyline", {**a, **data})
    if p["kind"] == "text":
        a = {"id": p["id"], "x": "%.1f" % p["x"], "y": "%.1f" % p["y"],
             "font-size": str(p.get("size", 12)),
             "font-family": "Helvetica, Arial, sans-serif",
             "fill": p.get("color", "#000000"),
             "text-anchor": p.get("anchor", "middle")}
        if p.get("italic"):
            a["font-style"] = "italic"
        if p.get("bold"):
            a["font-weight"] = "bold"
        el = ET.SubElement(parent, "text", {**a, **data})
        el.text = str(p.get("text", ""))
        return el
    raise ValueError("unknown primitive kind: %r" % p.get("kind"))


def write_primitives(path, prims, width, height, metadata=None):
    """Write any primitive list as a layered SVG (used by charts too)."""
    svg = ET.Element("svg", {
        "xmlns": SVG_NS, "width": "%.0f" % width, "height": "%.0f" % height,
        "viewBox": "0 0 %.0f %.0f" % (width, height), "version": "1.1"})
    if metadata is not None:
        meta = ET.SubElement(svg, "metadata", {"id": "embedded-geometry"})
        meta.text = json.dumps(metadata, ensure_ascii=False)
    defs = ET.SubElement(svg, "defs")
    _markers(defs)
    ET.SubElement(svg, "rect", {"id": "background", "x": "0", "y": "0",
                                "width": "%.0f" % width, "height": "%.0f" % height,
                                "fill": "#ffffff"})
    groups = {}
    for layer in LAYERS:
        groups[layer] = ET.SubElement(svg, "g", {"id": "layer-%s" % layer})
    for p in prims:
        layer = p.get("layer", "entities")
        _prim_el(groups.get(layer, groups["entities"]), p)
    tree = ET.ElementTree(svg)
    ET.indent(tree, space="  ")
    with open(path, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)
    return path


def write_svg(model, path):
    W, H, prims, _ = G.primitives(model)
    write_primitives(path, prims, W, H, metadata=model)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="emit layered SVG from geometry.json")
    ap.add_argument("--geometry", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    model = G.load_geometry(args.geometry)
    write_svg(model, args.out)
    print(json.dumps({"status": "ok", "svg": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
