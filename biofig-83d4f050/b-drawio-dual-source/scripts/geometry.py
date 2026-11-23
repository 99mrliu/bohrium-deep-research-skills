#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
geometry.py -- geometry model + deterministic layout for mechanism/pathway diagrams.

Model format (geometry.json):
{
  "id": "case-id",
  "note": "provenance note (mark 'synthetic' if example)",
  "canvas": {"width": 1200, "height": 850},
  "compartments": [ {"id": "cytosol", "label": "...", "band": "cytosol"} ],
  "entities": [ {"id", "label", "type": protein|gene|small_molecule|complex|receptor|generic,
                 "compartment", "col"?, "row"?, "source"?, "fill"?, "uncertain"?} ],
  "edges": [ {"id", "from", "to", "kind": activation|inhibition|binding|phosphorylation|
              ubiquitination|transport|uncertain, "label"?, "source"?, "evidence"?} ],
  "encodings": [ {"kind": "log2fc_color", "field", "source", "legend", "map": {entity_id: value}} ],
  "sources": {entity_or_edge_id: "paper.pdf p.4 Fig.2"}
}

Deterministic layout: compartments become horizontal swimlane bands with fixed
y-ranges (extracellular > membrane > cytosol > nucleus, top to bottom). Entities are
placed left->right by flow layer (longest-path layering over edges, overridable with
"col"), stacked vertically within their band. Edges route as orthogonal polylines;
edges whose target band is ABOVE the source band are feedback and route below both
entities; multiple edges leaving one node fan out with offset exit points.

Functions: load_geometry(path), layout(model), primitives(model).
CLI: python3 geometry.py --geometry FILE --out FILE [--primitives FILE]
"""
import argparse
import json
import sys

# --- fixed band geometry (top -> bottom) -------------------------------------
BANDS = {
    "extracellular": (40.0, 170.0),
    "membrane": (170.0, 250.0),
    "cytosol": (250.0, 520.0),
    "nucleus": (520.0, 700.0),
}
BAND_ORDER = ["extracellular", "membrane", "cytosol", "nucleus"]
CANVAS_W = 1200.0
CANVAS_H = 700.0          # bands region; legend strip is appended below
LEGEND_H = 150.0
MARGIN_X = 60.0

ENTITY_SIZE = {
    "protein": (150.0, 60.0),
    "gene": (150.0, 60.0),
    "small_molecule": (110.0, 50.0),
    "complex": (170.0, 80.0),
    "receptor": (70.0, 150.0),
    "generic": (140.0, 60.0),
}
DEFAULT_FILL = {
    "protein": "#dbeafe", "gene": "#fef3c7", "small_molecule": "#dcfce7",
    "complex": "#ede9fe", "receptor": "#fee2e2", "generic": "#f1f5f9",
}
STROKE = "#334155"
COMPARTMENT_FILL = {
    "extracellular": "#f8fafc", "membrane": "#fde68a",
    "cytosol": "#f0fdf4", "nucleus": "#eff6ff",
}

EDGE_STYLES = {
    "activation":     {"arrow": "classic", "dashed": False, "color": "#15803d", "glyph": ""},
    "inhibition":     {"arrow": "bar",     "dashed": False, "color": "#b91c1c", "glyph": ""},
    "binding":        {"arrow": "open",    "dashed": False, "color": "#475569", "glyph": ""},
    "phosphorylation": {"arrow": "classic", "dashed": False, "color": "#7e22ce", "glyph": "P"},
    "ubiquitination": {"arrow": "classic", "dashed": False, "color": "#7e22ce", "glyph": "Ub"},
    "transport":      {"arrow": "classic", "dashed": True,  "color": "#1d4ed8", "glyph": ""},
    "uncertain":      {"arrow": "classic", "dashed": True,  "color": "#64748b", "glyph": "?"},
}
EDGE_KIND_LABELS = {
    "activation": "激活 activation", "inhibition": "抑制 inhibition",
    "binding": "结合 binding", "phosphorylation": "磷酸化 phosphorylation",
    "ubiquitination": "泛素化 ubiquitination", "transport": "转运 transport",
    "uncertain": "不确定 uncertain",
}


def load_geometry(path):
    """Load and lightly validate a geometry model from JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        model = json.load(fh)
    for key in ("entities", "edges"):
        model.setdefault(key, [])
    model.setdefault("compartments", [])
    model.setdefault("encodings", [])
    model.setdefault("sources", {})
    ids = set()
    for e in model["entities"]:
        if "id" not in e or "label" not in e:
            raise ValueError("entity missing id/label: %r" % e)
        if e["id"] in ids:
            raise ValueError("duplicate entity id: %s" % e["id"])
        ids.add(e["id"])
        e.setdefault("type", "generic")
    for e in model["edges"]:
        if e.get("from") not in ids or e.get("to") not in ids:
            raise ValueError("edge %r references unknown entity" % e.get("id"))
        e.setdefault("kind", "uncertain")
    return model


