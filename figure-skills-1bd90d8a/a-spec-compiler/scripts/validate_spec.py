#!/usr/bin/env python3
"""validate_spec.py - stdlib-only validator for figure.spec.json (fig-spec-compiler).

Checks: JSON parse, required keys, unknown keys, types, provenance presence,
unit consistency, label length, CJK risk, value sanity (NaN / magnitude span).

Exit code: 0 normally; with --strict, 1 when errors are present.
A JSON report is always written when --report is given.

Usage:
    python3 validate_spec.py figure.spec.json [--report REPORT.json] [--strict]
"""
import argparse
import json
import math
import os
import sys

VERSION = "1.0.0"

TOP_KEYS = {"version", "case_id", "title", "canvas", "mode", "layout",
            "chart", "panels", "diagram"}
CANVAS_KEYS = {"width_mm", "height_mm", "background"}
AXIS_KEYS = {"label", "unit", "scale", "min", "max", "ticks"}
PANEL_KEYS = {"type", "title", "axes", "series", "annotations", "legend"}
SERIES_KEYS = {"name", "glyph", "marker", "color", "unit", "error_meaning",
               "data", "derived", "manual", "uncertain"}
DATA_KEYS = {"source", "values", "source_locator"}
SOURCE_KEYS = {"path", "format", "column_x", "column_y", "column_yerr", "rows"}
ANNOT_KEYS = {"text", "x", "y", "data_coords", "anchor", "color",
              "source_locator", "derived", "manual", "uncertain"}
DIAGRAM_KEYS = {"title", "compartments", "nodes", "edges", "legend"}
NODE_KEYS = {"id", "shape", "x", "y", "w", "h", "label", "fill",
             "source_locator", "derived", "manual", "uncertain", "comment"}
EDGE_KEYS = {"from", "to", "style", "label", "route",
             "source_locator", "derived", "manual", "uncertain"}
COMP_KEYS = {"id", "x", "y", "w", "h", "label", "fill", "manual"}

CHART_TYPES = {"grouped_bar", "line", "scatter"}
GLYPHS = {"bar", "line", "marker"}
MARKERS = {"circle", "square", "triangle", "none"}
SHAPES = {"rounded_rect", "ellipse", "cylinder", "diamond"}
EDGE_STYLES = {"arrow", "blunt", "tbar", "dashed"}
SCALES = {"linear", "log", "categorical"}

MAX_LABEL_CHARS = 60
MISSING_TOKENS = {"", "nan", "na", "n/a", "null", "none", "-"}


class Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.notes = []

    def error(self, where, msg):
        self.errors.append({"where": where, "message": msg})

    def warn(self, where, msg):
        self.warnings.append({"where": where, "message": msg})

    def note(self, where, msg):
        self.notes.append({"where": where, "message": msg})


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_unknown(obj, allowed, where, rep):
    for k in obj:
        if k not in allowed:
            rep.warn(where, "unknown key %r (ignored by compiler)" % k)


def has_provenance(elem, where, rep, kind):
    """kind in {'series','node','edge','annotation'}."""
    if elem.get("derived") or elem.get("manual") is True:
        return
    if kind == "series":
        data = elem.get("data") or {}
        if isinstance(data, dict) and (data.get("source") or data.get("source_locator")):
            return
    else:
        if elem.get("source_locator"):
            return
    rep.error(where, "%s has no provenance: add data.source, source_locator, "
              "'derived' or 'manual': true" % kind)


def check_label(where, text, rep):
    if not isinstance(text, str):
        return
    if len(text) > MAX_LABEL_CHARS:
        rep.warn(where, "label is %d chars (> %d); compiler will wrap, "
                 "consider shortening" % (len(text), MAX_LABEL_CHARS))
    if any(ord(c) > 127 for c in text):
        rep.note(where, "non-ASCII (CJK?) text: compiler emits font-family "
                 "fallback list; verify no tofu boxes in PNG preview")


