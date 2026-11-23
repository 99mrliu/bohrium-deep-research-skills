#!/usr/bin/env python3
"""compile_figure.py - deterministic, stdlib-only figure compiler.

Reads a declarative figure.spec.json and renders a layered, editable SVG
(chart mode: grouped_bar / line / scatter; diagram mode: nodes + edges +
compartments). Every data glyph carries class="glyph" and a data-src
provenance attribute; a mapping_ledger.json gives the bidirectional
glyph <-> source-cell correspondence.

Determinism: same spec (+ same input data files) => byte-identical SVG.
No timestamps or random values are written into the SVG.

Usage:
    python3 compile_figure.py figure.spec.json --out-svg figure.svg \
        --ledger mapping_ledger.json

Exit codes: 0 ok; 2 spec/data error (message on stderr) - fix the SPEC,
never the SVG.
"""
import argparse
import csv
import datetime
import json
import math
import os
import sys

VERSION = "1.0.0"
FONT_STACK = ("Helvetica, Arial, 'Noto Sans CJK SC', 'Source Han Sans SC', "
              "'WenQuanYi Micro Hei', sans-serif")
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756",
           "#72B7B2", "#EECA3B", "#B279A2", "#9D755D"]
MISSING_TOKENS = {"", "nan", "na", "n/a", "null", "none", "-"}
BASE_FS = 3.2          # base font size in mm (~9 pt)
TICK_FS = 2.8
ANNOT_FS = 2.8


class CompileError(Exception):
    pass


# ---------------------------------------------------------------- utilities
def F(v):
    """Deterministic compact number formatting for SVG attributes."""
    s = "%.3f" % (float(v) + 0.0)
    s = s.rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s


def fmt_num(v):
    """Human tick labels."""
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e6 or av < 1e-4:
        s = "%.1e" % v
        mant, exp = s.split("e")
        return "%se%d" % (mant, int(exp))
    s = "%.6g" % v
    return s


def xesc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def aesc(s):
    return xesc(s).replace('"', "&quot;")


def est_w(s, fs):
    """Estimated text width in mm; CJK chars count 2x ASCII."""
    w = 0.0
    for c in str(s):
        w += fs * (1.0 if ord(c) >= 0x2E80 else 0.52)
    return w