def _log2fc_color(value, vmax=2.0):
    """Diverging white->blue (neg) / white->red (pos) fill for log2FC encodings."""
    t = max(-1.0, min(1.0, float(value) / max(vmax, 1e-9)))
    if t >= 0:
        r, g, b = 255, int(255 * (1 - t) + 38 * t), int(255 * (1 - t) + 38 * t)
    else:
        r, g, b = int(255 * (1 + t) + 33 * t * -1), int(255 * (1 + t) + 102 * -t), 255
    return "#%02x%02x%02x" % (r, g, b)


def _entity_fill(model, ent):
    enc = _encoding_for(model, ent["id"])
    if enc is not None:
        kind, encdef, value = enc
        if kind == "log2fc_color":
            vmax = max([abs(v) for v in encdef.get("map", {}).values()] + [1.0])
            return _log2fc_color(value, vmax)
    if ent.get("fill"):
        return ent["fill"]
    return DEFAULT_FILL.get(ent.get("type", "generic"), DEFAULT_FILL["generic"])


def _encoding_for(model, entity_id):
    for encdef in model.get("encodings", []):
        m = encdef.get("map", {})
        if entity_id in m:
            return encdef.get("kind", "log2fc_color"), encdef, m[entity_id]
    return None


def _layer_cols(model):
    """Longest-path layering: col = distance from a source node (cycles guarded)."""
    cols_hint = {}
    for e in model["entities"]:
        if "col" in e:
            cols_hint[e["id"]] = int(e["col"])
    pred = {}
    for ed in model["edges"]:
        pred.setdefault(ed["to"], []).append(ed["from"])
    colmemo, guard = {}, set()

    def colof(n):
        if n in colmemo:
            return colmemo[n]
        if n in guard:
            return 0
        guard.add(n)
        c = 0
        for p in pred.get(n, []):
            c = max(c, 1 + colof(p))
        guard.discard(n)
        colmemo[n] = c
        return c

    cols, max_auto = {}, 0
    for e in model["entities"]:
        cols[e["id"]] = cols_hint.get(e["id"], colof(e["id"]))
        max_auto = max(max_auto, cols[e["id"]])
    return cols, max_auto


def layout(model):
    """Assign coordinates to compartments, entities, and edge routes (in place)."""
    if model.get("laid_out"):
        return model
    bands_present = []
    comp_by_id = {}
    for c in model.get("compartments", []):
        band = c.get("band", "cytosol")
        if band not in BANDS:
            band = "cytosol"
        c["band"] = band
        comp_by_id[c["id"]] = c
        if band not in bands_present:
            bands_present.append(band)
    # entities without explicit compartment land in the first non-membrane band
    fallback_comp = None
    for b in BAND_ORDER:
        for c in model["compartments"]:
            if c["band"] == b and b != "membrane":
                fallback_comp = c["id"]
                break
        if fallback_comp:
            break
    for e in model["entities"]:
        if not e.get("compartment"):
            e["compartment"] = fallback_comp

    W = float(model.get("canvas", {}).get("width", CANVAS_W))
    # compartments: swimlane rects spanning the band
    for c in model["compartments"]:
        y0, y1 = BANDS[c["band"]]
        c["x"], c["y"], c["w"], c["h"] = MARGIN_X / 2, y0, W - MARGIN_X, y1 - y0

    cols, maxcol = _layer_cols(model)
    step_x = max(210.0, (W - 2 * MARGIN_X - 150.0) / max(1, maxcol + 1))
    # group entities per compartment, then per col
    by_comp = {}
    for e in model["entities"]:
        by_comp.setdefault(e["compartment"], []).append(e)
    for cid, ents in by_comp.items():
        comp = comp_by_id.get(cid)
        band = comp["band"] if comp else "cytosol"
        y0, y1 = BANDS[band]
        per_col = {}
        for e in ents:
            per_col.setdefault(cols[e["id"]], []).append(e)
        for col, group in per_col.items():
            group.sort(key=lambda z: z["id"])
            if "row" in group[0] or any("row" in g for g in group):
                group.sort(key=lambda z: z.get("row", group.index(z)))
            n = len(group)
            for i, e in enumerate(group):
                w, h = ENTITY_SIZE.get(e.get("type", "generic"), ENTITY_SIZE["generic"])
                cx = MARGIN_X + (cols[e["id"]] + 0.5) * step_x
                cx = min(max(cx, MARGIN_X + w / 2), W - MARGIN_X - w / 2)
                if e.get("type") == "receptor" and "membrane" in BANDS:
                    my0, my1 = BANDS["membrane"]
                    cy = (my0 + my1) / 2.0  # transmembrane: crosses the band
                elif n == 1:
                    cy = (y0 + y1) / 2.0
                else:
                    span = min(110.0, max(70.0, (y1 - y0 - 90.0) / max(1, n - 1)))
                    cy = (y0 + y1) / 2.0 + (i - (n - 1) / 2.0) * span
                    cy = min(max(cy, y0 + h / 2 + 12), y1 - h / 2 - 12)
                e["x"], e["y"], e["w"], e["h"] = cx - w / 2, cy - h / 2, w, h

    # --- edge routing ---------------------------------------------------------
    _route_edges(model)

    model["laid_out"] = True
    model.setdefault("canvas", {})
    model["canvas"]["width"] = W
    model["canvas"]["height"] = CANVAS_H + LEGEND_H
    return model