def values_sanity(where, values, rep, axis_scale):
    nums = [v for v in values if is_number(v) and not math.isnan(v)]
    n_missing = len(values) - len(nums)
    if n_missing:
        rep.note(where, "%d missing/NaN value(s); compiler draws gap(s) and "
                 "records them in the ledger" % n_missing)
    if not nums:
        rep.error(where, "series contains no numeric values")
        return
    if axis_scale == "log":
        bad = [v for v in nums if v <= 0]
        if bad:
            rep.warn(where, "%d non-positive value(s) on log scale; compiler "
                     "skips them with a ledger note" % len(bad))
    pos = [abs(v) for v in nums if v != 0]
    if pos and max(pos) / min(pos) > 1e6:
        rep.warn(where, "magnitude span > 1e6 (%.3g .. %.3g); consider "
                 "scale='log' or rescaling with explicit unit" % (min(pos), max(pos)))


def check_axis(ax, where, rep, is_x):
    if not isinstance(ax, dict):
        rep.error(where, "axis must be an object")
        return
    check_unknown(ax, AXIS_KEYS, where, rep)
    if "label" not in ax:
        rep.error(where, "axis.label is required")
    else:
        check_label(where + ".label", ax["label"], rep)
    scale = ax.get("scale", "linear")
    if scale not in SCALES:
        rep.error(where, "axis.scale must be one of %s" % sorted(SCALES))
    if not is_x and scale == "categorical":
        rep.error(where, "y axis cannot be categorical")
    if "ticks" in ax and not isinstance(ax["ticks"], list):
        rep.error(where, "axis.ticks must be a list of numbers")


def series_inline_values(series):
    data = series.get("data") or {}
    vals = data.get("values")
    out = []
    if isinstance(vals, list):
        for item in vals:
            if isinstance(item, dict):
                out.append(item.get("y"))
    return out


def check_series_file_source(series, where, rep, spec_dir):
    data = series.get("data") or {}
    src = data.get("source")
    if not src:
        if not data.get("values"):
            rep.error(where, "data must have 'source' or 'values'+source_locator")
        elif not data.get("source_locator"):
            rep.error(where, "inline values require source_locator "
                      "(e.g. paper.pdf#page=4,table=2)")
        return
    check_unknown(src, SOURCE_KEYS, where + ".data.source", rep)
    path = src.get("path")
    if not path:
        rep.error(where, "data.source.path is required")
        return
    full = path if os.path.isabs(path) else os.path.join(spec_dir, path)
    if not os.path.exists(full):
        rep.error(where, "data file not found: %s" % full)
        return
    if not src.get("column_y"):
        rep.error(where, "data.source.column_y is required")
        return
    # verify columns exist for csv/tsv
    fmt = src.get("format") or os.path.splitext(full)[1].lstrip(".").lower()
    if fmt in ("csv", "tsv"):
        try:
            with open(full, "r", encoding="utf-8-sig", newline="") as fh:
                header = fh.readline().rstrip("\n").rstrip("\r")
            delim = "\t" if fmt == "tsv" else ","
            cols = [c.strip() for c in header.split(delim)]
            for key in ("column_x", "column_y", "column_yerr"):
                col = src.get(key)
                if col and col not in cols:
                    rep.error(where, "column %r not in %s header %s "
                              "(fix the locator, not the data)"
                              % (col, os.path.basename(full), cols))
        except OSError as exc:
            rep.warn(where, "could not read data file: %s" % exc)


