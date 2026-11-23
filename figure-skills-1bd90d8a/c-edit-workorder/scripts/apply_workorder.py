#!/usr/bin/env python3
"""apply_workorder.py - apply a declarative edit workorder to a layered SVG.

PURE STDLIB (xml.etree + re + json + math + datetime).  No third-party deps.

A workorder is {"ops": [op, ...]}; each op is applied in sequence, geometry is
re-derived from the bound source values through figmap.json (never
hand-computed pixels), and every op is appended to the change log with
old/new/source_ref.  Value-changing ops (update_value) REQUIRE source_ref,
unless explicitly marked {"manual": true, "reason": "..."} - then they are
applied but conspicuously logged as 人工修改 (manual edit).  Without either,
the op is REJECTED.

Ops (see references/workorder_schema.md for full semantics):
  update_value     {series, index|key, value, x?, source_ref?, manual?, reason?}
  restyle_series   {series, color?, linestyle?, marker?}
  relabel          {target_id, new_text}
  move_annotation  {target_id, dx, dy}
  add_annotation   {id, x_data, y_data, text, source_ref?, manual?, reason?}
  set_axis_range   {axis: "x"|"y", min, max}
  highlight_region {x0, x1, label?}

Unknown targets -> op status "failed" (with reason), remaining ops continue.
Exit code: 0 normally; 2 if ops were attempted but zero applied.

Usage:
  python3 apply_workorder.py FIGURE.svg workorder.json \
      --figmap figmap.json --out-svg /app/output/figure.svg \
      --log /app/output/change_log.json
"""
import argparse
import copy
import datetime
import json
import math
import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
for pfx, uri in [("", SVG_NS), ("xlink", XLINK_NS),
                 ("dc", "http://purl.org/dc/elements/1.1/"),
                 ("cc", "http://creativecommons.org/ns#"),
                 ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
                 ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"),
                 ("inkscape", "http://www.inkscape.org/namespaces/inkscape")]:
    try:
        ET.register_namespace(pfx, uri)
    except ValueError:
        pass

NUM = r"-?\d+\.?\d*(?:[eE][-+]?\d+)?"
DASHES = {"-": None, "solid": None, "--": "6,4", "dashed": "6,4",
          ":": "2,3", "dotted": "2,3", "-.": "6,3,2,3", "dashdot": "6,3,2,3"}


def local(tag):
    return tag.split("}")[-1]


def floats(s):
    return [float(t) for t in re.findall(NUM, s or "")]


def find_by_id(root, eid):
    for el in root.iter():
        if el.get("id") == eid:
            return el
    return None


def get_style(el):
    d = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def set_style(el, d):
    el.set("style", "; ".join("%s: %s" % (k, v) for k, v in d.items()))


def fmt(v):
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return "%g" % v


# ---------------------------------------------------------------- geometry --
def path_segments(d):
    """Split a path d into [(cmd, [numbers]), ...]."""
    segs = []
    for m in re.finditer(r"([A-Za-z])([^A-Za-z]*)", d or ""):
        segs.append([m.group(1), floats(m.group(2))])
    return segs


def rewrite_bar(path_el, y_val_px, y_base_px):
    nums = floats(path_el.get("d"))
    xs = nums[0::2]
    if len(xs) < 2:
        return False
    x0, x1 = min(xs), max(xs)
    y_hi, y_lo = min(y_val_px, y_base_px), max(y_val_px, y_base_px)
    path_el.set("d", "M %.4f %.4f L %.4f %.4f L %.4f %.4f L %.4f %.4f z"
                % (x0, y_hi, x1, y_hi, x1, y_lo, x0, y_lo))
    return True


def rewrite_line_vertex(path_el, index, new_x=None, new_y=None):
    segs = path_segments(path_el.get("d"))
    vi = -1
    out = []
    for cmd, nums in segs:
        if cmd in ("M", "L") and len(nums) >= 2:
            vi += 1
            if vi == index:
                if new_x is not None:
                    nums[0] = new_x
                if new_y is not None:
                    nums[1] = new_y
        elif cmd in ("m", "l", "c", "q"):
            return False  # relative/curve paths unsupported
        out.append(cmd + " " + " ".join("%.4f" % n for n in nums))
    if vi < index:
        return False
    path_el.set("d", "\n".join(out) + "\n")
    return True


