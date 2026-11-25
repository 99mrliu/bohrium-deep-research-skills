#!/usr/bin/env python3
"""Small deterministic renderer for the SYNTHETIC quality-gates demonstration.

The input specification is an Agent-authored translation of source material.
This renderer has no biology knowledge and makes no scientific decisions.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        tmp = Path(f.name)
    os.replace(tmp, path)


def sub(parent: ET.Element, tag: str, ident: str, **attrs: str) -> ET.Element:
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {"id": ident, **attrs})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("Renderer refuses to overwrite an existing SVG; runner controls replacement")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    entities = spec["entities"]
    edges = spec["edges"]
    if len({e["id"] for e in entities}) != len(entities) or len({e["id"] for e in edges}) != len(edges):
        ap.error("Non-unique specification IDs")
    root = ET.Element(f"{{{SVG}}}svg", {"id": "svg-root", "width": "900", "height": "600", "viewBox": "0 0 900 600", "version": "1.1"})
    sub(root, "title", "figure-title").text = spec["title"]
    sub(root, "metadata", "source-provenance").text = "SYNTHETIC; Agent-authored specification; renderer makes no scientific judgment"
    defs = sub(root, "defs", "definitions")
    for kind, color in (("direct", "#2563eb"), ("feedback", "#7c3aed"), ("uncertain", "#b45309")):
        marker = sub(defs, "marker", f"marker-{kind}", markerWidth="10", markerHeight="10", refX="9", refY="3", orient="auto", markerUnits="strokeWidth")
        sub(marker, "path", f"marker-{kind}-shape", d="M0,0 L0,6 L9,3 z", fill=color)
    sub(root, "rect", "background", x="0", y="0", width="900", height="600", fill="#f8fafc")
    sub(root, "text", "title-text", x="40", y="48", **{"font-family": "sans-serif", "font-size": "26", "font-weight": "700", "fill": "#0f172a"}).text = spec["title"]
    by_id = {e["id"]: e for e in entities}
    edge_layer = sub(root, "g", "edges-layer", fill="none", **{"stroke-width": "3"})
    positions = {e["id"]: (e["x"] + 90, e["y"] + 55) for e in entities}
    for edge in edges:
        src, dst = by_id[edge["source"]], by_id[edge["target"]]
        sid, tid = src["id"], dst["id"]
        if edge["kind"] == "feedback" and sid == "node-b" and tid == "node-a":
            d = "M600 322 C500 440 350 440 290 322"; p0, p1 = (350, 440), (290, 322)
        elif sid == "node-c" and tid == "node-b":
            d = "M655 162 L655 190"; p0, p1 = (655, 162), (655, 190)
        elif sid == "node-a" and tid == "node-b":
            d = "M327 255 L552 255"; p0, p1 = (327, 255), (552, 255)
        else:
            sx, sy = positions[sid]; tx, ty = positions[tid]
            import math
            length = math.hypot(tx-sx, ty-sy) or 1.0; ux, uy = (tx-sx)/length, (ty-sy)/length
            p0, p1 = (sx+ux*92, sy+uy*92), (tx-ux*92, ty-uy*92)
            d = f"M{p0[0]} {p0[1]} L{p1[0]} {p1[1]}"
        attrs = {"d": d, "stroke": edge.get("color", "#2563eb"), "data-kind": "edge", "data-edge-id": edge["id"], "data-source": sid, "data-target": tid, "data-relation": edge["relation"], "data-uncertainty": str(edge.get("uncertain", False)).lower(), "marker-end": f"url(#marker-{edge['kind']})"}
        if edge["kind"] in {"feedback", "uncertain"}:
            attrs["stroke-dasharray"] = "10 6" if edge["kind"] == "feedback" else "4 5"
        sub(edge_layer, "path", "edge-" + edge["id"], **attrs)
        import math
        length = math.hypot(p1[0]-p0[0], p1[1]-p0[1]) or 1.0
        ux, uy = (p1[0]-p0[0])/length, (p1[1]-p0[1])/length; px, py = -uy*7, ux*7
        color = edge.get("color", "#2563eb")
        if "inhibit" in edge["relation"].lower():
            sub(edge_layer, "line", "terminal-"+edge["id"], x1=str(p1[0]+px), y1=str(p1[1]+py), x2=str(p1[0]-px), y2=str(p1[1]-py), stroke=color, **{"stroke-width":"4", "data-terminal":"inhibition-tbar"})
        else:
            bx, by = p1[0]-ux*15, p1[1]-uy*15
            points = f"{p1[0]},{p1[1]} {bx+px},{by+py} {bx-px},{by-py}"
            sub(edge_layer, "polygon", "terminal-"+edge["id"], points=points, fill="white" if edge["kind"]=="uncertain" else color, stroke=color, **{"stroke-width":"2", "data-terminal":"direction-arrow"})
    nodes = sub(root, "g", "entities-layer", **{"font-family": "sans-serif"})
    for entity in entities:
        x, y = entity["x"], entity["y"]
        group = sub(nodes, "g", "group-" + entity["id"], **{"data-kind": "entity-container"})
        sub(group, "rect", "box-" + entity["id"], x=str(x), y=str(y), width="180", height="110", rx="12", fill=entity.get("fill", "#dbeafe"), stroke=entity.get("stroke", "#1e40af"), **{"stroke-width": "2"})
        sub(group, "text", "label-" + entity["id"], x=str(x + 90), y=str(y + 48), **{"text-anchor": "middle", "font-size": "21", "fill": "#0f172a", "data-kind": "entity", "data-entity-id": entity["id"], "data-label-source": entity["source"]}).text = entity["label"]
        sub(group, "text", "note-" + entity["id"], x=str(x + 90), y=str(y + 80), **{"text-anchor": "middle", "font-size": "13", "fill": "#475569"}).text = entity["note"]
    annotations = sub(root, "g", "annotations-layer", **{"font-family": "sans-serif"})
    for n, edge in enumerate(edges):
        coords = [(440, 236), (450, 455), (770, 180)][n]
        sub(annotations, "text", "edge-label-" + edge["id"], x=str(coords[0]), y=str(coords[1]), **{"text-anchor": "middle", "font-size": "15", "fill": edge.get("color", "#2563eb")}).text = edge["legend"]
    legend = sub(annotations, "g", "legend", **{"data-kind": "legend"})
    sub(legend, "rect", "legend-background", x="70", y="490", width="760", height="80", rx="8", fill="white", stroke="#cbd5e1")
    for n, item in enumerate(spec["legend"]):
        x = 105 + n * 245
        line_attrs = {"x1": str(x), "y1": str(529), "x2": str(x + 45), "y2": str(529), "stroke": item["color"], "stroke-width": "3"}
        sub(legend, "line", f"legend-line-{n}", **line_attrs)
        sub(legend, "text", f"legend-entry-{n}", x=str(x + 55), y=str(535), **{"font-size": "13", "fill": "#334155", "data-kind": "legend-entry", "data-relation": item["relation"], "data-uncertainty": str(item.get("uncertain", False)).lower()}).text = item["label"]
    ET.register_namespace("", SVG)
    atomic(args.output, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(json.dumps({"rendered": str(args.output), "entities": len(entities), "edges": len(edges), "scientific_decisions": "none"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
