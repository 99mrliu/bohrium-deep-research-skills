#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mxgraph_write.py -- emit figure.drawio (mxGraph XML) from a laid-out geometry model.

Structure: mxfile > diagram > mxGraphModel > root > mxCell(0,1, ...cells).
Mapping (see references/drawio-mapping.md for the full vocabulary):
  compartment  -> style "swimlane" vertex (entities parented inside, relative coords)
  protein/gene -> rounded=1 vertex (gene adds fontStyle=2 italic)
  small_molecule -> shape=ellipse
  complex      -> shape=ext;double=1 (double-bordered rectangle)
  receptor     -> plain tall rectangle placed across the membrane band
  edges        -> edge mxCells with endArrow semantics:
                  activation endArrow=classic, inhibition endArrow=bar,
                  binding endArrow=open, phosphorylation/ubiquitination classic + label
                  P / Ub, transport dashed=1, uncertain dashed=1 + label "?"
Cell ids are stable: "entity:<id>", "edge:<id>", "compartment:<id>".
Every cell carries data-* attributes (data-etype/data-ekind/data-source/...) and the
mxGraphModel carries data-geometry-sidecar so the geometry can be round-tripped.

Also exposes emit_cells() as a low-level writer used by build_chart.py.
CLI: python3 mxgraph_write.py --geometry FILE --out FILE [--sidecar NAME]
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import geometry as G  # noqa: E402

BASE_VERTEX = "whiteSpace=wrap;html=1;fontSize=13;fontFamily=Helvetica;strokeColor=#334155;strokeWidth=1.6;"
BASE_EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;strokeWidth=2;fontSize=12;fontFamily=Helvetica;"

EDGE_KIND_TO_MX = {
    # kind -> (endArrow, endFill, dashed, default label glyph)
    "activation": ("classic", 1, False, ""),
    "inhibition": ("bar", 0, False, ""),
    "binding": ("open", 0, False, ""),
    "phosphorylation": ("classic", 1, False, "P"),
    "ubiquitination": ("classic", 1, False, "Ub"),
    "transport": ("classic", 1, True, ""),
    "uncertain": ("classic", 1, True, "?"),
}
EDGE_COLORS = {k: v["color"] for k, v in G.EDGE_STYLES.items()}


def edge_style(kind, uncertain=False):
    arrow, fill, dashed, _ = EDGE_KIND_TO_MX.get(kind, EDGE_KIND_TO_MX["uncertain"])
    color = EDGE_COLORS.get(kind, "#64748b")
    if uncertain:
        dashed = True
        color = EDGE_COLORS["uncertain"]
    style = BASE_EDGE + "endArrow=%s;endFill=%d;strokeColor=%s;" % (arrow, fill, color)
    if dashed:
        style += "dashed=1;dashPattern=6 4;"
    return style


def vertex_style(etype, fill):
    if etype == "small_molecule":
        shape = "ellipse;"
    elif etype == "complex":
        shape = "shape=ext;double=1;"
    elif etype == "receptor":
        shape = "rounded=0;"
    else:
        shape = "rounded=1;arcSize=18;"
    style = shape + BASE_VERTEX + "fillColor=%s;" % fill
    if etype == "gene":
        style += "fontStyle=2;"  # italic
    return style


def swimlane_style(fill):
    return ("swimlane;fontSize=14;fontFamily=Helvetica;startSize=24;verticalAlign=top;"
            "align=left;spacingLeft=12;fillColor=%s;strokeColor=#94a3b8;html=1;" % fill)


def _esc_attrs(d):
    return {k: (str(v) if v is not None else "") for k, v in d.items()}