def wrap_text(s, fs, maxw):
    """Wrap text to estimated width; breaks at spaces, hard-breaks CJK/long
    tokens anywhere."""
    s = str(s)
    if est_w(s, fs) <= maxw or maxw <= 0:
        return [s]
    lines, cur = [], ""
    for ch in s:
        trial = cur + ch
        if est_w(trial, fs) > maxw and cur:
            sp = cur.rfind(" ")
            if sp > 0 and ord(ch) < 0x2E80:
                lines.append(cur[:sp].rstrip())
                cur = cur[sp + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [s]


def truncate_label(s, fs, maxw):
    """Hard-truncate overlong labels with an ellipsis; returns (text, cut)."""
    s = str(s)
    if est_w(s, fs) <= maxw:
        return s, False
    ell = "…"
    while s and est_w(s + ell, fs) > maxw:
        s = s[:-1]
    return (s + ell) if s else ell, True


def nice_ticks(vmin, vmax, target=5):
    """Nice-number ticks: step in {1,2,2.5,5}*10^n."""
    if not (math.isfinite(vmin) and math.isfinite(vmax)):
        raise CompileError("non-finite axis range")
    if vmin == vmax:
        vmin, vmax = vmin - 1.0, vmax + 1.0
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    raw = (vmax - vmin) / max(1, target)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = 10.0 * mag
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= m * mag:
            step = m * mag
            break
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    ticks, t, guard = [], lo, 0
    while t <= hi + step * 1e-9 and guard < 200:
        ticks.append(round(t, 9))
        t += step
        guard += 1
    return ticks, lo, hi


# ---------------------------------------------------------------- svg writer
class SVG(object):
    def __init__(self, w_mm, h_mm, background, title_desc):
        self.w, self.h = w_mm, h_mm
        self.p = []
        self.p.append('<?xml version="1.0" encoding="UTF-8"?>')
        self.p.append('<svg xmlns="http://www.w3.org/2000/svg" '
                      'width="%smm" height="%smm" viewBox="0 0 %s %s">'
                      % (F(w_mm), F(h_mm), F(w_mm), F(h_mm)))
        self.p.append('<desc>%s</desc>' % xesc(title_desc))
        self.p.append('<style>text{font-family:%s;fill:#1a1a1a}'
                      '.glyph{stroke-linejoin:round}'
                      '.uncertain{stroke-dasharray:1.5,1}'
                      '</style>' % xesc(FONT_STACK))
        self.p.append('<defs>'
                      '<marker id="head-arrow" viewBox="0 0 10 10" refX="9" '
                      'refY="5" markerWidth="4" markerHeight="4" '
                      'orient="auto-start-reverse">'
                      '<path d="M0,0 L10,5 L0,10 z" fill="#1a1a1a"/></marker>'
                      '<marker id="head-tbar" viewBox="0 0 10 10" refX="8" '
                      'refY="5" markerWidth="4" markerHeight="4" '
                      'orient="auto">'
                      '<path d="M8,1 L8,9" stroke="#1a1a1a" '
                      'stroke-width="2" fill="none"/></marker>'
                      '</defs>')
        self.p.append('<g id="layer-background">')
        if background and background != "none":
            self.p.append('<rect x="0" y="0" width="%s" height="%s" fill="%s"/>'
                          % (F(w_mm), F(h_mm), aesc(background)))
        self.p.append('</g>')

    def open(self, layer_id):
        self.p.append('<g id="%s">' % aesc(layer_id))

    def close(self):
        self.p.append('</g>')

    def add(self, s):
        self.p.append(s)

    def text(self, x, y, s, fs=BASE_FS, anchor="start", fill="#1a1a1a",
             rotate=None, extra=""):
        tr = (' transform="rotate(%s %s %s)"' % (F(rotate), F(x), F(y))
              if rotate else "")
        self.p.append('<text x="%s" y="%s" font-size="%s" text-anchor="%s" '
                      'fill="%s"%s%s>%s</text>'
                      % (F(x), F(y), F(fs), anchor, aesc(fill), tr, extra,
                         xesc(s)))

    def mtext(self, x, y, lines, fs=BASE_FS, anchor="middle", fill="#1a1a1a",
              leading=1.25, extra=""):
        """Multi-line centered text; y is the vertical center of the block."""
        n = len(lines)
        y0 = y - (n - 1) * fs * leading / 2.0 + fs * 0.35
        parts = ['<text x="%s" y="%s" font-size="%s" text-anchor="%s" '
                 'fill="%s"%s>' % (F(x), F(y0), F(fs), anchor, aesc(fill),
                                   extra)]
        for i, ln in enumerate(lines):
            dy = 0 if i == 0 else fs * leading
            parts.append('<tspan x="%s" dy="%s">%s</tspan>'
                         % (F(x), F(dy), xesc(ln)))
        parts.append('</text>')
        self.p.append("".join(parts))

    def finish(self):
        self.p.append('</svg>')
        return "\n".join(self.p) + "\n"


# ---------------------------------------------------------------- ledger
class Ledger(object):
    def __init__(self, case_id, mode):
        self.doc = {"tool": "fig-spec-compiler/" + VERSION,
                    "case_id": case_id, "mode": mode,
                    "generated_at_utc": datetime.datetime.now(
                        datetime.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                    "glyphs": [], "warnings": [], "source_index": {}}

    def warn(self, msg):
        self.doc["warnings"].append(msg)

    def glyph(self, layer, kind, values, source, transform, notes=None,
              uncertain=False):
        gid = "g%03d" % (len(self.doc["glyphs"]) + 1)
        entry = {"glyph_id": gid, "layer": layer, "kind": kind,
                 "values": values, "source": source,
                 "transform": transform, "uncertain": bool(uncertain),
                 "notes": notes or []}
        self.doc["glyphs"].append(entry)
        key = None
        if isinstance(source, dict):
            key = source.get("key")
        if key:
            self.doc["source_index"].setdefault(key, []).append(gid)
        return gid


# ---------------------------------------------------------------- data input
def to_float(v, ctx):
    if v is None:
        return None
    if isinstance(v, bool):
        raise CompileError("%s: boolean is not a number" % ctx)
    if isinstance(v, (int, float)):
        f = float(v)
        return None if math.isnan(f) else f
    s = str(v).strip()
    if s.lower() in MISSING_TOKENS:
        return None
    try:
        return float(s)
    except ValueError:
        raise CompileError("%s: non-numeric value %r" % (ctx, s))


def read_records(source, spec_dir):
    path = source.get("path")
    if not path:
        raise CompileError("data.source.path is required")
    full = path if os.path.isabs(path) else os.path.join(spec_dir, path)
    if not os.path.exists(full):
        raise CompileError("data file not found: %s" % full)
    fmt = (source.get("format")
           or os.path.splitext(full)[1].lstrip(".").lower())
    records, columns = [], []
    if fmt in ("csv", "tsv"):
        delim = "\t" if fmt == "tsv" else ","
        with open(full, "r", encoding="utf-8-sig", newline="") as fh:
            rdr = csv.reader(fh, delimiter=delim)
            rows = [r for r in rdr if r]
        if not rows:
            raise CompileError("%s: empty data file" % full)
        columns = [c.strip() for c in rows[0]]
        for r in rows[1:]:
            rec = {}
            for i, c in enumerate(columns):
                rec[c] = r[i] if i < len(r) else ""
            records.append(rec)
    elif fmt == "json":
        with open(full, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        if isinstance(obj, list):
            records = obj
            columns = sorted({k for r in records if isinstance(r, dict)
                              for k in r})
        elif isinstance(obj, dict):  # dict of columns
            columns = list(obj.keys())
            n = max((len(v) for v in obj.values() if isinstance(v, list)),
                    default=0)
            for i in range(n):
                records.append({c: (obj[c][i] if i < len(obj[c]) else None)
                                for c in columns})
        else:
            raise CompileError("%s: unsupported json structure" % full)
    else:
        raise CompileError("%s: unsupported format %r (csv/tsv/json)"
                           % (full, fmt))
    sel = source.get("rows")
    if sel:
        records = [records[i] for i in sel if 0 <= i < len(records)]
    for key in ("column_x", "column_y", "column_yerr"):
        col = source.get(key)
        if col and col not in columns:
            raise CompileError(
                "%s: column %r not found; available columns: %s. "
                "Fix the locator in the spec, not the data."
                % (full, col, ", ".join(columns)))
    return records, full


def load_series_points(series, spec_dir, ledger, sname):
    """Return list of dicts: {x, y, yerr, srckey, locator, row}."""
    data = series.get("data") or {}
    out = []
    if data.get("source"):
        src = data["source"]
        records, full = read_records(src, spec_dir)
        cx, cy, ce = src.get("column_x"), src.get("column_y"), src.get("column_yerr")
        for i, rec in enumerate(records):
            ctx = "%s row %d (%s)" % (os.path.basename(full), i, sname)
            x = rec.get(cx) if cx else i
            if cx:
                try:
                    xf = to_float(x, ctx)
                    x = xf if xf is not None else str(x).strip()
                except CompileError:
                    x = str(x).strip()  # categorical x label, not a number
            try:
                y = to_float(rec.get(cy), ctx + " column " + str(cy))
            except CompileError:
                y = None  # dirty cell -> recorded gap, not a crash
                ledger.warn("%s: non-numeric y %r treated as missing gap"
                            % (ctx, rec.get(cy)))
            if ce:
                try:
                    e = to_float(rec.get(ce), ctx + " column " + str(ce))
                except CompileError:
                    e = None
                    ledger.warn("%s: non-numeric yerr %r ignored"
                                % (ctx, rec.get(ce)))
            else:
                e = None
            srckey = "%s#column=%s,row=%d" % (full, cy, i)
            out.append({"x": x, "y": y, "yerr": e, "row": i,
                        "srckey": srckey,
                        "source": {"path": full, "column": cy,
                                   "column_x": cx, "row": i,
                                   "key": srckey}})
    else:
        vals = data.get("values") or []
        loc = data.get("source_locator", "")
        for i, item in enumerate(vals):
            y = to_float(item.get("y"), "values[%d] (%s)" % (i, sname))
            e = to_float(item.get("yerr"), "values[%d].yerr" % i)
            srckey = "%s,item=%d" % (loc, i) if loc else "manual,item=%d" % i
            out.append({"x": item.get("x"), "y": y, "yerr": e, "row": i,
                        "srckey": srckey,
                        "source": {"path": None, "locator": loc, "row": i,
                                   "key": srckey}})
    if series.get("derived"):
        for p in out:
            p["source"]["derived"] = series["derived"]
    return out


# ---------------------------------------------------------------- chart mode
class AxisMap(object):
    """Maps data values to mm. Categorical x uses slot indices."""

    def __init__(self, scale, lo, hi, p_lo, p_hi):
        self.scale, self.lo, self.hi = scale, lo, hi
        self.p_lo, self.p_hi = p_lo, p_hi

    def map(self, v):
        if self.scale == "log":
            lo, hi, v = math.log10(self.lo), math.log10(self.hi), math.log10(v)
        else:
            lo, hi = self.lo, self.hi
        if hi == lo:
            return (self.p_lo + self.p_hi) / 2.0
        return self.p_lo + (v - lo) / (hi - lo) * (self.p_hi - self.p_lo)

    def transform_note(self, axis_name):
        if self.scale == "log":
            return ("%s_mm = %s + (log10(v)-log10(%g))/(log10(%g)-log10(%g))"
                    "*%s" % (axis_name, F(self.p_lo), self.lo, self.hi,
                             self.lo, F(self.p_hi - self.p_lo)))
        return ("%s_mm = %s + (v-(%g))/((%g)-(%g))*%s"
                % (axis_name, F(self.p_lo), self.lo, self.hi, self.lo,
                   F(self.p_hi - self.p_lo)))


def axis_label(ax):
    lbl = ax.get("label", "")
    return "%s (%s)" % (lbl, ax["unit"]) if ax.get("unit") else lbl


def marker_path(svg, shape, x, y, r, fill, attrs):
    if shape == "square":
        svg.add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"%s/>'
                % (F(x - r), F(y - r), F(2 * r), F(2 * r), aesc(fill), attrs))
    elif shape == "triangle":
        pts = "%s,%s %s,%s %s,%s" % (F(x), F(y - r), F(x - r), F(y + r * 0.8),
                                     F(x + r), F(y + r * 0.8))
        svg.add('<polygon points="%s" fill="%s"%s/>' % (pts, aesc(fill), attrs))
    else:  # circle
        svg.add('<circle cx="%s" cy="%s" r="%s" fill="%s"%s/>'
                % (F(x), F(y), F(r), aesc(fill), attrs))


def err_bar(svg, x, ylo, yhi, cap, color, attrs):
    svg.add('<path d="M%s,%s L%s,%s M%s,%s L%s,%s M%s,%s L%s,%s" '
            'stroke="%s" stroke-width="0.35" fill="none"%s/>'
            % (F(x), F(ylo), F(x), F(yhi),
               F(x - cap), F(ylo), F(x + cap), F(ylo),
               F(x - cap), F(yhi), F(x + cap), F(yhi),
               aesc(color), attrs))


def render_chart_panel(svg, ledger, panel, px, py, pw, ph, tag, spec_dir,
                       series_offset):
    axes = panel["axes"]
    ax_x, ax_y = axes["x"], axes["y"]
    ptype = panel["type"]
    yscale = ax_y.get("scale", "linear")
    xscale = ax_x.get("scale", "linear")
    categorical_x = ptype == "grouped_bar" or xscale == "categorical"
    series = panel["series"]

    # ---- load data
    loaded = []
    for s in series:
        pts = load_series_points(s, spec_dir, ledger, s.get("name", "?"))
        loaded.append((s, pts))

    # ---- categories / x range
    cats = []
    if categorical_x:
        for s, pts in loaded:
            for p in pts:
                k = str(p["x"])
                if k not in cats:
                    cats.append(k)
        if not cats:
            raise CompileError("%s: no x categories found" % tag)
    else:
        xs = [p["x"] for s, pts in loaded for p in pts
              if isinstance(p["x"], (int, float))]
        if not xs:
            raise CompileError("%s: numeric x required for line/scatter"
                               % tag)
        xlo, xhi = min(xs), max(xs)
        if ax_x.get("min") is not None:
            xlo = float(ax_x["min"])
        if ax_x.get("max") is not None:
            xhi = float(ax_x["max"])
        xticks, xlo, xhi = (ax_x.get("ticks") and
                            (ax_x["ticks"], min(ax_x["ticks"]),
                             max(ax_x["ticks"]))) or nice_ticks(xlo, xhi)

    # ---- y range
    ys = []
    for s, pts in loaded:
        for p in pts:
            if p["y"] is None:
                continue
            if yscale == "log" and p["y"] <= 0:
                ledger.warn("%s: non-positive value %g skipped on log scale"
                            % (tag, p["y"]))
                continue
            ys.append(p["y"])
            if p["yerr"]:
                ys.extend([p["y"] + p["yerr"],
                           max(p["y"] - p["yerr"], 1e-12)
                           if yscale == "log" else p["y"] - p["yerr"]])
    if not ys:
        raise CompileError("%s: no numeric y values" % tag)
    ylo, yhi = min(ys), max(ys)
    if ptype == "grouped_bar" and yscale != "log":
        ylo, yhi = min(ylo, 0.0), max(yhi, 0.0)
    if ax_y.get("min") is not None:
        ylo = float(ax_y["min"])
    if ax_y.get("max") is not None:
        yhi = float(ax_y["max"])
    if yscale == "log":
        klo, khi = math.floor(math.log10(ylo)), math.ceil(math.log10(yhi))
        yticks = [10.0 ** k for k in range(int(klo), int(khi) + 1)]
        ylo, yhi = yticks[0], yticks[-1]
    elif ax_y.get("ticks"):
        yticks = ax_y["ticks"]
        ylo, yhi = min(ylo, min(yticks)), max(yhi, max(yticks))
    else:
        yticks, ylo, yhi = nice_ticks(ylo, yhi)

    # ---- margins
    tick_w = max(est_w(fmt_num(t), TICK_FS) for t in yticks) if yticks else 0
    ml = tick_w + 9.0
    mt, mr = (6.0 if panel.get("title") else 3.0), 3.0
    rot_x = False
    cat_labels = {}
    if categorical_x:
        slot = (pw - ml - mr) / len(cats)
        max_lab = min(30.0, max(12.0, slot * 2.5))
        for c in cats:
            txt, cut = truncate_label(c, TICK_FS, max_lab)
            cat_labels[c] = txt
            if cut:
                ledger.warn("%s: overlong x tick label %r truncated to %r"
                            % (tag, c, txt))
        lab_w = max(est_w(t, TICK_FS) for t in cat_labels.values())
        rot_x = lab_w > slot * 0.92 and len(cats) > 1
        mb = (lab_w * 0.68 + 8.5) if rot_x else 9.5
    else:
        mb = 9.5
    plot_x, plot_y = px + ml, py + mt
    plot_w, plot_h = pw - ml - mr, ph - mt - mb
    if plot_w < 10 or plot_h < 10:
        raise CompileError("%s: panel too small (%gx%g mm)" % (tag, pw, ph))

    ymap = AxisMap(yscale, ylo, yhi, plot_y + plot_h, plot_y)
    if categorical_x:
        xmap = None
        slot = plot_w / len(cats)
        cat_cx = {c: plot_x + (i + 0.5) * slot for i, c in enumerate(cats)}
    else:
        xmap = AxisMap(ax_x.get("scale", "linear"), xlo, xhi,
                       plot_x, plot_x + plot_w)

    # ---- panel title
    if panel.get("title"):
        svg.open("layer-%s-title" % tag)
        svg.text(plot_x, py + 3.4, panel["title"], fs=BASE_FS,
                 anchor="start", extra=' font-weight="bold"')
        svg.close()

    # ---- grid + axes
    svg.open("layer-%s-grid" % tag)
    for t in yticks:
        yy = ymap.map(t)
        svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#e3e3e3" '
                'stroke-width="0.2"/>' % (F(plot_x), F(yy),
                                          F(plot_x + plot_w), F(yy)))
    svg.close()
    svg.open("layer-%s-axes" % tag)
    svg.add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" '
            'stroke="#1a1a1a" stroke-width="0.3"/>'
            % (F(plot_x), F(plot_y), F(plot_w), F(plot_h)))
    for t in yticks:
        yy = ymap.map(t)
        svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#1a1a1a" '
                'stroke-width="0.3"/>' % (F(plot_x - 1.2), F(yy),
                                          F(plot_x), F(yy)))
        svg.text(plot_x - 1.8, yy + TICK_FS * 0.35, fmt_num(t),
                 fs=TICK_FS, anchor="end")
    if categorical_x:
        for c in cats:
            cx = cat_cx[c]
            svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#1a1a1a" '
                    'stroke-width="0.3"/>' % (F(cx), F(plot_y + plot_h),
                                              F(cx), F(plot_y + plot_h + 1.2)))
            if rot_x:
                svg.text(cx - 0.6, plot_y + plot_h + 2.6, cat_labels[c],
                         fs=TICK_FS, anchor="end", rotate=-40)
            else:
                svg.text(cx, plot_y + plot_h + 3.4, cat_labels[c],
                         fs=TICK_FS, anchor="middle")
    else:
        for t in xticks:
            xx = xmap.map(t)
            svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#1a1a1a" '
                    'stroke-width="0.3"/>' % (F(xx), F(plot_y + plot_h),
                                              F(xx), F(plot_y + plot_h + 1.2)))
            svg.text(xx, plot_y + plot_h + 3.4, fmt_num(t), fs=TICK_FS,
                     anchor="middle")
    # axis titles
    svg.text(plot_x + plot_w / 2.0, plot_y + plot_h + mb - 1.2,
             axis_label(ax_x), fs=BASE_FS, anchor="middle")
    yl = axis_label(ax_y)
    svg.text(plot_x - ml + 2.6, plot_y + plot_h / 2.0, yl, fs=BASE_FS,
             anchor="middle", rotate=-90)
    svg.close()

    # ---- series glyphs
    bar_series = [i for i, (s, _) in enumerate(loaded)
                  if s.get("glyph", "bar" if ptype == "grouped_bar"
                           else "line") == "bar"]
    n_bars = max(1, len(bar_series))
    for si, (s, pts) in enumerate(loaded):
        name = s.get("name", "series%d" % si)
        color = s.get("color") or PALETTE[(series_offset + si) % len(PALETTE)]
        glyph = s.get("glyph", "bar" if ptype == "grouped_bar" else "line")
        marker = s.get("marker", "circle")
        uncertain = s.get("uncertain") is True
        layer = "layer-%s-series-%s" % (tag, name)
        svg.open(layer)
        dash = ' stroke-dasharray="1.5,1"' if uncertain else ""
        # x position helper
        def xpos(p):
            if categorical_x:
                k = str(p["x"])
                if k not in cat_cx:
                    return None
                return cat_cx[k]
            if not isinstance(p["x"], (int, float)):
                return None
            return xmap.map(p["x"])

        drawn = 0
        if glyph == "bar":
            slot = plot_w / len(cats)
            bw = slot * 0.72 / n_bars
            bidx = bar_series.index(si)
            for p in pts:
                cx = xpos(p)
                if cx is None:
                    ledger.warn("%s: unknown category %r skipped"
                                % (tag, p["x"]))
                    continue
                bx = cx - slot * 0.36 + bidx * bw
                base = ymap.map(0.0) if (ylo <= 0 <= yhi and
                                         yscale != "log") else ymap.map(ylo)
                if p["y"] is None:
                    ledger.glyph(layer, "bar-gap",
                                 {"x": str(p["x"]), "y": None}, p["source"],
                                 "missing value: no bar drawn",
                                 notes=["missing_value"], uncertain=uncertain)
                    continue
                if yscale == "log" and p["y"] <= 0:
                    continue
                top = ymap.map(p["y"])
                y0, h = min(top, base), abs(base - top)
                attrs = (' class="glyph%s" data-src="%s" data-value="%s"'
                         % (" uncertain" if uncertain else "",
                            aesc(p["srckey"]), aesc(fmt_num(p["y"]))))
                gid = ledger.glyph(layer, "bar",
                                   {"x": str(p["x"]), "y": p["y"],
                                    "yerr": p["yerr"]}, p["source"],
                                   ymap.transform_note("y"),
                                   uncertain=uncertain)
                svg.add('<rect id="%s" x="%s" y="%s" width="%s" height="%s" '
                        'fill="%s" stroke="#1a1a1a" stroke-width="0.2"%s/>'
                        % (gid, F(bx), F(y0), F(bw), F(h), aesc(color),
                           attrs))
                if p["yerr"]:
                    err_bar(svg, bx + bw / 2.0, ymap.map(p["y"] - p["yerr"]),
                            ymap.map(p["y"] + p["yerr"]), bw * 0.25,
                            "#1a1a1a", ' class="glyph" data-src="%s"'
                            % aesc(p["srckey"]))
                drawn += 1
        else:  # line or marker
            def skey(p):
                x = p["x"]
                if categorical_x:
                    k = str(x)
                    return (0, cats.index(k)) if k in cats else (1, 0.0)
                if isinstance(x, (int, float)):
                    return (0, float(x))
                try:
                    return (0, float(str(x)))
                except ValueError:
                    return (1, str(x))
            segs, cur = [], []
            for p in sorted(pts, key=skey):
                cx = xpos(p)
                if cx is None or p["y"] is None or (yscale == "log"
                                                    and p["y"] <= 0):
                    if cur:
                        segs.append(cur)
                        cur = []
                    if p["y"] is None:
                        ledger.glyph(layer, "point-gap",
                                     {"x": str(p["x"]), "y": None},
                                     p["source"],
                                     "missing value: line broken here",
                                     notes=["missing_value"],
                                     uncertain=uncertain)
                    continue
                cur.append((cx, ymap.map(p["y"]), p))
            if cur:
                segs.append(cur)
            if glyph == "line":
                for seg in segs:
                    d = " ".join("%s%s,%s" % ("M" if i == 0 else "L",
                                              F(a), F(b))
                                 for i, (a, b, _) in enumerate(seg))
                    svg.add('<path d="%s" fill="none" stroke="%s" '
                            'stroke-width="0.5"%s/>' % (d, aesc(color), dash))
            for seg in segs:
                for a, b, p in seg:
                    attrs = (' class="glyph%s" data-src="%s" data-value="%s"'
                             % (" uncertain" if uncertain else "",
                                aesc(p["srckey"]), aesc(fmt_num(p["y"]))))
                    gid = ledger.glyph(
                        layer, "point",
                        {"x": str(p["x"]), "y": p["y"], "yerr": p["yerr"]},
                        p["source"],
                        ymap.transform_note("y") + "; " +
                        ("x categorical slot" if categorical_x
                         else xmap.transform_note("x")),
                        uncertain=uncertain)
                    if glyph == "line" and marker != "none" or glyph == "marker":
                        marker_path(svg, marker, a, b, 1.1, color,
                                    ' id="%s"%s' % (gid, attrs))
                    if p["yerr"]:
                        err_bar(svg, a, ymap.map(p["y"] - p["yerr"]),
                                ymap.map(p["y"] + p["yerr"]), 1.0,
                                color, ' class="glyph" data-src="%s"'
                                % aesc(p["srckey"]))
                    drawn += 1
        if drawn == 0:
            ledger.warn("%s: series %r produced no glyphs (all missing?)"
                        % (tag, name))
        svg.close()

    # ---- annotations
    anns = panel.get("annotations") or []
    if anns:
        svg.open("layer-%s-annotations" % tag)
        for a in anns:
            x, y = a.get("x"), a.get("y")
            if a.get("data_coords", True):
                if categorical_x and str(x) in cat_cx:
                    xx = cat_cx[str(x)]
                elif isinstance(x, (int, float)) and xmap:
                    xx = xmap.map(x)
                else:
                    ledger.warn("%s: annotation x %r unmappable" % (tag, x))
                    continue
                yy = ymap.map(float(y))
            else:
                xx, yy = px + float(x), py + float(y)
            unc = a.get("uncertain") is True
            src = a.get("source_locator") or a.get("derived") or "manual"
            ledger.glyph("layer-%s-annotations" % tag, "annotation",
                         {"text": a["text"]},
                         {"locator": src, "key": "annotation:" + src},
                         "annotation at data coords (%s,%s)" % (x, y),
                         uncertain=unc)
            svg.text(xx, yy, a["text"], fs=ANNOT_FS,
                     anchor=a.get("anchor", "middle"),
                     fill=a.get("color", "#1a1a1a"),
                     extra=' class="%s"' % ("uncertain" if unc else "annot"))
        svg.close()

    # ---- legend
    leg = panel.get("legend") or {}
    pos = leg.get("position", "top-right")
    if pos != "none" and len(series) > 0:
        ent = []
        for si, (s, _) in enumerate(loaded):
            nm = s.get("name", "series%d" % si)
            col = s.get("color") or PALETTE[(series_offset + si)
                                            % len(PALETTE)]
            gl = s.get("glyph", "bar" if ptype == "grouped_bar" else "line")
            mk = s.get("marker", "circle")
            errm = s.get("error_meaning")
            label = "%s (error: %s)" % (nm, errm) if errm and any(
                p["yerr"] for p in loaded[si][1]) else nm
            ent.append((label, col, gl, mk))
        lw = max(est_w(e[0], TICK_FS) for e in ent) + 8.0
        lh = len(ent) * 4.0 + 2.0
        lx = plot_x + plot_w - lw - 1.5 if "right" in pos else plot_x + 1.5
        ly = plot_y + 1.5 if "top" in pos else plot_y + plot_h - lh - 1.5
        svg.open("layer-%s-legend" % tag)
        svg.add('<rect x="%s" y="%s" width="%s" height="%s" fill="#ffffff" '
                'fill-opacity="0.85" stroke="#999999" stroke-width="0.2"/>'
                % (F(lx), F(ly), F(lw), F(lh)))
        for i, (label, col, gl, mk) in enumerate(ent):
            ey = ly + 2.0 + i * 4.0
            if gl == "bar":
                svg.add('<rect x="%s" y="%s" width="3.2" height="2.2" '
                        'fill="%s" stroke="#1a1a1a" stroke-width="0.15"/>'
                        % (F(lx + 1.2), F(ey), aesc(col)))
            else:
                svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                        'stroke-width="0.5"/>' % (F(lx + 1.2), F(ey + 1.1),
                                                  F(lx + 4.4), F(ey + 1.1),
                                                  aesc(col)))
                marker_path(svg, mk if mk != "none" else "circle",
                            lx + 2.8, ey + 1.1, 0.8, col, "")
            svg.text(lx + 5.4, ey + 2.0, label, fs=TICK_FS, anchor="start")
        svg.close()


