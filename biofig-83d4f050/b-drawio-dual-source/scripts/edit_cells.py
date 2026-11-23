#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_cells.py -- structured, source-preserving edits on a .drawio file.

Ops (JSON list, --ops FILE):
  {"op": "set-label",     "cell": "entity:akt", "value": "AKT1"}
  {"op": "set-color",     "cell": "entity:akt", "value": "#ff8800"}
  {"op": "move-cell",     "cell": "entity:akt", "dx": 40, "dy": -20}
  {"op": "set-edge-kind", "cell": "edge:e1",    "kind": "inhibition"}
  {"op": "add-edge",      "from": "akt", "to": "mtor", "kind": "activation", "label": ""}
  {"op": "remove-cell",   "cell": "edge:e1"}

Behaviour:
  1. Backs up the drawio to versions/<name>.vN.drawio (N auto-increments) BEFORE
     any modification.
  2. Applies ops one by one via XML manipulation with existence checks; a failed op
     is recorded honestly (status "failed") and does not abort the remaining ops.
  3. Appends one entry per op -- with before/after XML snippets and a UTC
     timestamp -- to the edit journal (--edit-record FILE, JSON).
  4. With --reexport --geometry-out FILE the edited drawio is re-parsed to a
     geometry model so SVG/PNG/PDF can be regenerated from the edited source.

CLI: python3 edit_cells.py --drawio FILE --ops FILE --edit-record FILE
     [--reexport --geometry-out FILE]
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

EDGE_KIND_TO_MX = {
    "activation": ("classic", 1, False, ""),
    "inhibition": ("bar", 0, False, ""),
    "binding": ("open", 0, False, ""),
    "phosphorylation": ("classic", 1, False, "P"),
    "ubiquitination": ("classic", 1, False, "Ub"),
    "transport": ("classic", 1, True, ""),
    "uncertain": ("classic", 1, True, "?"),
}
EDGE_COLORS = {
    "activation": "#15803d", "inhibition": "#b91c1c", "binding": "#475569",
    "phosphorylation": "#7e22ce", "ubiquitination": "#7e22ce",
    "transport": "#1d4ed8", "uncertain": "#64748b",
}
BASE_EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;"
             "orthogonalLoop=1;strokeWidth=2;fontSize=12;fontFamily=Helvetica;")


def _norm_cell_id(name):
    if ":" in name:
        return name
    return "entity:%s" % name


def _edge_style(kind):
    arrow, fill, dashed, _ = EDGE_KIND_TO_MX.get(kind, EDGE_KIND_TO_MX["uncertain"])
    s = BASE_EDGE + "endArrow=%s;endFill=%d;strokeColor=%s;" % (
        arrow, fill, EDGE_COLORS.get(kind, "#64748b"))
    if dashed:
        s += "dashed=1;dashPattern=6 4;"
    return s


def _set_style_key(style, key, value):
    parts = [p for p in style.split(";") if p and not p.startswith(key + "=")]
    parts.append("%s=%s" % (key, value))
    return ";".join(parts) + ";"


