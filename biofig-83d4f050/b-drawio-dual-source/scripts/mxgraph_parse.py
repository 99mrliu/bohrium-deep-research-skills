#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mxgraph_parse.py -- parse a .drawio file back into a geometry model (geometry.json).

Reads mxCell vertices (compartments / entities) and edges, reconstructs absolute
positions (cells parented to a swimlane are relative to it), maps mx styles back to
entity types and edge kinds (endArrow=classic|bar|open, dashed=1, labels P/Ub/?).

Round-trip limits (reported in model["_skipped"] and printed as warnings):
  * mxCells whose id is neither entity:/edge:/compartment: and carry no data-etype
    are skipped and reported.
  * Freehand vertex styles that no longer match a known entity type become "generic".
  * data-* custom attributes survive edits done by edit_cells.py or plain XML
    editing; a save performed inside diagrams.net itself may strip them (the parser
    then falls back to style inspection and marks evidence as uncertain when the
    edge kind cannot be determined).

CLI: python3 mxgraph_parse.py --drawio FILE --out geometry.json
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

KIND_FROM_ARROW = [
    # (predicate(style_attrs), kind)
    (lambda a: a.get("endArrow") == "bar", "inhibition"),
    (lambda a: a.get("endArrow") == "open", "binding"),
    (lambda a: a.get("endArrow") in ("classic", "block") and a.get("dashed") == "1", "transport"),
    (lambda a: a.get("endArrow") in ("classic", "block"), "activation"),
]


def parse_style(style):
    out = {}
    for part in (style or "").split(";"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
        else:
            out[part] = "1"
    return out


def _etype_from_style(attrs, data_etype):
    if data_etype:
        return data_etype
    if attrs.get("shape") == "ellipse" or "ellipse" in attrs:
        return "small_molecule"
    if attrs.get("shape") == "ext":
        return "complex"
    if attrs.get("fontStyle") == "2":
        return "gene"
    if attrs.get("rounded") == "1":
        return "protein"
    return "generic"


def parse_drawio(path):
    """Return (model, report). model is a laid-out geometry dict."""
    tree = ET.parse(path)
    root_el = tree.getroot()
    if root_el.tag != "mxfile":
        raise ValueError("not a drawio mxfile: root tag %r" % root_el.tag)
    model_el = root_el.find(".//mxGraphModel")
    if model_el is None:
        raise ValueError("no mxGraphModel found")
    sidecar = model_el.get("data-geometry-sidecar", "")
    cells = {}
    skipped = []
    for el in model_el.iter("mxCell"):
        cells[el.get("id")] = el

    comps, ents, edges = {}, {}, {}
    for cid, el in cells.items():
        if cid in ("0", "1"):
            continue
        style = parse_style(el.get("style", ""))
        if el.get("vertex") == "1":
            if cid.startswith("compartment:") or "swimlane" in style:
                g = el.find("mxGeometry")
                comps[cid] = {
                    "id": cid.split(":", 1)[1] if ":" in cid else cid,
                    "label": el.get("value", ""),
                    "band": el.get("data-band", _band_from_y(float(g.get("y", 0)))),
                    "x": float(g.get("x", 0)), "y": float(g.get("y", 0)),
                    "w": float(g.get("width", 0)), "h": float(g.get("height", 0)),
                }
            elif cid.startswith("entity:") or el.get("data-etype"):
                g = el.find("mxGeometry")
                parent = el.get("parent", "1")
                x, y = float(g.get("x", 0)), float(g.get("y", 0))
                if parent in comps or (parent in cells and parent.startswith("compartment:")):
                    pel = cells[parent].find("mxGeometry") if parent in cells else None
                    if pel is None and parent in comps:
                        x += comps[parent]["x"]
                        y += comps[parent]["y"]
                    elif pel is not None:
                        x += float(pel.get("x", 0))
                        y += float(pel.get("y", 0))
                fill = style.get("fillColor", "")
                ent = {
                    "id": cid.split(":", 1)[1] if ":" in cid else cid,
                    "label": el.get("value", ""),
                    "type": _etype_from_style(style, el.get("data-etype", "")),
                    "compartment": el.get("data-compartment", ""),
                    "x": x, "y": y,
                    "w": float(g.get("width", 0)), "h": float(g.get("height", 0)),
                }
                if fill:
                    ent["fill"] = fill
                if el.get("data-source"):
                    ent["source"] = el.get("data-source")
                ents[ent["id"]] = ent
            else:
                skipped.append({"id": cid, "reason": "unrecognized vertex style/id"})
        elif el.get("edge") == "1":
            if not (cid.startswith("edge:") or el.get("data-ekind")):
                skipped.append({"id": cid, "reason": "edge without edge: id or data-ekind"})
                continue
            src, tgt = el.get("source", ""), el.get("target", "")
            src = src.split(":", 1)[1] if src.startswith("entity:") else src
            tgt = tgt.split(":", 1)[1] if tgt.startswith("entity:") else tgt
            kind = el.get("data-ekind", "")
            label = el.get("value", "")
            if not kind:
                kind = "uncertain"
                for pred, k in KIND_FROM_ARROW:
                    if pred(style):
                        kind = k
                        break
                if label == "P" and kind == "activation":
                    kind = "phosphorylation"
                elif label == "Ub" and kind == "activation":
                    kind = "ubiquitination"
            pts = []
            gel = el.find("mxGeometry")
            if gel is not None:
                arr = gel.find("Array")
                if arr is not None:
                    for p in arr.findall("mxPoint"):
                        pts.append([float(p.get("x", 0)), float(p.get("y", 0))])
            ed = {"id": cid.split(":", 1)[1] if ":" in cid else cid,
                  "from": src, "to": tgt, "kind": kind}
            if label and label not in ("P", "Ub", "?"):
                ed["label"] = label
            if el.get("data-evidence") == "uncertain" or (not el.get("data-ekind") and kind == "uncertain"):
                ed["evidence"] = "uncertain"
            if el.get("data-source"):
                ed["source"] = el.get("data-source")
            if pts:
                ed["_waypoints"] = pts
            edges[ed["id"]] = ed

    # resolve compartment membership from parenting when data-compartment missing
    for cid, el in cells.items():
        if el.get("vertex") == "1" and (cid.startswith("entity:")):
            parent = el.get("parent", "")
            if parent.startswith("compartment:"):
                eid = cid.split(":", 1)[1]
                if eid in ents and not ents[eid]["compartment"]:
                    ents[eid]["compartment"] = parent.split(":", 1)[1]

    model = {
        "id": "reparsed",
        "note": "re-parsed from %s" % path,
        "canvas": {"width": 1200, "height": 850},
        "compartments": list(comps.values()),
        "entities": list(ents.values()),
        "edges": list(edges.values()),
        "encodings": [],
        "sources": {e["id"]: e["source"] for e in ents.values() if e.get("source")},
        "laid_out": True,
        "sidecar": sidecar,
        "_skipped": skipped,
    }
    report = {"skipped": skipped, "entities": len(ents), "edges": len(edges),
              "compartments": len(comps), "sidecar": sidecar}
    return model, report


def _band_from_y(y):
    for band, (y0, y1) in (("extracellular", (40, 170)), ("membrane", (170, 250)),
                           ("cytosol", (250, 520)), ("nucleus", (520, 700))):
        if y0 <= y < y1:
            return band
    return "cytosol"


def main(argv=None):
    ap = argparse.ArgumentParser(description="parse .drawio back to geometry.json")
    ap.add_argument("--drawio", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    model, report = parse_drawio(args.drawio)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