# -------------------------------------------------------------- diagram mode
def node_border_point(cx, cy, w, h, tx, ty):
    """Intersection of segment center->target with the node's bbox (rect
    approximation for all shapes)."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = w / 2.0, h / 2.0
    ts = []
    if dx:
        ts.append(hw / abs(dx))
    if dy:
        ts.append(hh / abs(dy))
    t = min(ts) if ts else 1.0
    return cx + dx * t, cy + dy * t


def render_diagram(svg, ledger, d, W, H):
    title = d.get("title")
    top = 8.0 if title else 3.0
    mx0, my0 = 5.0, top
    mw, mh = W - 10.0, H - top - 4.0

    def mm(x, y):
        return mx0 + x / 100.0 * mw, my0 + y / 100.0 * mh

    nodes = {n["id"]: n for n in d.get("nodes", [])}

    # compartments behind everything
    comps = d.get("compartments") or []
    if comps:
        svg.open("layer-compartments")
        for i, c in enumerate(comps):
            x0, y0 = mm(c["x"], c["y"])
            cw, ch = c["w"] / 100.0 * mw, c["h"] / 100.0 * mh
            fill = c.get("fill", "#f4f4f4")
            cid = c.get("id", "comp%d" % i)
            gid = ledger.glyph("layer-compartments", "compartment",
                               {"label": c.get("label", "")},
                               {"locator": c.get("source_locator", "manual"),
                                "key": "compartment:%s" % cid},
                               "compartment rect in 0-100 relative coords")
            svg.add('<rect id="%s" x="%s" y="%s" width="%s" height="%s" '
                    'rx="1.5" fill="%s" stroke="#bbbbbb" stroke-width="0.25" '
                    'class="glyph" data-src="%s"/>'
                    % (gid, F(x0), F(y0), F(cw), F(ch), aesc(fill),
                       aesc("compartment:" + cid)))
            if c.get("label"):
                svg.text(x0 + 1.5, y0 + 3.2, c["label"], fs=TICK_FS,
                         anchor="start", fill="#555555")
        svg.close()

    # edges
    edges = d.get("edges") or []
    if edges:
        svg.open("layer-edges")
        for e in edges:
            a, b = nodes.get(e.get("from")), nodes.get(e.get("to"))
            if not a or not b:
                ledger.warn("edge %s->%s references unknown node; skipped"
                            % (e.get("from"), e.get("to")))
                continue
            acx, acy = mm(a["x"], a["y"])
            bcx, bcy = mm(b["x"], b["y"])
            aw, ah = a["w"] / 100.0 * mw, a["h"] / 100.0 * mh
            bw, bh = b["w"] / 100.0 * mw, b["h"] / 100.0 * mh
            style = e.get("style", "arrow")
            dash = ' stroke-dasharray="1.6,1.2"' if style == "dashed" else ""
            mark = {"arrow": ' marker-end="url(#head-arrow)"',
                    "dashed": ' marker-end="url(#head-arrow)"',
                    "tbar": ' marker-end="url(#head-tbar)"',
                    "blunt": ""}[style]
            unc = e.get("uncertain") is True
            if unc:
                dash = ' stroke-dasharray="1.6,1.2"'
            route = e.get("route", "straight")
            if route == "elbow":
                if abs(bcx - acx) >= abs(bcy - acy):
                    sx, sy = acx + math.copysign(aw / 2.0, bcx - acx), acy
                    ex, ey = bcx - math.copysign(bw / 2.0, bcx - acx), bcy
                    midx = (sx + ex) / 2.0
                    dpath = "M%s,%s L%s,%s L%s,%s L%s,%s" % (
                        F(sx), F(sy), F(midx), F(sy), F(midx), F(ey),
                        F(ex), F(ey))
                else:
                    sx, sy = acx, acy + math.copysign(ah / 2.0, bcy - acy)
                    ex, ey = bcx, bcy - math.copysign(bh / 2.0, bcy - acy)
                    midy = (sy + ey) / 2.0
                    dpath = "M%s,%s L%s,%s L%s,%s L%s,%s" % (
                        F(sx), F(sy), F(sx), F(midy), F(ex), F(midy),
                        F(ex), F(ey))
            else:
                sx, sy = node_border_point(acx, acy, aw, ah, bcx, bcy)
                ex, ey = node_border_point(bcx, bcy, bw, bh, acx, acy)
                dpath = "M%s,%s L%s,%s" % (F(sx), F(sy), F(ex), F(ey))
            loc = e.get("source_locator") or e.get("derived") or "manual"
            gid = ledger.glyph(
                "layer-edges", "edge",
                {"from": e.get("from"), "to": e.get("to"),
                 "style": style, "label": e.get("label")},
                {"locator": loc, "key": "edge:%s->%s:%s"
                 % (e.get("from"), e.get("to"), loc)},
                "center-to-center clipped at node bbox; style=%s" % style,
                uncertain=unc)
            svg.add('<path id="%s" d="%s" fill="none" stroke="#1a1a1a" '
                    'stroke-width="0.4"%s%s class="glyph%s" data-src="%s"/>'
                    % (gid, dpath, dash, mark,
                       " uncertain" if unc else "", aesc(loc)))
            if e.get("label"):
                lx, ly = (sx + ex) / 2.0, (sy + ey) / 2.0 - 1.2
                svg.text(lx, ly, e["label"], fs=ANNOT_FS, anchor="middle",
                         fill="#333333")
        svg.close()

    # nodes
    svg.open("layer-nodes")
    for n in d.get("nodes", []):
        cx, cy = mm(n["x"], n["y"])
        w, h = n["w"] / 100.0 * mw, n["h"] / 100.0 * mh
        shape = n.get("shape", "rounded_rect")
        fill = n.get("fill", "#dbe9f6")
        unc = n.get("uncertain") is True
        loc = n.get("source_locator") or n.get("derived") or "manual"
        cls = "glyph uncertain" if unc else "glyph"
        attrs = ' class="%s" data-src="%s"' % (cls, aesc(loc))
        gid = ledger.glyph(
            "layer-nodes", "node",
            {"id": n["id"], "label": n.get("label"), "shape": shape},
            {"locator": loc, "key": "node:%s:%s" % (n["id"], loc)},
            "center=(%g,%g) of 0-100 canvas" % (n["x"], n["y"]),
            uncertain=unc)
        common = 'id="%s" fill="%s" stroke="#1a1a1a" stroke-width="0.35"%s'
        if shape == "ellipse":
            svg.add(('<ellipse %s cx="%s" cy="%s" rx="%s" ry="%s"/>'
                     % (common % (gid, aesc(fill), attrs), F(cx), F(cy),
                        F(w / 2.0), F(h / 2.0))))
        elif shape == "diamond":
            pts = "%s,%s %s,%s %s,%s %s,%s" % (
                F(cx), F(cy - h / 2.0), F(cx + w / 2.0), F(cy),
                F(cx), F(cy + h / 2.0), F(cx - w / 2.0), F(cy))
            svg.add('<polygon %s points="%s"/>'
                    % (common % (gid, aesc(fill), attrs), pts))
        elif shape == "cylinder":
            ry = min(h * 0.18, 3.0)
            dpath = ("M%s,%s A%s,%s 0 0 1 %s,%s L%s,%s A%s,%s 0 0 1 %s,%s Z"
                     % (F(cx - w / 2), F(cy - h / 2 + ry), F(w / 2), F(ry),
                        F(cx + w / 2), F(cy - h / 2 + ry),
                        F(cx + w / 2), F(cy + h / 2 - ry), F(w / 2), F(ry),
                        F(cx - w / 2), F(cy + h / 2 - ry)))
            svg.add('<path %s d="%s"/>'
                    % (common % (gid, aesc(fill), attrs), dpath))
        else:  # rounded_rect
            svg.add('<rect %s x="%s" y="%s" width="%s" height="%s" rx="%s"/>'
                    % (common % (gid, aesc(fill), attrs), F(cx - w / 2),
                       F(cy - h / 2), F(w), F(h), F(min(w, h) * 0.18)))
        lines = wrap_text(n.get("label", ""), BASE_FS, w * 0.86)
        if len(lines) > 4:
            ledger.warn("node %r label wrapped to %d lines; may overflow"
                        % (n["id"], len(lines)))
        svg.mtext(cx, cy, lines, fs=BASE_FS)
    svg.close()

    # legend
    leg = d.get("legend") or {}
    items = leg.get("items") or []
    pos = leg.get("position", "bottom-left")
    if items and pos != "none":
        lw = max(est_w(i.get("label", ""), TICK_FS) for i in items) + 10.0
        lh = len(items) * 4.2 + 2.0
        lx = W - lw - 4.0 if "right" in pos else 4.0
        ly = top + 1.0 if "top" in pos else H - lh - 3.0
        svg.open("layer-legend")
        svg.add('<rect x="%s" y="%s" width="%s" height="%s" fill="#ffffff" '
                'fill-opacity="0.9" stroke="#999999" stroke-width="0.2"/>'
                % (F(lx), F(ly), F(lw), F(lh)))
        for i, it in enumerate(items):
            ey = ly + 2.4 + i * 4.2
            if it.get("style"):
                mark = {"arrow": ' marker-end="url(#head-arrow)"',
                        "dashed": ' marker-end="url(#head-arrow)"',
                        "tbar": ' marker-end="url(#head-tbar)"',
                        "blunt": ""}[it["style"]]
                dash = (' stroke-dasharray="1.6,1.2"'
                        if it["style"] == "dashed" else "")
                svg.add('<line x1="%s" y1="%s" x2="%s" y2="%s" '
                        'stroke="#1a1a1a" stroke-width="0.4"%s%s/>'
                        % (F(lx + 1.2), F(ey), F(lx + 7.0), F(ey), dash,
                           mark))
            else:
                svg.add('<rect x="%s" y="%s" width="3.4" height="2.4" '
                        'fill="%s" stroke="#1a1a1a" stroke-width="0.2"/>'
                        % (F(lx + 1.2), F(ey - 1.2),
                           aesc(it.get("fill", "#dbe9f6"))))
            svg.text(lx + 8.0, ey + 1.0, it.get("label", ""), fs=TICK_FS,
                     anchor="start")
        svg.close()

    if title:
        svg.open("layer-title")
        svg.text(W / 2.0, 4.6, title, fs=BASE_FS + 0.6, anchor="middle",
                 extra=' font-weight="bold"')
        svg.close()


# ---------------------------------------------------------------- driver
def compile_spec(spec, spec_dir):
    mode = spec.get("mode")
    canvas = spec.get("canvas") or {}
    W = float(canvas.get("width_mm", 180))
    H = float(canvas.get("height_mm", 120))
    bg = canvas.get("background", "#ffffff")
    ledger = Ledger(spec.get("case_id", ""), mode)
    desc = ("fig-spec-compiler %s | case=%s | mode=%s | layered editable SVG; "
            "glyphs carry data-src provenance" % (VERSION,
                                                  spec.get("case_id", ""),
                                                  mode))
    svg = SVG(W, H, bg, desc)
    if mode == "chart":
        if "panels" in spec:
            panels = spec["panels"]
        elif "chart" in spec:
            panels = [spec["chart"]]
        else:
            raise CompileError("mode=chart requires 'chart' or 'panels'")
        n = len(panels)
        cols = (spec.get("layout") or {}).get("cols") or min(n, 2)
        rows = int(math.ceil(n / float(cols)))
        title_band = 8.0 if spec.get("title") else 2.0
        cw, ch = W / cols, (H - title_band) / rows
        total_series = 0
        for i, p in enumerate(panels):
            r, c = divmod(i, cols)
            render_chart_panel(svg, ledger, p, c * cw, title_band + r * ch,
                               cw, ch, "panel%d" % i, spec_dir, total_series)
            total_series += len(p.get("series") or [])
        if spec.get("title"):
            svg.open("layer-title")
            svg.text(W / 2.0, 5.0, spec["title"], fs=BASE_FS + 0.8,
                     anchor="middle", extra=' font-weight="bold"')
            svg.close()
    elif mode == "diagram":
        render_diagram(svg, ledger, spec.get("diagram") or {}, W, H)
    else:
        raise CompileError("mode must be 'chart' or 'diagram'")
    return svg.finish(), ledger.doc


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Compile figure.spec.json to layered editable SVG + "
                    "mapping ledger (deterministic, stdlib-only).")
    ap.add_argument("spec", help="path to figure.spec.json")
    ap.add_argument("--out-svg", required=True, help="output SVG path")
    ap.add_argument("--ledger", help="output mapping_ledger.json path")
    args = ap.parse_args(argv)

    try:
        with open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as exc:
        print("ERROR: cannot parse spec %s: %s" % (args.spec, exc),
              file=sys.stderr)
        return 2
    spec_dir = os.path.dirname(os.path.abspath(args.spec))
    try:
        svg_text, ledger = compile_spec(spec, spec_dir)
    except CompileError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    out_dir = os.path.dirname(os.path.abspath(args.out_svg))
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(args.out_svg, "w", encoding="utf-8") as fh:
        fh.write(svg_text)
    if args.ledger:
        with open(args.ledger, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, indent=2, ensure_ascii=False)
    print("compile_figure %s: wrote %s (%d glyphs, %d warnings)"
          % (VERSION, args.out_svg, len(ledger["glyphs"]),
             len(ledger["warnings"])))
    for w in ledger["warnings"]:
        print("  WARNING %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