def _route_edges(model):
    """Compute orthogonal routes for edges that lack stored points (idempotent)."""
    comp_by_id = {c["id"]: c for c in model.get("compartments", [])}
    band_idx = {}
    for e in model["entities"]:
        comp = comp_by_id.get(e.get("compartment"))
        band_idx[e["id"]] = BAND_ORDER.index(comp["band"]) if comp else 2
    ent_by_id = {e["id"]: e for e in model["entities"]}
    out_count = {}
    for ed in model["edges"]:
        if ed.get("points"):
            continue
        if ed["from"] not in ent_by_id or ed["to"] not in ent_by_id:
            continue
        s, t = ent_by_id[ed["from"]], ent_by_id[ed["to"]]
        s, t = ent_by_id[ed["from"]], ent_by_id[ed["to"]]
        sx, sy = s["x"] + s["w"] / 2, s["y"] + s["h"] / 2
        tx, ty = t["x"] + t["w"] / 2, t["y"] + t["h"] / 2
        bdir = band_idx[ed["to"]] - band_idx[ed["from"]]
        if bdir < 0:
            exit_side, enter_side = "bottom", "bottom"   # feedback below
        elif bdir > 0:
            exit_side, enter_side = "bottom", "top"
        else:
            if abs(tx - sx) < max(s["w"], t["w"]) * 0.5 and abs(ty - sy) > 10:
                # vertically stacked within one band: route bottom -> top
                exit_side = "bottom" if ty > sy else "top"
                enter_side = "top" if ty > sy else "bottom"
            else:
                exit_side = "right" if tx >= sx else "left"
                enter_side = "left" if tx >= sx else "right"
        k = out_count.get((ed["from"], exit_side), 0)
        n_out = sum(1 for x in model["edges"] if x["from"] == ed["from"])
        out_count[(ed["from"], exit_side)] = k + 1
        off = (k - (n_out - 1) / 2.0) * 16.0

        def pt(node, side, offv=0.0):
            cx, cy = node["x"] + node["w"] / 2, node["y"] + node["h"] / 2
            if side == "top":
                return [cx + offv, node["y"]]
            if side == "bottom":
                return [cx + offv, node["y"] + node["h"]]
            if side == "left":
                return [node["x"], cy + offv]
            return [node["x"] + node["w"], cy + offv]

        p0 = pt(s, exit_side, off if exit_side in ("top", "bottom") else 0)
        p3 = pt(t, enter_side)
        if exit_side in ("bottom", "top") and bdir < 0:
            fb_y = min(CANVAS_H - 20.0, max(p0[1], p3[1]) + 55.0)
            pts = [p0, [p0[0], fb_y], [p3[0], fb_y], p3]
            ed["route"] = "feedback"
        elif exit_side in ("bottom", "top"):
            midy = (p0[1] + p3[1]) / 2.0
            pts = [p0, [p0[0], midy], [p3[0], midy], p3]
        else:
            midx = (p0[0] + p3[0]) / 2.0
            pts = [p0, [midx, p0[1]], [midx, p3[1]], p3]
        ed["points"] = [[round(a, 1), round(b, 1)] for a, b in pts]
        mx = (pts[1][0] + pts[2][0]) / 2.0
        my = (pts[1][1] + pts[2][1]) / 2.0
        ed["label_xy"] = [round(mx, 1), round(my - 8.0, 1)]


