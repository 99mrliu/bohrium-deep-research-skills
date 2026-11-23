#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_chart.py -- chart mode: data file (CSV/TSV/JSON) -> drawio + SVG + PNG + PDF.

Reads real data only -- never invents values. Axis labels and units come from the
data headers. Bars/points/lines are emitted as the same drawing primitives used by
the pathway pipeline, so the chart gets a native .drawio (rects for bars, ellipses
for scatter points, edges for axes/lines) and a layered SVG, while PNG/PDF are
rendered directly from the parsed data with matplotlib (graceful skip if missing).

A content_map fragment maps every visual mark back to its data cell, e.g.
  "bar:2" -> "example-data.csv row 3: log2FC = 1.90"

CLI:
  python3 build_chart.py --data FILE --kind bar|line|scatter \
      [--x COL] [--y COL] [--title T] --out-dir DIR --basename NAME \
      [--content-map-out FILE]
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import svg_write  # noqa: E402

W, H = 1000.0, 700.0
ML, MR, MT, MB = 110.0, 40.0, 70.0, 110.0  # plot margins
BAR_FILL = "#60a5fa"
PT_FILL = "#f97316"
LINE_COLOR = "#2563eb"


def load_table(path):
    """Return (headers, rows) where rows are lists of strings. '#' lines skipped."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        raw = [ln for ln in fh.read().splitlines()
               if ln.strip() and not ln.lstrip().startswith("#")]
    if not raw:
        raise ValueError("empty data file: %s" % path)
    if path.lower().endswith(".json"):
        data = json.loads("\n".join(raw))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [[str(r.get(h, "")) for h in headers] for r in data]
            return headers, rows
        raise ValueError("JSON data must be a list of objects")
    dialect = csv.Sniffer().sniff(raw[0], delimiters=",\t;")
    reader = csv.reader(raw, dialect)
    rows = list(reader)
    return rows[0], rows[1:]


def _to_float(s, where):
    try:
        return float(str(s).strip())
    except ValueError:
        raise ValueError("non-numeric value %r at %s -- refusing to invent data"
                         % (s, where))


def pick_columns(headers, rows, x_col, y_col, kind):
    def idx(name):
        if name in headers:
            return headers.index(name)
        raise ValueError("column %r not in headers %r" % (name, headers))

    numeric = []
    for j, h in enumerate(headers):
        try:
            for r in rows:
                _to_float(r[j], "column %s" % h)
            numeric.append(j)
        except ValueError:
            continue
    if y_col:
        yi = idx(y_col)
    elif numeric:
        yi = numeric[0]
    else:
        raise ValueError("no fully numeric column found for y")
    if x_col:
        xi = idx(x_col)
    elif kind == "bar":  # categorical x preferred
        nonnum = [j for j in range(len(headers)) if j not in numeric]
        xi = nonnum[0] if nonnum else (0 if yi != 0 else 1)
    else:  # line/scatter need numeric x
        cand = [j for j in numeric if j != yi]
        if not cand:
            raise ValueError("kind=%s needs a numeric x column; none found "
                             "(use --x/--y to pick columns)" % kind)
        xi = cand[0]
    if xi == yi:
        raise ValueError("x and y resolve to the same column; use --x/--y")
    return xi, yi


def chart_primitives(kind, headers, rows, xi, yi, title, data_path):
    """Build primitives + content-map fragment from parsed data."""
    xs_raw = [r[xi] for r in rows]
    ys = [_to_float(r[yi], "row %d" % (i + 2)) for i, r in enumerate(rows)]
    numeric_x = kind in ("line", "scatter")
    xs = [_to_float(v, "row %d" % (i + 2)) for i, v in enumerate(xs_raw)] \
        if numeric_x else list(range(len(rows)))
    x_label, y_label = headers[xi], headers[yi]
    pw, ph = W - ML - MR, H - MT - MB
    ymin, ymax = min(ys + [0.0]), max(ys + [0.0])
    if ymax == ymin:
        ymax = ymin + 1.0
    pad = (ymax - ymin) * 0.08
    ymin -= pad if ymin < 0 else 0
    ymax += pad

    def X(v):
        if numeric_x:
            lo, hi = min(xs), max(xs)
            span = (hi - lo) or 1.0
            return ML + (v - lo) / span * pw
        return ML + (v + 0.5) / len(xs) * pw

    def Y(v):
        return MT + ph - (v - ymin) / (ymax - ymin) * ph

    prims, cmap = [], {}
    # axes
    y0 = Y(0.0) if ymin < 0 else MT + ph
    prims.append({"kind": "polyline", "id": "chart:xaxis", "layer": "chart",
                  "role": "axis", "points": [[ML, y0], [ML + pw, y0]],
                  "stroke": "#0f172a", "dashed": False, "arrow": "none",
                  "stroke_w": 1.5})
    prims.append({"kind": "polyline", "id": "chart:yaxis", "layer": "chart",
                  "role": "axis", "points": [[ML, MT], [ML, MT + ph]],
                  "stroke": "#0f172a", "dashed": False, "arrow": "none",
                  "stroke_w": 1.5})
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        yy = Y(v)
        prims.append({"kind": "polyline", "id": "chart:ytick:%d" % i, "layer": "chart",
                      "role": "tick", "points": [[ML - 6, yy], [ML, yy]],
                      "stroke": "#0f172a", "dashed": False, "arrow": "none",
                      "stroke_w": 1.2})
        prims.append({"kind": "text", "id": "chart:ytick-label:%d" % i, "layer": "chart",
                      "role": "tick-label", "x": ML - 12, "y": yy + 3,
                      "text": "%.3g" % v, "size": 11, "italic": False, "bold": False,
                      "anchor": "end", "color": "#334155"})
    prims.append({"kind": "text", "id": "chart:title", "layer": "chart", "role": "title",
                  "x": W / 2, "y": 36, "text": title or y_label, "size": 16,
                  "italic": False, "bold": True, "anchor": "middle",
                  "color": "#0f172a"})
    prims.append({"kind": "text", "id": "chart:xlabel", "layer": "chart", "role": "axis-label",
                  "x": ML + pw / 2, "y": H - 30, "text": x_label, "size": 13,
                  "italic": False, "bold": False, "anchor": "middle",
                  "color": "#0f172a"})
    prims.append({"kind": "text", "id": "chart:ylabel", "layer": "chart", "role": "axis-label",
                  "x": 30, "y": MT + ph / 2, "text": y_label, "size": 13,
                  "italic": False, "bold": False, "anchor": "middle",
                  "color": "#0f172a"})

    src = os.path.basename(data_path)
    if kind == "bar":
        bw = pw / len(xs) * 0.62
        for i, v in enumerate(ys):
            top = Y(max(v, 0.0))
            hgt = abs(Y(v) - Y(0.0))
            bid = "bar:%d" % i
            prims.append({"kind": "rect", "id": bid, "layer": "chart", "role": "bar",
                          "x": X(i) - bw / 2, "y": top, "w": bw, "h": max(hgt, 1.0),
                          "fill": BAR_FILL, "stroke": "#1e3a8a", "stroke_w": 1.2,
                          "rounded": False, "double": False})
            cmap[bid] = "%s row %d: %s = %s" % (src, i + 2, y_label, rows[i][yi])
            lx, ly = X(i), MT + ph + 18
            prims.append({"kind": "text", "id": "chart:xtick-label:%d" % i,
                          "layer": "chart", "role": "tick-label", "x": lx, "y": ly,
                          "text": str(xs_raw[i]), "size": 11, "italic": False,
                          "bold": False, "anchor": "middle", "color": "#334155"})
    elif kind == "scatter":
        for i, v in enumerate(ys):
            pid = "point:%d" % i
            prims.append({"kind": "ellipse", "id": pid, "layer": "chart", "role": "point",
                          "cx": X(xs[i]), "cy": Y(v), "rx": 6, "ry": 6,
                          "fill": PT_FILL, "stroke": "#7c2d12", "stroke_w": 1.0})
            cmap[pid] = "%s row %d: (%s = %s, %s = %s)" % (
                src, i + 2, x_label, rows[i][xi], y_label, rows[i][yi])
    else:  # line
        pts = [[X(xs[i]), Y(ys[i])] for i in range(len(ys))]
        prims.append({"kind": "polyline", "id": "series:0", "layer": "chart",
                      "role": "series", "points": pts, "stroke": LINE_COLOR,
                      "dashed": False, "arrow": "none", "stroke_w": 2.0})
        for i, v in enumerate(ys):
            pid = "point:%d" % i
            prims.append({"kind": "ellipse", "id": pid, "layer": "chart", "role": "point",
                          "cx": pts[i][0], "cy": pts[i][1], "rx": 5, "ry": 5,
                          "fill": "#ffffff", "stroke": LINE_COLOR, "stroke_w": 1.5})
            cmap[pid] = "%s row %d: (%s = %s, %s = %s)" % (
                src, i + 2, x_label, rows[i][xi], y_label, rows[i][yi])
    return prims, cmap


def prims_to_cells(prims):
    """Map chart primitives to mxCells for the .drawio emission."""
    cells = []
    for p in prims:
        if p["kind"] == "rect":
            cells.append({"id": p["id"], "value": "", "vertex": True, "parent": "1",
                          "style": "rounded=0;whiteSpace=wrap;html=1;fillColor=%s;"
                                   "strokeColor=%s;" % (p.get("fill", "#ffffff"),
                                                        p.get("stroke", "#000000")),
                          "geom": {"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"]},
                          "data": {"data-role": p.get("role", "")}})
        elif p["kind"] == "ellipse":
            cells.append({"id": p["id"], "value": "", "vertex": True, "parent": "1",
                          "style": "ellipse;whiteSpace=wrap;html=1;fillColor=%s;"
                                   "strokeColor=%s;" % (p.get("fill", "#ffffff"),
                                                        p.get("stroke", "#000000")),
                          "geom": {"x": p["cx"] - p["rx"], "y": p["cy"] - p["ry"],
                                   "w": p["rx"] * 2, "h": p["ry"] * 2},
                          "data": {"data-role": p.get("role", "")}})
        elif p["kind"] == "polyline":
            style = ("endArrow=none;html=1;rounded=0;strokeColor=%s;strokeWidth=%s;"
                     % (p.get("stroke", "#000000"), int(p.get("stroke_w", 1.5))))
            if p.get("dashed"):
                style += "dashed=1;"
            pts = p["points"]
            cells.append({"id": p["id"], "value": "", "edge": True, "parent": "1",
                          "style": style,
                          "points": pts[1:-1] if len(pts) > 2 else [],
                          "geom_points": pts,
                          "data": {"data-role": p.get("role", "")}})
        elif p["kind"] == "text":
            style = ("text;html=1;align=%s;fontSize=%d;fontColor=%s;"
                     % ({"start": "left", "middle": "center", "end": "right"}.get(
                         p.get("anchor", "middle"), "center"),
                        int(p.get("size", 12)), p.get("color", "#000000")))
            if p.get("bold"):
                style += "fontStyle=1;"
            w = max(40, len(str(p.get("text", ""))) * p.get("size", 12) * 0.6)
            cells.append({"id": p["id"], "value": str(p.get("text", "")),
                          "vertex": True, "parent": "1", "style": style,
                          "geom": {"x": p["x"] - w / 2, "y": p["y"] - 9, "w": w, "h": 18},
                          "data": {"data-role": p.get("role", "")}})
    return cells


def mpl_chart(kind, x_vals, y_vals, x_label, y_label, title, png_path, pdf_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False, "matplotlib not installed; PNG/PDF skipped"
    matplotlib.rcParams["pdf.fonttype"] = 42
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    if kind == "bar":
        ax.bar(x_vals, y_vals, color=BAR_FILL, edgecolor="#1e3a8a")
    elif kind == "scatter":
        ax.scatter(x_vals, y_vals, color=PT_FILL, edgecolor="#7c2d12", zorder=3)
    else:
        ax.plot(x_vals, y_vals, marker="o", color=LINE_COLOR,
                markerfacecolor="#ffffff")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if title:
        ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(png_path, dpi=300)
    fig.savefig(pdf_path)
    plt.close(fig)
    return True, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description="build chart artifacts from real data")
    ap.add_argument("--data", required=True)
    ap.add_argument("--kind", required=True, choices=["bar", "line", "scatter"])
    ap.add_argument("--x")
    ap.add_argument("--y")
    ap.add_argument("--title", default="")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--basename", required=True)
    ap.add_argument("--content-map-out")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)

    try:
        headers, rows = load_table(args.data)
        xi, yi = pick_columns(headers, rows, args.x, args.y, args.kind)
        prims, cmap = chart_primitives(args.kind, headers, rows, xi, yi,
                                       args.title, args.data)
    except (ValueError, OSError, csv.Error) as exc:
        print(json.dumps({"status": "failed",
                          "reason": "data error: %s" % exc}, ensure_ascii=False))
        return 1
    base = os.path.join(args.out_dir, args.basename)

    svg_write.write_primitives(base + ".svg", prims, W, H,
                               metadata={"chart": args.kind,
                                         "data": os.path.basename(args.data),
                                         "x": headers[xi], "y": headers[yi]})
    cells = prims_to_cells(prims)
    # attach absolute endpoints for standalone polylines
    for cell, p in zip([c for c in cells if c.get("edge")],
                       [p for p in prims if p["kind"] == "polyline"]):
        pts = p["points"]
        cell["points"] = pts[1:-1] if len(pts) > 2 else []
        cell["abs_endpoints"] = (pts[0], pts[-1])
    _emit_chart_drawio(base + ".drawio", cells)

    xs_raw = [r[xi] for r in rows]
    ys = [float(r[yi]) for r in rows]
    x_vals = xs_raw if args.kind == "bar" else [float(v) for v in xs_raw]
    mpl_ok, mpl_msg = mpl_chart(args.kind, x_vals, ys, headers[xi], headers[yi],
                                args.title, base + ".png", base + ".pdf")
    if args.content_map_out:
        with open(args.content_map_out, "w", encoding="utf-8") as fh:
            json.dump({"chart:%s" % args.basename: cmap}, fh,
                      ensure_ascii=False, indent=2)
    artifacts = [base + ext for ext in (".drawio", ".svg")]
    if mpl_ok:
        artifacts += [base + ".png", base + ".pdf"]
    print(json.dumps({"status": "ok" if mpl_ok else "partial",
                      "matplotlib": mpl_msg, "artifacts": artifacts,
                      "marks": len(cmap)}, ensure_ascii=False, indent=2))
    return 0


def _emit_chart_drawio(path, cells):
    """Chart drawio: text/rect/ellipse vertices + absolute-coordinate edges."""
    import xml.etree.ElementTree as ET
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net",
                                   "agent": "drawio-dual-source/1.0",
                                   "type": "device", "version": "24.0.0"})
    diagram = ET.SubElement(mxfile, "diagram", {"name": "chart", "id": "chart-1"})
    model_el = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1000", "dy": "700", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": "1000", "pageHeight": "700",
        "math": "0", "shadow": "0"})
    root = ET.SubElement(model_el, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for cell in cells:
        a = {"id": cell["id"], "value": cell.get("value", ""),
             "style": cell.get("style", ""), "parent": "1"}
        a.update({k: str(v) for k, v in cell.get("data", {}).items()})
        if cell.get("vertex"):
            a["vertex"] = "1"
            el = ET.SubElement(root, "mxCell", a)
            g = cell["geom"]
            ET.SubElement(el, "mxGeometry", {
                "x": "%.1f" % g["x"], "y": "%.1f" % g["y"],
                "width": "%.1f" % g["w"], "height": "%.1f" % g["h"],
                "as": "geometry"})
        else:
            a["edge"] = "1"
            el = ET.SubElement(root, "mxCell", a)
            gel = ET.SubElement(el, "mxGeometry", {"relative": "1", "as": "geometry"})
            if cell.get("abs_endpoints"):
                (sx, sy), (tx, ty) = cell["abs_endpoints"]
                ET.SubElement(gel, "mxPoint", {"x": "%.1f" % sx, "y": "%.1f" % sy,
                                               "as": "sourcePoint"})
                ET.SubElement(gel, "mxPoint", {"x": "%.1f" % tx, "y": "%.1f" % ty,
                                               "as": "targetPoint"})
            if cell.get("points"):
                arr = ET.SubElement(gel, "Array", {"as": "points"})
                for px, py in cell["points"]:
                    ET.SubElement(arr, "mxPoint", {"x": "%.1f" % px,
                                                   "y": "%.1f" % py})
    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="  ")
    with open(path, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)
    return path


if __name__ == "__main__":
    sys.exit(main())