def scatter_points(group):
    pts = [u for u in group.iter()
           if local(u.tag) == "use" and u.get("x") is not None]
    if pts:
        return pts, "use"
    paths = [p for p in group if local(p.tag) == "path"]
    return paths, "path"


def shift_path_y(path_el, dy):
    segs = path_segments(path_el.get("d"))
    out = []
    for cmd, nums in segs:
        for i in range(1, len(nums), 2):
            nums[i] += dy
        out.append(cmd + " " + " ".join("%.4f" % n for n in nums))
    path_el.set("d", "\n".join(out) + "\n")


def shift_path_x(path_el, dx):
    segs = path_segments(path_el.get("d"))
    out = []
    for cmd, nums in segs:
        for i in range(0, len(nums), 2):
            nums[i] += dx
        out.append(cmd + " " + " ".join("%.4f" % n for n in nums))
    path_el.set("d", "\n".join(out) + "\n")


def first_text(el):
    if local(el.tag) == "text":
        return el
    for sub in el.iter():
        if local(sub.tag) == "text":
            return sub
    return None


def replace_text(tel, new_text):
    old = "".join(tel.itertext())
    for child in list(tel):
        tel.remove(child)
    tel.text = new_text
    return old


def move_element(el, dx, dy):
    tag = local(el.tag)
    if el.get("x") is not None and el.get("y") is not None:
        el.set("x", "%.4f" % (float(el.get("x")) + dx))
        el.set("y", "%.4f" % (float(el.get("y")) + dy))
        tr = el.get("transform")
        if tr and "rotate" in tr:
            def fix(m):
                return "rotate(%s %.4f %.4f)" % (
                    m.group(1), float(m.group(2)) + dx, float(m.group(3)) + dy)
            el.set("transform", re.sub(
                r"rotate\((%s)\s+(%s)\s+(%s)\)" % (NUM, NUM, NUM), fix, tr))
        return True
    tr = el.get("transform") or ""
    el.set("transform", (tr + " translate(%.4f %.4f)" % (dx, dy)).strip())
    return True


# --------------------------------------------------------------- transforms --
class Figmap:
    def __init__(self, fm):
        self.fm = fm or {}
        ax = self.fm.get("axes", {})
        self.y = ax.get("y") or {}
        self.x = ax.get("x") or {}
        self.series = self.fm.get("series") or {}
        self.plot = self.fm.get("plot_area") or {}

    def y2px(self, v):
        return self.y["a"] * v + self.y["b"]

    def x2px(self, v):
        if self.x.get("kind") == "category":
            return self.x.get("centers", {}).get(str(v))
        return self.x["a"] * v + self.x["b"]