def primitives(model):
    """Flatten a laid-out model into drawing primitives.

    Returns (width, height, prims, legend) where each prim is a dict with
    kind in {rect, ellipse, polyline, text}, an "id", a "layer" in
    {compartments, edges, entities, legend} and style fields.
    """
    layout(model)
    _route_edges(model)  # route edges that lack points (e.g. after re-parse)
    W = model["canvas"]["width"]
    H = model["canvas"]["height"]
    prims = []
    for c in model.get("compartments", []):
        prims.append({
            "kind": "rect", "id": "compartment:%s" % c["id"], "layer": "compartments",
            "role": "compartment", "band": c["band"],
            "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"],
            "fill": COMPARTMENT_FILL.get(c["band"], "#f8fafc"),
            "stroke": "#94a3b8", "stroke_w": 1.2, "rounded": False, "double": False,
        })
        prims.append({
            "kind": "text", "id": "compartment-label:%s" % c["id"], "layer": "compartments",
            "role": "compartment-label", "x": c["x"] + 14, "y": c["y"] + 16,
            "text": c.get("label", c["id"]), "size": 13, "italic": False,
            "bold": True, "anchor": "start", "color": "#64748b",
        })
    for ed in model.get("edges", []):
        st = EDGE_STYLES.get(ed.get("kind", "uncertain"), EDGE_STYLES["uncertain"])
        uncertain = ed.get("evidence") == "uncertain" or ed.get("kind") == "uncertain"
        prims.append({
            "kind": "polyline", "id": "edge:%s" % ed["id"], "layer": "edges",
            "role": "edge", "ekind": ed.get("kind", "uncertain"),
            "points": ed.get("points", []),
            "stroke": EDGE_STYLES["uncertain"]["color"] if uncertain and ed.get("kind") != "uncertain" else st["color"],
            "dashed": bool(st["dashed"] or uncertain),
            "arrow": st["arrow"], "stroke_w": 2.0,
        })
        label = ed.get("label") or st["glyph"]
        if uncertain and not label:
            label = "?"
        if label:
            lx, ly = ed.get("label_xy", [0, 0])
            prims.append({
                "kind": "text", "id": "edge-label:%s" % ed["id"], "layer": "edges",
                "role": "edge-label", "x": lx, "y": ly, "text": label,
                "size": 12, "italic": False, "bold": True, "anchor": "middle",
                "color": st["color"],
            })
    for e in model.get("entities", []):
        fill = _entity_fill(model, e)
        etype = e.get("type", "generic")
        base = {
            "id": "entity:%s" % e["id"], "layer": "entities", "role": "entity",
            "etype": etype, "fill": fill, "stroke": STROKE, "stroke_w": 1.6,
            "source": model.get("sources", {}).get(e["id"], e.get("source", "")),
        }
        if etype == "small_molecule":
            prims.append(dict(base, kind="ellipse",
                              cx=e["x"] + e["w"] / 2, cy=e["y"] + e["h"] / 2,
                              rx=e["w"] / 2, ry=e["h"] / 2))
        else:
            prims.append(dict(base, kind="rect", x=e["x"], y=e["y"], w=e["w"], h=e["h"],
                              rounded=etype in ("protein", "gene", "generic"),
                              double=etype == "complex"))
        prims.append({
            "kind": "text", "id": "entity-label:%s" % e["id"], "layer": "entities",
            "role": "entity-label", "x": e["x"] + e["w"] / 2, "y": e["y"] + e["h"] / 2 + 4,
            "text": e["label"], "size": 13, "italic": etype == "gene",
            "bold": False, "anchor": "middle", "color": "#0f172a",
        })
    legend = _legend(model, W, H)
    prims.extend(legend)
    return W, H, prims, [p for p in legend]