def check_panel(panel, where, rep, spec_dir):
    if not isinstance(panel, dict):
        rep.error(where, "panel must be an object")
        return
    check_unknown(panel, PANEL_KEYS, where, rep)
    ptype = panel.get("type")
    if ptype not in CHART_TYPES:
        rep.error(where, "chart type must be one of %s" % sorted(CHART_TYPES))
    axes = panel.get("axes")
    if not isinstance(axes, dict):
        rep.error(where, "axes {x,y} required")
        return
    check_axis(axes.get("x"), where + ".axes.x", rep, is_x=True)
    check_axis(axes.get("y"), where + ".axes.y", rep, is_x=False)
    yscale = (axes.get("y") or {}).get("scale", "linear")
    series = panel.get("series")
    if not isinstance(series, list) or not series:
        rep.error(where, "at least one series is required")
        return
    units = set()
    axis_unit = (axes.get("y") or {}).get("unit")
    for i, s in enumerate(series):
        sw = "%s.series[%d](%s)" % (where, i, s.get("name", "?"))
        if not isinstance(s, dict):
            rep.error(sw, "series must be an object")
            continue
        check_unknown(s, SERIES_KEYS, sw, rep)
        if not s.get("name"):
            rep.error(sw, "series.name is required (it is the legend text)")
        else:
            check_label(sw + ".name", s["name"], rep)
        glyph = s.get("glyph")
        if glyph not in GLYPHS:
            rep.error(sw, "glyph must be one of %s" % sorted(GLYPHS))
        if ptype == "grouped_bar" and glyph not in ("bar", None):
            rep.warn(sw, "grouped_bar chart expects glyph 'bar'")
        if ptype == "scatter" and glyph == "bar":
            rep.error(sw, "scatter chart cannot use glyph 'bar'")
        if s.get("marker") and s["marker"] not in MARKERS:
            rep.error(sw, "marker must be one of %s" % sorted(MARKERS))
        has_prov = bool((s.get("data") or {}).get("source")) or \
            bool((s.get("data") or {}).get("source_locator")) or \
            bool(s.get("derived")) or s.get("manual") is True
        if not has_prov:
            rep.error(sw, "series has no provenance: add data.source, "
                      "data.source_locator, 'derived' or 'manual': true")
        check_series_file_source(s, sw, rep, spec_dir)
        vals = series_inline_values(s)
        if vals:
            values_sanity(sw, vals, rep, yscale)
        data = s.get("data") or {}
        has_err = bool((data.get("source") or {}).get("column_yerr")) or \
            any(isinstance(v, dict) and v.get("yerr") is not None
                for v in (data.get("values") or []))
        if has_err and not s.get("error_meaning"):
            rep.warn(sw, "error bars present but error_meaning (SD/SEM/95%CI) "
                     "not declared; add it for honest labeling")
        if s.get("unit"):
            units.add(s["unit"])
    if axis_unit:
        units.add(axis_unit)
    if len(units) > 1:
        rep.warn(where, "inconsistent y units across series: %s"
                 % sorted(units))
    for j, a in enumerate(panel.get("annotations") or []):
        aw = "%s.annotations[%d]" % (where, j)
        if not isinstance(a, dict):
            rep.error(aw, "annotation must be an object")
            continue
        check_unknown(a, ANNOT_KEYS, aw, rep)
        if not a.get("text"):
            rep.error(aw, "annotation.text is required")
        else:
            check_label(aw + ".text", a["text"], rep)
        if "x" not in a or "y" not in a:
            rep.error(aw, "annotation requires x and y")
        has_provenance(a, aw, rep, "annotation")


def check_diagram(d, where, rep):
    if not isinstance(d, dict):
        rep.error(where, "diagram must be an object")
        return
    check_unknown(d, DIAGRAM_KEYS, where, rep)
    nodes = d.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        rep.error(where, "diagram.nodes (non-empty) is required")
        return
    ids = set()
    for i, n in enumerate(nodes):
        nw = "%s.nodes[%d](%s)" % (where, i, n.get("id", "?"))
        if not isinstance(n, dict):
            rep.error(nw, "node must be an object")
            continue
        check_unknown(n, NODE_KEYS, nw, rep)
        nid = n.get("id")
        if not nid:
            rep.error(nw, "node.id is required")
        elif nid in ids:
            rep.error(nw, "duplicate node id %r" % nid)
        else:
            ids.add(nid)
        if n.get("shape") not in SHAPES:
            rep.error(nw, "shape must be one of %s" % sorted(SHAPES))
        for k in ("x", "y", "w", "h"):
            if not is_number(n.get(k)):
                rep.error(nw, "node.%s must be a number (0-100 relative)" % k)
        for k in ("x", "y"):
            v = n.get(k)
            if is_number(v) and not (0 <= v <= 100):
                rep.warn(nw, "%s=%g outside 0-100 canvas range" % (k, v))
        if not n.get("label"):
            rep.error(nw, "node.label is required (copy entity name verbatim)")
        else:
            check_label(nw + ".label", n["label"], rep)
        has_provenance(n, nw, rep, "node")
        if n.get("uncertain") is True:
            rep.note(nw, "uncertain node: rendered dashed, recorded in ledger")
    for i, e in enumerate(d.get("edges") or []):
        ew = "%s.edges[%d]" % (where, i)
        if not isinstance(e, dict):
            rep.error(ew, "edge must be an object")
            continue
        check_unknown(e, EDGE_KEYS, ew, rep)
        for k in ("from", "to"):
            if e.get(k) not in ids:
                rep.error(ew, "edge.%s=%r is not a known node id"
                          % (k, e.get(k)))
        if e.get("style") not in EDGE_STYLES:
            rep.error(ew, "edge style must be one of %s" % sorted(EDGE_STYLES))
        if e.get("route", "straight") not in ("straight", "elbow"):
            rep.error(ew, "route must be straight or elbow")
        if e.get("label"):
            check_label(ew + ".label", e["label"], rep)
        has_provenance(e, ew, rep, "edge")
    for i, c in enumerate(d.get("compartments") or []):
        cw = "%s.compartments[%d]" % (where, i)
        if not isinstance(c, dict):
            rep.error(cw, "compartment must be an object")
            continue
        check_unknown(c, COMP_KEYS, cw, rep)
        for k in ("x", "y", "w", "h"):
            if not is_number(c.get(k)):
                rep.error(cw, "compartment.%s must be a number" % k)
        if c.get("label"):
            check_label(cw + ".label", c["label"], rep)