# --------------------------------------------------------------------- ops --
def op_update_value(root, fm, op):
    if fm is None or not fm.series:
        return "failed", None, None, ("unbound - no figmap data binding; "
                                      "manual confirmation required")
    name = op.get("series")
    rec = fm.series.get(name)
    if rec is None:
        return "failed", None, None, "unknown series: %s" % name
    if op.get("key") is not None:
        key = str(op["key"])
        if key not in [str(v) for v in rec["x"]]:
            return "failed", None, None, "unknown key %s in series %s" % (key, name)
        idx = [str(v) for v in rec["x"]].index(key)
    else:
        idx = int(op.get("index", -1))
    if idx < 0 or idx >= len(rec["y"]):
        return "failed", None, None, "index %s out of range" % idx

    has_src = bool(op.get("source_ref"))
    manual = bool(op.get("manual")) and bool(op.get("reason"))
    if not has_src and not manual:
        return "rejected", None, None, ("update_value requires source_ref "
                                        "(or manual:true + reason)")

    old_val = rec["y"][idx]
    new_val = float(op["value"])
    kind = rec["kind"]
    y_px = fm.y2px(new_val)
    ok = False
    if kind == "bar":
        el = find_by_id(root, "series/%s/bar-%d" % (name, idx))
        if el is None:
            return "failed", None, None, "element series/%s/bar-%d not found" % (name, idx)
        path = el.find("{%s}path" % SVG_NS)
        if path is None:
            path = el.find("path")
        base_px = fm.y2px(rec.get("baseline", 0.0))
        ok = path is not None and rewrite_bar(path, y_px, base_px)
    elif kind == "line":
        el = find_by_id(root, "series/%s/line" % name)
        if el is None:
            return "failed", None, None, "element series/%s/line not found" % name
        path = el.find("{%s}path" % SVG_NS)
        if path is None:
            path = el.find("path")
        new_x = None
        if op.get("x") is not None:
            if fm.x.get("kind") != "linear":
                return "failed", None, None, "x update needs linear x axis"
            new_x = fm.x2px(float(op["x"]))
        ok = path is not None and rewrite_line_vertex(path, idx, new_x, y_px)
        if ok:
            # markers are separate <use> glyphs; keep them glued to the vertex
            markers = [u for u in el.iter()
                       if local(u.tag) == "use" and u.get("x") is not None]
            if idx < len(markers):
                markers[idx].set("y", "%.4f" % y_px)
                if new_x is not None:
                    markers[idx].set("x", "%.4f" % new_x)
    elif kind == "scatter":
        el = find_by_id(root, "series/%s/pts" % name)
        if el is None:
            return "failed", None, None, "element series/%s/pts not found" % name
        pts, mode = scatter_points(el)
        if idx >= len(pts):
            return "failed", None, None, "scatter point %d not found" % idx
        if mode == "use":
            pts[idx].set("y", "%.4f" % y_px)
            if op.get("x") is not None:
                if fm.x.get("kind") != "linear":
                    return "failed", None, None, "x update needs linear x axis"
                pts[idx].set("x", "%.4f" % fm.x2px(float(op["x"])))
        else:
            old_py = fm.y2px(old_val)
            shift_path_y(pts[idx], y_px - old_py)
        ok = True
    else:
        return "failed", None, None, "unsupported series kind %s" % kind
    if not ok:
        return "failed", None, None, "geometry rewrite failed"
    rec["y"][idx] = new_val
    if op.get("x") is not None and fm.x.get("kind") == "linear":
        rec["x"][idx] = float(op["x"])
    detail = None
    if rec.get("yerr"):
        detail = "warning: yerr geometry NOT re-derived; verify error bars"
    return "applied", old_val, new_val, detail


def op_restyle_series(root, fm, op):
    name = op.get("series")
    targets = [el for el in root.iter()
               if el.get("id") == "series/%s" % name
               or (el.get("id") or "").startswith("series/%s/" % name)]
    if not targets:
        return "failed", None, None, "unknown series group: %s" % name
    old = {"color": set(), "dash": set()}
    changed = 0
    for g in targets:
        for el in g.iter():
            if local(el.tag) not in ("path", "use", "rect", "circle",
                                     "polygon", "polyline", "line"):
                continue
            st = get_style(el)
            if not st:
                continue
            if op.get("color"):
                for prop in ("fill", "stroke"):
                    if prop in st and st[prop] != "none":
                        old["color"].add(st[prop])
                        st[prop] = op["color"]
            ls = op.get("linestyle")
            if ls and "stroke" in st and st["stroke"] != "none":
                old["dash"].add(st.get("stroke-dasharray", "none"))
                dash = DASHES.get(ls, ls if re.match(r"^[\d, ]+$", ls) else None)
                if dash is None:
                    st.pop("stroke-dasharray", None)
                else:
                    st["stroke-dasharray"] = dash
            set_style(el, st)
            changed += 1
    detail = None
    if op.get("marker"):
        detail = "warning: marker glyph restyle is not supported; ignored"
    if changed == 0:
        return "failed", None, None, "no styleable elements under series/%s" % name
    return "applied", {"colors": sorted(old["color"]),
                       "dashes": sorted(old["dash"])}, \
        {"color": op.get("color"), "linestyle": op.get("linestyle")}, detail


def op_relabel(root, fm, op):
    el = find_by_id(root, op.get("target_id", ""))
    if el is None:
        return "failed", None, None, "unknown target_id: %s" % op.get("target_id")
    tel = first_text(el)
    if tel is None:
        return "failed", None, None, "target %s has no <text>" % op.get("target_id")
    old = replace_text(tel, str(op.get("new_text", "")))
    return "applied", old, op.get("new_text"), None