def _backup(path):
    vdir = os.path.join(os.path.dirname(os.path.abspath(path)), "versions")
    os.makedirs(vdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    n = 1
    while os.path.exists(os.path.join(vdir, "%s.v%d.drawio" % (base, n))):
        n += 1
    dest = os.path.join(vdir, "%s.v%d.drawio" % (base, n))
    shutil.copy2(path, dest)
    return dest


def _snippet(el):
    if el is None:
        return None
    s = ET.tostring(el, encoding="unicode")
    return s if len(s) <= 600 else s[:600] + "..."


def _find_cell(root_el, cell_id):
    for el in root_el.iter("mxCell"):
        if el.get("id") == cell_id:
            return el
    return None


def _next_edit_edge_id(root_el):
    n = 1
    existing = {el.get("id") for el in root_el.iter("mxCell")}
    while "edge:edit-%d" % n in existing:
        n += 1
    return "edge:edit-%d" % n


def apply_op(root_el, op):
    """Apply one op; returns (ok, detail, before_snippet, after_snippet)."""
    kind = op.get("op")
    if kind == "add-edge":
        src = _norm_cell_id(op.get("from", ""))
        tgt = _norm_cell_id(op.get("to", ""))
        for cid, role in ((src, "from"), (tgt, "to")):
            if _find_cell(root_el, cid) is None:
                return False, "%s cell %r not found" % (role, cid), None, None
        ekind = op.get("kind", "uncertain")
        _, _, _, glyph = EDGE_KIND_TO_MX.get(ekind, EDGE_KIND_TO_MX["uncertain"])
        eid = _next_edit_edge_id(root_el)
        el = ET.SubElement(root_el, "mxCell", {
            "id": eid, "value": op.get("label", "") or glyph,
            "style": _edge_style(ekind), "edge": "1", "parent": "1",
            "source": src, "target": tgt,
            "data-ekind": ekind, "data-evidence": op.get("evidence", "supported"),
            "data-source": op.get("source", "edit")})
        ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
        return True, "added %s (%s -> %s)" % (eid, src, tgt), None, _snippet(el)

    cell = _norm_cell_id(op.get("cell", ""))
    el = _find_cell(root_el, cell)
    if el is None:
        return False, "cell %r not found" % cell, None, None
    before = _snippet(el)

    if kind == "set-label":
        el.set("value", str(op.get("value", "")))
    elif kind == "set-color":
        el.set("style", _set_style_key(el.get("style", ""), "fillColor",
                                       str(op.get("value", ""))))
    elif kind == "move-cell":
        g = el.find("mxGeometry")
        if g is None:
            return False, "cell %r has no mxGeometry" % cell, before, None
        g.set("x", "%.1f" % (float(g.get("x", 0)) + float(op.get("dx", 0))))
        g.set("y", "%.1f" % (float(g.get("y", 0)) + float(op.get("dy", 0))))
    elif kind == "set-edge-kind":
        if el.get("edge") != "1":
            return False, "cell %r is not an edge" % cell, before, None
        ekind = op.get("kind", "uncertain")
        _, _, _, glyph = EDGE_KIND_TO_MX.get(ekind, EDGE_KIND_TO_MX["uncertain"])
        el.set("style", _edge_style(ekind))
        el.set("data-ekind", ekind)
        if glyph and not el.get("value"):
            el.set("value", glyph)
    elif kind == "remove-cell":
        parent = None
        for cand in root_el.iter():
            if el in list(cand):
                parent = cand
                break
        if parent is None:
            return False, "could not locate parent of %r" % cell, before, None
        parent.remove(el)
        removed_edges = []
        for other in list(root_el.iter("mxCell")):
            if other.get("edge") == "1" and (
                    other.get("source") == cell or other.get("target") == cell):
                other_parent = None
                for cand in root_el.iter():
                    if other in list(cand):
                        other_parent = cand
                        break
                if other_parent is not None:
                    other_parent.remove(other)
                    removed_edges.append(other.get("id"))
        return True, "removed %s (plus edges: %s)" % (
            cell, ", ".join(removed_edges) or "none"), before, None
    else:
        return False, "unknown op %r" % kind, before, None
    return True, "%s applied to %s" % (kind, cell), before, _snippet(el)


def load_record(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
            if isinstance(rec, dict) and "entries" in rec:
                return rec
        except Exception:
            pass
    return {"journal": "drawio cell-level edit record", "entries": []}


def main(argv=None):
    ap = argparse.ArgumentParser(description="cell-level edits on a .drawio file")
    ap.add_argument("--drawio", required=True)
    ap.add_argument("--ops", required=True, help="JSON list of ops")
    ap.add_argument("--edit-record", required=True)
    ap.add_argument("--reexport", action="store_true",
                    help="re-parse edited drawio to geometry")
    ap.add_argument("--geometry-out", help="geometry JSON output when --reexport")
    args = ap.parse_args(argv)

    with open(args.ops, "r", encoding="utf-8") as fh:
        ops = json.load(fh)
    if not isinstance(ops, list):
        ops = [ops]

    backup = _backup(args.drawio)
    tree = ET.parse(args.drawio)
    mxfile = tree.getroot()
    model_el = mxfile.find(".//mxGraphModel")
    root_el = model_el.find("root")

    record = load_record(args.edit_record)
    results = []
    for op in ops:
        ok, detail, before, after = apply_op(root_el, op)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "drawio": os.path.abspath(args.drawio),
            "backup": backup,
            "op": op,
            "status": "applied" if ok else "failed",
            "detail": detail,
            "before": before,
            "after": after,
        }
        record["entries"].append(entry)
        results.append({"op": op.get("op"), "cell": op.get("cell") or
                        "%s->%s" % (op.get("from"), op.get("to")),
                        "status": entry["status"], "detail": detail})

    ET.indent(tree, space="  ")
    with open(args.drawio, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)

    os.makedirs(os.path.dirname(os.path.abspath(args.edit_record)), exist_ok=True)
    with open(args.edit_record, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)

    reexport = None
    if args.reexport:
        if not args.geometry_out:
            results.append({"op": "reexport", "status": "failed",
                            "detail": "--geometry-out required with --reexport"})
        else:
            sys.path.insert(0, __file__.rsplit("/", 1)[0])
            import mxgraph_parse  # noqa: E402
            model, report = mxgraph_parse.parse_drawio(args.drawio)
            with open(args.geometry_out, "w", encoding="utf-8") as fh:
                json.dump(model, fh, ensure_ascii=False, indent=2)
            reexport = {"geometry_out": args.geometry_out, "report": report}

    summary = {"status": "ok" if all(r["status"] == "applied" for r in results
                                     if r.get("op") != "reexport") else "partial",
               "drawio": os.path.abspath(args.drawio), "backup": backup,
               "edit_record": os.path.abspath(args.edit_record),
               "results": results, "reexport": reexport}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