def model_to_cells(model, sidecar=""):
    """Convert a laid-out model to a list of mxCell dicts (also used by parse)."""
    G.layout(model)
    cells = []
    comp_pos = {}
    for c in model.get("compartments", []):
        cells.append({
            "id": "compartment:%s" % c["id"], "value": c.get("label", c["id"]),
            "style": swimlane_style(G.COMPARTMENT_FILL.get(c["band"], "#f8fafc")),
            "vertex": True, "parent": "1",
            "geom": {"x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"]},
            "data": {"data-ctype": "compartment", "data-band": c["band"],
                     "data-source": model.get("sources", {}).get(c["id"], "")},
        })
        comp_pos[c["id"]] = (c["x"], c["y"])
    for e in model.get("entities", []):
        parent = "1"
        gx, gy = e["x"], e["y"]
        if e.get("compartment") in comp_pos:
            parent = "compartment:%s" % e["compartment"]
            px, py = comp_pos[e["compartment"]]
            gx, gy = e["x"] - px, e["y"] - py
        cells.append({
            "id": "entity:%s" % e["id"], "value": e["label"],
            "style": vertex_style(e.get("type", "generic"), G._entity_fill(model, e)),
            "vertex": True, "parent": parent,
            "geom": {"x": gx, "y": gy, "w": e["w"], "h": e["h"]},
            "data": {"data-etype": e.get("type", "generic"),
                     "data-compartment": e.get("compartment", ""),
                     "data-source": model.get("sources", {}).get(e["id"], e.get("source", ""))},
        })
    for ed in model.get("edges", []):
        kind = ed.get("kind", "uncertain")
        uncertain = ed.get("evidence") == "uncertain"
        _, _, _, glyph = EDGE_KIND_TO_MX.get(kind, EDGE_KIND_TO_MX["uncertain"])
        value = ed.get("label") or glyph
        if uncertain and not value:
            value = "?"
        cells.append({
            "id": "edge:%s" % ed["id"], "value": value,
            "style": edge_style(kind, uncertain),
            "edge": True, "parent": "1",
            "source": "entity:%s" % ed["from"], "target": "entity:%s" % ed["to"],
            "points": ed.get("points", [])[1:-1],  # interior waypoints
            "data": {"data-ekind": kind,
                     "data-evidence": "uncertain" if uncertain else "supported",
                     "data-source": model.get("sources", {}).get(ed["id"], ed.get("source", ""))},
        })
    return cells


def emit_cells(path, cells, name="Page-1", sidecar=""):
    """Low-level writer: serialize a list of cell dicts as a .drawio mxfile."""
    mxfile = ET.Element("mxfile", {
        "host": "app.diagrams.net", "agent": "drawio-dual-source/1.0",
        "type": "device", "version": "24.0.0",
    })
    diagram = ET.SubElement(mxfile, "diagram", {"name": name, "id": "diagram-1"})
    attrs = {"dx": "1200", "dy": "800", "grid": "1", "gridSize": "10", "guides": "1",
             "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
             "pageScale": "1", "pageWidth": "1200", "pageHeight": "850",
             "math": "0", "shadow": "0"}
    if sidecar:
        attrs["data-geometry-sidecar"] = sidecar
    model_el = ET.SubElement(diagram, "mxGraphModel", attrs)
    root = ET.SubElement(model_el, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for cell in cells:
        a = {"id": cell["id"], "value": cell.get("value", ""),
             "style": cell.get("style", ""), "parent": cell.get("parent", "1")}
        if cell.get("vertex"):
            a["vertex"] = "1"
        if cell.get("edge"):
            a["edge"] = "1"
            if cell.get("source"):
                a["source"] = cell["source"]
            if cell.get("target"):
                a["target"] = cell["target"]
        a.update(_esc_attrs(cell.get("data", {})))
        el = ET.SubElement(root, "mxCell", a)
        if cell.get("vertex"):
            g = cell["geom"]
            ET.SubElement(el, "mxGeometry", {
                "x": "%.1f" % g["x"], "y": "%.1f" % g["y"],
                "width": "%.1f" % g["w"], "height": "%.1f" % g["h"],
                "as": "geometry"})
        elif cell.get("edge"):
            gel = ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
            pts = cell.get("points") or []
            if pts:
                arr = ET.SubElement(gel, "Array", {"as": "points"})
                for px, py in pts:
                    ET.SubElement(arr, "mxPoint", {"x": "%.1f" % px, "y": "%.1f" % py})
    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="  ")
    with open(path, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)
    return path


def write_drawio(model, path, sidecar=""):
    cells = model_to_cells(model, sidecar=sidecar)
    emit_cells(path, cells, name=model.get("id", "Page-1"), sidecar=sidecar)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="emit figure.drawio from geometry.json")
    ap.add_argument("--geometry", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sidecar", default="", help="geometry sidecar filename pointer")
    args = ap.parse_args(argv)
    model = G.load_geometry(args.geometry)
    write_drawio(model, args.out, sidecar=args.sidecar)
    print(json.dumps({"status": "ok", "drawio": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