def op_move_annotation(root, fm, op):
    el = find_by_id(root, op.get("target_id", ""))
    if el is None:
        return "failed", None, None, "unknown target_id: %s" % op.get("target_id")
    dx, dy = float(op.get("dx", 0)), float(op.get("dy", 0))
    move_element(el, dx, dy)
    return "applied", {"dx": 0, "dy": 0}, {"dx": dx, "dy": dy}, None


def find_axes_group(root):
    for eid in ("axes", "axes_1", "layer/axes"):
        el = find_by_id(root, eid)
        if el is not None:
            return el
    return root


def op_add_annotation(root, fm, op):
    if fm is None:
        return "failed", None, None, "unbound - add_annotation needs figmap"
    aid = op.get("id", "ann")
    if find_by_id(root, "annotation/%s" % aid) is not None:
        return "failed", None, None, "annotation/%s already exists" % aid
    try:
        px = fm.x2px(op["x_data"])
        py = fm.y2px(float(op["y_data"]))
    except (KeyError, TypeError):
        return "failed", None, None, "cannot map data coords through figmap"
    if px is None:
        return "failed", None, None, "unknown x category: %s" % op.get("x_data")
    ldx, ldy = float(op.get("leader_dx", 10)), float(op.get("leader_dy", -14))
    g = ET.Element("{%s}g" % SVG_NS, {"id": "annotation/%s" % aid})
    line = ET.SubElement(g, "{%s}line" % SVG_NS, {
        "x1": "%.4f" % px, "y1": "%.4f" % py,
        "x2": "%.4f" % (px + ldx), "y2": "%.4f" % (py + ldy),
        "style": "stroke: #555555; stroke-width: 0.8"})
    tel = ET.SubElement(g, "{%s}text" % SVG_NS, {
        "x": "%.4f" % (px + ldx + 2), "y": "%.4f" % (py + ldy),
        "style": "font-size: 7px; font-family: sans-serif; fill: #111111"})
    tel.text = str(op.get("text", ""))
    find_axes_group(root).append(g)
    detail = None
    if not op.get("source_ref") and not (op.get("manual") and op.get("reason")):
        detail = "warning: annotation added without source_ref/manual reason"
    return "applied", None, {"id": "annotation/%s" % aid,
                             "px": [px, py], "text": op.get("text")}, detail