def _legend(model, W, H):
    """Auto legend from encodings and edge kinds actually used. Strip below bands."""
    prims = []
    used_kinds = []
    for ed in model.get("edges", []):
        k = ed.get("kind", "uncertain")
        if k not in used_kinds:
            used_kinds.append(k)
    encs = model.get("encodings", [])
    if not used_kinds and not encs:
        return prims
    y0 = CANVAS_H + 14.0
    prims.append({"kind": "rect", "id": "legend:box", "layer": "legend", "role": "legend",
                  "x": MARGIN_X / 2, "y": y0 - 6, "w": W - MARGIN_X, "h": LEGEND_H - 22,
                  "fill": "#ffffff", "stroke": "#cbd5e1", "stroke_w": 1.0,
                  "rounded": True, "double": False})
    prims.append({"kind": "text", "id": "legend:title", "layer": "legend", "role": "legend",
                  "x": MARGIN_X / 2 + 12, "y": y0 + 10, "text": "图例 Legend",
                  "size": 12, "italic": False, "bold": True, "anchor": "start",
                  "color": "#0f172a"})
    x = MARGIN_X / 2 + 12.0
    y = y0 + 34.0
    for k in used_kinds:
        st = EDGE_STYLES.get(k, EDGE_STYLES["uncertain"])
        prims.append({"kind": "polyline", "id": "legend:edge:%s" % k, "layer": "legend",
                      "role": "legend", "ekind": k,
                      "points": [[x, y + 5], [x + 22, y + 5], [x + 34, y + 5]],
                      "stroke": st["color"], "dashed": st["dashed"],
                      "arrow": st["arrow"], "stroke_w": 2.0})
        prims.append({"kind": "text", "id": "legend:edge-label:%s" % k, "layer": "legend",
                      "role": "legend", "x": x + 42, "y": y + 9,
                      "text": EDGE_KIND_LABELS.get(k, k), "size": 11, "italic": False,
                      "bold": False, "anchor": "start", "color": "#334155"})
        x += 190.0
        if x > W - 260.0:
            x = MARGIN_X / 2 + 12.0
            y += 26.0
    for encdef in encs:
        if encdef.get("kind") != "log2fc_color":
            continue
        vals = list(encdef.get("map", {}).values())
        vmax = max([abs(v) for v in vals] + [1.0])
        prims.append({"kind": "text", "id": "legend:enc-label", "layer": "legend",
                      "role": "legend", "x": x, "y": y + 9,
                      "text": "%s (%s)" % (encdef.get("legend", encdef.get("field", "value")),
                                           encdef.get("source", "")),
                      "size": 11, "italic": False, "bold": False, "anchor": "start",
                      "color": "#334155"})
        x += 14.0
        steps = 5
        for i in range(steps):
            v = -vmax + 2 * vmax * i / (steps - 1)
            prims.append({"kind": "rect", "id": "legend:swatch:%d" % i, "layer": "legend",
                          "role": "legend-swatch", "x": x + 150 + i * 26, "y": y - 2,
                          "w": 26, "h": 14, "fill": _log2fc_color(v, vmax),
                          "stroke": "#94a3b8", "stroke_w": 0.6, "rounded": False,
                          "double": False, "value": round(v, 2)})
        prims.append({"kind": "text", "id": "legend:swatch-lo", "layer": "legend",
                      "role": "legend", "x": x + 150, "y": y + 24,
                      "text": "%.1f" % -vmax, "size": 9, "italic": False, "bold": False,
                      "anchor": "start", "color": "#64748b"})
        prims.append({"kind": "text", "id": "legend:swatch-hi", "layer": "legend",
                      "role": "legend", "x": x + 150 + steps * 26 - 4, "y": y + 24,
                      "text": "+%.1f" % vmax, "size": 9, "italic": False, "bold": False,
                      "anchor": "end", "color": "#64748b"})
    return prims


def main(argv=None):
    ap = argparse.ArgumentParser(description="layout a geometry model")
    ap.add_argument("--geometry", required=True)
    ap.add_argument("--out", required=True, help="laid-out model JSON")
    ap.add_argument("--primitives", help="optional: dump primitives JSON")
    args = ap.parse_args(argv)
    model = load_geometry(args.geometry)
    layout(model)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=2)
    if args.primitives:
        W, H, prims, _ = primitives(model)
        with open(args.primitives, "w", encoding="utf-8") as fh:
            json.dump({"width": W, "height": H, "primitives": prims},
                      fh, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "entities": len(model["entities"]),
                      "edges": len(model["edges"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