def validate(spec, spec_dir):
    rep = Report()
    if not isinstance(spec, dict):
        rep.error("$", "top level must be a JSON object")
        return rep
    check_unknown(spec, TOP_KEYS, "$", rep)
    if spec.get("version") != "1.0":
        rep.error("$.version", "version must be \"1.0\"")
    if not spec.get("case_id"):
        rep.warn("$.case_id", "case_id missing; copy it verbatim from case.json")
    canvas = spec.get("canvas")
    if not isinstance(canvas, dict):
        rep.error("$.canvas", "canvas {width_mm,height_mm} is required")
    else:
        check_unknown(canvas, CANVAS_KEYS, "$.canvas", rep)
        for k in ("width_mm", "height_mm"):
            if not is_number(canvas.get(k)) or canvas[k] <= 20:
                rep.error("$.canvas." + k, "canvas.%s must be a number > 20" % k)
    mode = spec.get("mode")
    if mode not in ("chart", "diagram"):
        rep.error("$.mode", "mode must be 'chart' or 'diagram'")
    if spec.get("title"):
        check_label("$.title", spec["title"], rep)
    if mode == "chart":
        if "chart" in spec and "panels" in spec:
            rep.error("$", "use either 'chart' or 'panels', not both")
        if "chart" in spec:
            check_panel(spec["chart"], "$.chart", rep, spec_dir)
        elif "panels" in spec:
            if not isinstance(spec["panels"], list) or not spec["panels"]:
                rep.error("$.panels", "panels must be a non-empty array")
            else:
                for i, p in enumerate(spec["panels"]):
                    check_panel(p, "$.panels[%d]" % i, rep, spec_dir)
        else:
            rep.error("$", "mode=chart requires 'chart' or 'panels'")
    elif mode == "diagram":
        if "diagram" not in spec:
            rep.error("$", "mode=diagram requires 'diagram'")
        else:
            check_diagram(spec["diagram"], "$.diagram", rep)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Validate figure.spec.json for fig-spec-compiler. "
                    "Exit 0 unless --strict and errors are present.")
    ap.add_argument("spec", help="path to figure.spec.json")
    ap.add_argument("--report", help="write JSON report to this path")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when validation errors are present")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as exc:
        print("ERROR: cannot parse %s: %s" % (args.spec, exc))
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                json.dump({"ok": False,
                           "errors": [{"where": "$", "message": str(exc)}],
                           "warnings": [], "notes": []},
                          fh, indent=2, ensure_ascii=False)
        return 1 if args.strict else 0

    rep = validate(spec, os.path.dirname(os.path.abspath(args.spec)))
    ok = not rep.errors
    doc = {"ok": ok, "spec": os.path.abspath(args.spec),
           "n_errors": len(rep.errors), "n_warnings": len(rep.warnings),
           "errors": rep.errors, "warnings": rep.warnings, "notes": rep.notes}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False, sort_keys=True)
    print("validate_spec %s: %s (%d errors, %d warnings, %d notes)"
          % (VERSION, "OK" if ok else "ERRORS PRESENT",
             len(rep.errors), len(rep.warnings), len(rep.notes)))
    for e in rep.errors:
        print("  ERROR   %s: %s" % (e["where"], e["message"]))
    for w in rep.warnings:
        print("  WARNING %s: %s" % (w["where"], w["message"]))
    for n in rep.notes:
        print("  NOTE    %s: %s" % (n["where"], n["message"]))
    if rep.errors and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