def _rescale_series_geometry(root, fm, name, rec):
    """Rewrite every bound glyph of a series from stored values+transform."""
    kind = rec["kind"]
    if kind == "bar":
        if fm.x.get("kind") == "linear":
            return False, "bar x-rescale on linear axis unsupported"
        base_px = fm.y2px(rec.get("baseline", 0.0))
        for i, v in enumerate(rec["y"]):
            el = find_by_id(root, "series/%s/bar-%d" % (name, i))
            if el is None:
                continue
            path = el.find("{%s}path" % SVG_NS)
            if path is None:
                path = el.find("path")
            if path is not None:
                rewrite_bar(path, fm.y2px(v), base_px)
    elif kind == "line":
        el = find_by_id(root, "series/%s/line" % name)
        path = el.find("{%s}path" % SVG_NS) if el is not None else None
        if path is None:
            return False, "line path missing"
        markers = [u for u in el.iter()
                   if local(u.tag) == "use" and u.get("x") is not None]
        for i, v in enumerate(rec["y"]):
            nx = fm.x2px(rec["x"][i]) if fm.x.get("kind") == "linear" else None
            ny = fm.y2px(v)
            rewrite_line_vertex(path, i, nx, ny)
            if i < len(markers):
                markers[i].set("y", "%.4f" % ny)
                if nx is not None:
                    markers[i].set("x", "%.4f" % nx)
    elif kind == "scatter":
        el = find_by_id(root, "series/%s/pts" % name)
        if el is None:
            return False, "scatter group missing"
        pts, mode = scatter_points(el)
        for i, v in enumerate(rec["y"]):
            if i >= len(pts):
                break
            if mode == "use":
                pts[i].set("y", "%.4f" % fm.y2px(v))
                if fm.x.get("kind") == "linear":
                    pts[i].set("x", "%.4f" % fm.x2px(rec["x"][i]))
            else:
                # re-center path on the new point
                nums = floats(pts[i].get("d"))
                if len(nums) >= 2:
                    cx = sum(nums[0::2]) / (len(nums) // 2)
                    cy = sum(nums[1::2]) / (len(nums) // 2)
                    shift_path_y(pts[i], fm.y2px(v) - cy)
                    if fm.x.get("kind") == "linear":
                        shift_path_x(pts[i], fm.x2px(rec["x"][i]) - cx)
    return True, None


def op_set_axis_range(root, fm, op):
    if fm is None:
        return "failed", None, None, "unbound - set_axis_range needs figmap"
    axis = op.get("axis")
    if axis not in ("x", "y"):
        return "failed", None, None, "axis must be x or y"
    lo, hi = float(op["min"]), float(op["max"])
    if hi <= lo:
        return "failed", None, None, "max must exceed min"
    spec = fm.y if axis == "y" else fm.x
    if spec.get("kind") != "linear":
        return "failed", None, None, "%s axis is categorical" % axis
    old = {"min": spec.get("min"), "max": spec.get("max")}
    if axis == "y":
        yb, yt = fm.plot.get("y_bottom_px"), fm.plot.get("y_top_px")
        if yb is None or yt is None:
            return "failed", None, None, "figmap lacks plot_area y bounds"
        a = (yt - yb) / (hi - lo)
        spec["a"], spec["b"] = a, yb - a * lo
    else:
        xl, xr = fm.plot.get("x_left_px"), fm.plot.get("x_right_px")
        if xl is None or xr is None:
            return "failed", None, None, "figmap lacks plot_area x bounds"
        a = (xr - xl) / (hi - lo)
        spec["a"], spec["b"] = a, xl - a * lo
    spec["min"], spec["max"] = lo, hi
    for name, rec in fm.series.items():
        ok, why = _rescale_series_geometry(root, fm, name, rec)
        if not ok:
            return "failed", old, None, "rescale of series %s failed: %s" % (name, why)
    # retick: reuse existing tick groups, evenly spaced new values
    groups = []
    for el in root.iter():
        m = re.match(r"^%stick_(\d+)$" % axis, el.get("id") or "")
        if m:
            tel = first_text(el)
            if tel is not None:
                pos = float(tel.get("y" if axis == "y" else "x") or 0)
                groups.append((pos, el, tel))
    n = len(groups)
    if n >= 2:
        groups.sort(key=lambda t: t[0], reverse=(axis == "y"))
        vals = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
        if axis == "y":
            vals = vals[::-1]  # highest value at smallest svg y
        for (pos, g, tel), v in zip(groups, vals):
            new_px = fm.y2px(v) if axis == "y" else fm.x2px(v)
            delta = new_px - pos
            replace_text(tel, fmt(v))
            move_element(tel, delta if axis == "x" else 0,
                         0 if axis == "x" else delta)
            for use in g.iter():
                if local(use.tag) == "use" and use.get("y") is not None \
                        and use is not tel:
                    move_element(use, delta if axis == "x" else 0,
                                 0 if axis == "x" else delta)
    fm.fm.setdefault("axes", {})[axis] = spec
    return "applied", old, {"min": lo, "max": hi, "ticks_rewritten": n}, None


def op_highlight_region(root, fm, op):
    if fm is None:
        return "failed", None, None, "unbound - highlight_region needs figmap"
    try:
        p0 = fm.x2px(op["x0"])
        p1 = fm.x2px(op["x1"])
    except (KeyError, TypeError):
        return "failed", None, None, "cannot map x0/x1 through figmap"
    if p0 is None or p1 is None:
        return "failed", None, None, "unknown x value/category in x0/x1"
    x0, x1 = min(p0, p1), max(p0, p1)
    y0 = fm.plot.get("y_top_px", 0.0)
    y1 = fm.plot.get("y_bottom_px", fm.fm.get("canvas", {}).get("height_px", 100))
    hid = op.get("id", "highlight-%d" % int(abs(x0 * 7 + x1) % 10000))
    g = ET.Element("{%s}g" % SVG_NS, {"id": "annotation/%s" % hid})
    ET.SubElement(g, "{%s}rect" % SVG_NS, {
        "x": "%.4f" % x0, "y": "%.4f" % y0,
        "width": "%.4f" % (x1 - x0), "height": "%.4f" % (y1 - y0),
        "style": "fill: #ffe9a8; fill-opacity: 0.35; stroke: none"})
    if op.get("label"):
        tel = ET.SubElement(g, "{%s}text" % SVG_NS, {
            "x": "%.4f" % ((x0 + x1) / 2), "y": "%.4f" % (y0 + 8),
            "style": "font-size: 6px; font-family: sans-serif; "
                     "text-anchor: middle; fill: #6b5b00"})
        tel.text = str(op["label"])
    axes = find_axes_group(root)
    axes.insert(0, g)  # behind everything else in the axes
    return "applied", None, {"id": "annotation/%s" % hid,
                             "x_px": [x0, x1]}, None


OPS = {
    "update_value": op_update_value,
    "restyle_series": op_restyle_series,
    "relabel": op_relabel,
    "move_annotation": op_move_annotation,
    "add_annotation": op_add_annotation,
    "set_axis_range": op_set_axis_range,
    "highlight_region": op_highlight_region,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg")
    ap.add_argument("workorder")
    ap.add_argument("--figmap", default=None)
    ap.add_argument("--out-svg", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    with open(args.workorder, encoding="utf-8") as fh:
        workorder = json.load(fh)
    ops = workorder.get("ops", [])
    fm = None
    if args.figmap:
        try:
            with open(args.figmap, encoding="utf-8") as fh:
                fm = Figmap(json.load(fh))
        except (OSError, json.JSONDecodeError) as exc:
            print("WARNING: figmap unreadable (%s); value ops will be unbound"
                  % exc, file=sys.stderr)

    try:
        tree = ET.parse(args.svg)
    except ET.ParseError as exc:
        print("ERROR: cannot parse SVG: %s" % exc, file=sys.stderr)
        sys.exit(3)
    root = tree.getroot()

    log = []
    n_applied = n_rejected = n_failed = 0
    for seq, op in enumerate(ops, 1):
        name = op.get("op")
        fn = OPS.get(name)
        entry = {"seq": seq,
                 "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "op": name, "op_args": {k: v for k, v in op.items()
                                         if k != "op"},
                 "target": op.get("series") or op.get("target_id")
                 or op.get("id") or op.get("axis"),
                 "source_ref": op.get("source_ref"),
                 "manual_reason": op.get("reason") if op.get("manual") else None}
        if fn is None:
            entry.update(status="failed", old=None, new=None,
                         detail="unknown op: %s" % name)
            n_failed += 1
        else:
            try:
                status, old, new, detail = fn(root, fm, copy.deepcopy(op))
            except Exception as exc:  # never let one op kill the batch
                status, old, new, detail = "failed", None, None, \
                    "exception: %s: %s" % (type(exc).__name__, exc)
            entry.update(status=status, old=old, new=new, detail=detail)
            if status == "applied":
                n_applied += 1
                if op.get("manual"):
                    entry["detail"] = (detail or "") + \
                        " [人工修改 manual edit: %s]" % op.get("reason")
            elif status == "rejected":
                n_rejected += 1
            else:
                n_failed += 1
        log.append(entry)
        print("op %d %-16s -> %s%s" % (seq, name, entry["status"],
              (": %s" % entry["detail"]) if entry.get("detail") else ""))

    tree.write(args.out_svg, encoding="utf-8", xml_declaration=True)
    if fm is not None and args.figmap:
        with open(args.figmap, "w", encoding="utf-8") as fh:
            json.dump(fm.fm, fh, ensure_ascii=False, indent=2)
    summary = {"svg_in": args.svg, "svg_out": args.out_svg,
               "figmap_used": bool(fm), "ops_total": len(ops),
               "applied": n_applied, "rejected": n_rejected,
               "failed": n_failed}
    with open(args.log, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "change_log": log}, fh,
                  ensure_ascii=False, indent=2)
    print("applied=%d rejected=%d failed=%d -> %s (log: %s)"
          % (n_applied, n_rejected, n_failed, args.out_svg, args.log))
    if ops and n_applied == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
