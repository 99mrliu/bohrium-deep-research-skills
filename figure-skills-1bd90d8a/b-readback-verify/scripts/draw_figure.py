#!/usr/bin/env python3
"""draw_figure.py -- draw a scientific figure from figure_plan.json.

Chart mode  : grouped bar (optional yerr), line (optional markers), scatter;
              single panel or a simple 1xN / Nx1 multi-panel array.
Diagram mode: nodes (box / roundbox / circle / diamond / cylinder) and edges
              (arrow styles) placed in a 0-100 coordinate space, for
              mechanism / flow schematics.

Headless (Agg). Writes figure.svg / figure.png (300 dpi) / figure.pdf and a
draw log JSON. Semantic gids are stamped on every data-bearing artist so the
independent verifier (readback_verify.py) can locate glyphs:
  bars      -> bar__<panel>__<series>__<i>
  err bars  -> err__<panel>__<series>
  lines     -> series__<panel>__<series>
  scatter   -> series__<panel>__<series>
  nodes     -> node__<id>
  edges     -> edge__<i>

Usage:
  python3 draw_figure.py figure_plan.json --out /app/output/figure \
      --formats svg,png,pdf [--log /app/work/draw_log.json]

Exit code: 0 on success, 2 on plan/data errors (message on stderr).
"""
import sys
import os
import json
import csv
import math
import hashlib
import argparse
import textwrap
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

try:
    import numpy as np
except ImportError:  # keep numpy optional
    np = None

MM_PER_INCH = 25.4

STYLE_PRESETS = {
    "default_pub": {
        "palette": ["#0072B2", "#E69F00", "#009E73", "#CC79A7",
                    "#56B4E9", "#D55E00", "#F0E442", "#000000"],
        "font_size": 7.5,
        "line_width": 1.0,
        "marker_size": 4.0,
        "spines_off": ("top", "right"),
        "grid": False,
    },
    "grayscale": {
        "palette": ["#222222", "#777777", "#BBBBBB", "#444444",
                    "#999999", "#DDDDDD"],
        "font_size": 7.5,
        "line_width": 1.0,
        "marker_size": 4.0,
        "spines_off": ("top", "right"),
        "grid": False,
    },
}

CJK_FONT_CANDIDATES = [
    "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
    "Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS",
]


def log_err(msg):
    sys.stderr.write("draw_figure: %s\n" % msg)


# ---------------------------------------------------------------- data I/O
def read_table(path):
    """Read CSV/TSV/JSON into {column: [values]} with row count.

    Strings that parse as float become floats; empty / 'nan' / 'NA' -> None.
    """
    if not os.path.isfile(path):
        raise ValueError("data file not found: %s" % path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):  # {col: [..]}
            return {str(k): [coerce(v) for v in vals]
                    for k, vals in obj.items()}
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            cols = {}
            for row in obj:
                for k, v in row.items():
                    cols.setdefault(str(k), []).append(coerce(v))
            return cols
        raise ValueError("unsupported JSON table shape in %s" % path)
    delim = "\t" if ext == ".tsv" else ","
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        if ext not in (".tsv",):
            try:
                delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
            except csv.Error:
                delim = ","
        rows = list(csv.reader(f, delimiter=delim))
    if len(rows) < 1:
        raise ValueError("empty data file: %s" % path)
    header = [h.strip() for h in rows[0]]
    cols = {h: [] for h in header}
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        for i, h in enumerate(header):
            cols[h].append(coerce(r[i]) if i < len(r) else None)
    return cols


def coerce(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return None
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "na", "n/a", "null", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return s


def resolve_values(spec, warnings, what):
    """spec: list of values, or {"file": ..., "column": ...}.

    Returns (values, source_locator). None entries are NaN gaps.
    """
    if isinstance(spec, dict):
        path = spec.get("file")
        col = spec.get("column")
        table = read_table(path)
        if col not in table:
            raise ValueError(
                "column %r missing in %s (available: %s)" %
                (col, path, ", ".join(sorted(table))))
        vals = table[col]
        n_missing = sum(1 for v in vals if v is None)
        if n_missing:
            warnings.append("nan_gap: %s has %d empty/NaN cells -> drawn as gaps"
                            % (what, n_missing))
        locator = "%s#%s" % (os.path.basename(path), col)
        return vals, locator
    if isinstance(spec, list):
        vals = [coerce(v) for v in spec]
        return vals, "literal"
    raise ValueError("unsupported value spec for %s: %r" % (what, spec))


# ---------------------------------------------------------------- fonts
def contains_nonascii(s):
    return any(ord(c) > 127 for c in s)


def collect_plan_text(plan):
    bits = [str(plan.get("title", ""))]
    for p in plan.get("panels", []):
        bits += [str(p.get("x_label", "")), str(p.get("y_label", "")),
                 str(p.get("title", ""))]
        for s in p.get("series", []):
            bits.append(str(s.get("name", "")))
        bits += [str(c) for c in p.get("categories", [])]
    d = plan.get("diagram") or {}
    for n in d.get("nodes", []):
        bits.append(str(n.get("label", "")))
    for e in d.get("edges", []):
        bits.append(str(e.get("label", "")))
    return bits


def pick_cjk_font():
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in CJK_FONT_CANDIDATES:
        if name in installed:
            return name
    return None


# ---------------------------------------------------------------- charts
def with_unit(label, unit):
    label = (label or "").strip()
    unit = (unit or "").strip()
    if unit and unit not in label:
        return "%s (%s)" % (label, unit) if label else unit
    return label


def numeric(xs):
    return [x for x in xs if isinstance(x, (int, float))]


def draw_bar_panel(ax, panel, preset, warnings, pid):
    cats = [str(c) for c in panel.get("categories", [])]
    series = panel.get("series", [])
    if not cats:
        raise ValueError("bar panel %s: 'categories' is required" % pid)
    if not series:
        raise ValueError("bar panel %s: at least one series is required" % pid)
    n, m = len(cats), len(series)
    total_w = 0.8
    bw = total_w / m
    xidx = list(range(n))
    palette = preset["palette"]
    for si, s in enumerate(series):
        name = str(s.get("name", "S%d" % si))
        vals, loc = resolve_values(s.get("values", []), warnings,
                                   "series %r values" % name)
        if len(vals) != n:
            raise ValueError(
                "series %r has %d values but %d categories" %
                (name, len(vals), n))
        heights = [v if isinstance(v, (int, float)) else 0.0 for v in vals]
        nan_idx = [i for i, v in enumerate(vals)
                   if not isinstance(v, (int, float))]
        if nan_idx:
            warnings.append("nan_gap: series %r missing categories %s -> "
                            "bar omitted (height 0 glyph avoided)"
                            % (name, [cats[i] for i in nan_idx]))
        offsets = [xi - total_w / 2 + bw * (si + 0.5) for xi in xidx]
        draw_x = [o for i, o in enumerate(offsets) if i not in nan_idx]
        draw_h = [heights[i] for i in range(n) if i not in nan_idx]
        color = s.get("color", palette[si % len(palette)])
        yerr = s.get("yerr")
        yerr_vals = None
        if yerr is not None:
            yv, _ = resolve_values(yerr, warnings, "series %r yerr" % name)
            if len(yv) != n:
                raise ValueError("series %r yerr length mismatch" % name)
            yerr_vals = [yv[i] for i in range(n) if i not in nan_idx]
        cont = ax.bar(draw_x, draw_h, bw, yerr=yerr_vals,
                      capsize=2 if yerr_vals else 0,
                      label=name, color=color,
                      edgecolor="black" if preset is STYLE_PRESETS["grayscale"]
                      else "none",
                      linewidth=0.5,
                      error_kw=dict(lw=0.7, capthick=0.7, ecolor="#333333"))
        for i, rect in zip([i for i in range(n) if i not in nan_idx],
                           cont.patches):
            rect.set_gid("bar__%s__%s__%d" % (pid, name, i))
        if yerr_vals and getattr(cont, "errorbar", None) is not None:
            data_line, caplines, barcols = cont.errorbar.lines
            for art in list(caplines) + list(barcols):
                art.set_gid("err__%s__%s" % (pid, name))
    ax.set_xticks(xidx)
    ax.set_xticklabels(cats)
    return [str(s.get("name", "S%d" % i)) for i, s in enumerate(series)]


def draw_xy_panel(ax, panel, preset, warnings, pid, kind):
    series = panel.get("series", [])
    if not series:
        raise ValueError("panel %s: at least one series is required" % pid)
    palette = preset["palette"]
    shared_x = panel.get("x")
    names = []
    for si, s in enumerate(series):
        name = str(s.get("name", "S%d" % si))
        names.append(name)
        xspec = s.get("x", shared_x)
        if xspec is None:
            ys_tmp, _ = resolve_values(s.get("values", []), warnings, name)
            xspec = list(range(len(ys_tmp)))
            warnings.append("series %r: no x given, using 0..N-1" % name)
        xs, _ = resolve_values(xspec, warnings, "series %r x" % name)
        ys, loc = resolve_values(s.get("values", []), warnings,
                                 "series %r values" % name)
        if len(xs) != len(ys):
            raise ValueError("series %r: x (%d) and values (%d) length "
                             "mismatch" % (name, len(xs), len(ys)))
        keep = [(x, y) for x, y in zip(xs, ys)
                if isinstance(x, (int, float)) and isinstance(y, (int, float))]
        dropped = len(xs) - len(keep)
        if dropped:
            warnings.append("nan_gap: series %r dropped %d NaN/empty points"
                            % (name, dropped))
        if not keep:
            warnings.append("series %r has no plottable points" % name)
            continue
        kx = [p[0] for p in keep]
        ky = [p[1] for p in keep]
        color = s.get("color", palette[si % len(palette)])
        if kind == "line":
            ln, = ax.plot(kx, ky,
                          marker=s.get("marker", "o" if len(kx) <= 30 else None),
                          ms=preset["marker_size"] * 0.8,
                          lw=preset["line_width"],
                          color=color, label=name)
            ln.set_gid("series__%s__%s" % (pid, name))
        else:  # scatter
            sc = ax.scatter(kx, ky, s=preset["marker_size"] ** 2,
                            color=color, label=name, zorder=3)
            sc.set_gid("series__%s__%s" % (pid, name))
    return names


def apply_panel_labels(ax, panel):
    ax.set_xlabel(with_unit(panel.get("x_label", ""), panel.get("x_unit", "")))
    ax.set_ylabel(with_unit(panel.get("y_label", ""), panel.get("y_unit", "")))
    if panel.get("title"):
        ax.set_title(str(panel["title"]), fontsize=8)


def draw_chart(plan, preset, warnings):
    panels = plan.get("panels") or [{}]
    npan = len(panels)
    w_mm = float(plan.get("width_mm", 89))
    h_mm = float(plan.get("height_mm", 70))
    fig, axes = plt.subplots(1, npan, figsize=(w_mm / MM_PER_INCH,
                                               h_mm / MM_PER_INCH),
                             squeeze=False)
    axes = axes[0]
    series_order = {}
    for pi, panel in enumerate(panels):
        ax = axes[pi]
        pid = str(panel.get("id", "p%d" % pi))
        ptype = panel.get("type", "bar")
        if ptype == "bar":
            names = draw_bar_panel(ax, panel, preset, warnings, pid)
        elif ptype in ("line", "scatter"):
            names = draw_xy_panel(ax, panel, preset, warnings, pid, ptype)
        else:
            raise ValueError("unknown panel type %r (bar|line|scatter)"
                             % ptype)
        apply_panel_labels(ax, panel)
        if panel.get("legend", True) and names:
            ax.legend(fontsize=preset["font_size"] - 1, frameon=False)
        for side in preset["spines_off"]:
            ax.spines[side].set_visible(False)
        ax.tick_params(labelsize=preset["font_size"])
        ax.xaxis.label.set_size(preset["font_size"])
        ax.yaxis.label.set_size(preset["font_size"])
        if preset.get("grid"):
            ax.grid(True, lw=0.3, alpha=0.5)
        series_order[pid] = names
    fig.tight_layout(pad=0.4)
    return fig, series_order


# ---------------------------------------------------------------- diagrams
def draw_diagram(plan, preset, warnings):
    d = plan.get("diagram") or {}
    nodes = d.get("nodes", [])
    edges = d.get("edges", [])
    if not nodes:
        raise ValueError("diagram mode requires diagram.nodes")
    w_mm = float(plan.get("width_mm", 120))
    h_mm = float(plan.get("height_mm", 80))
    fig, ax = plt.subplots(figsize=(w_mm / MM_PER_INCH, h_mm / MM_PER_INCH))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.invert_yaxis()  # plan coords: (0,0) top-left, y grows downward
    ax.axis("off")
    fs = preset["font_size"]
    pos = {}
    from matplotlib.patches import (FancyBboxPatch, Circle, Polygon, PathPatch)
    from matplotlib.path import Path
    for n in nodes:
        nid = str(n.get("id"))
        label = str(n.get("label", nid))
        x = float(n.get("x", 50)); y = float(n.get("y", 50))
        w = float(n.get("w", 18)); h = float(n.get("h", 10))
        shape = n.get("shape", "roundbox")
        fc = n.get("color", "#E8F1F8")
        pos[nid] = (x, y, w, h, shape)
        if shape == "circle":
            r = max(w, h) / 2.0
            ax.add_patch(Circle((x, y), r, fc=fc, ec="#333333", lw=0.8,
                                zorder=2))
        elif shape == "diamond":
            pts = [(x, y - h / 2 * 1.4), (x + w / 2 * 1.4, y),
                   (x, y + h / 2 * 1.4), (x - w / 2 * 1.4, y)]
            ax.add_patch(Polygon(pts, closed=True, fc=fc, ec="#333333",
                                 lw=0.8, zorder=2))
        elif shape == "cylinder":
            ry = h * 0.12
            verts = [(x - w / 2, y - h / 2 + ry), (x - w / 2, y + h / 2 - ry)]
            codes = [Path.MOVETO, Path.LINETO]
            # bottom arc
            for k in range(1, 25):
                t = math.pi * k / 24.0
                verts.append((x + (w / 2) * math.cos(math.pi + t) * -1,
                              y + h / 2 - ry + ry * math.sin(t) * -1))
                codes.append(Path.LINETO)
            verts.append((x + w / 2, y - h / 2 + ry)); codes.append(Path.LINETO)
            for k in range(1, 25):
                t = math.pi * k / 24.0
                verts.append((x + (w / 2) * math.cos(t),
                              y - h / 2 + ry - ry * math.sin(t) * -1))
                codes.append(Path.LINETO)
            verts.append(verts[0]); codes.append(Path.CLOSEPOLY)
            ax.add_patch(PathPatch(Path(verts, codes), fc=fc, ec="#333333",
                                   lw=0.8, zorder=2))
        elif shape == "box":
            ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                        boxstyle="square,pad=0", fc=fc,
                                        ec="#333333", lw=0.8, zorder=2))
        else:  # roundbox
            ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                        boxstyle="round,pad=0.6,rounding_size=1.5",
                                        fc=fc, ec="#333333", lw=0.8, zorder=2))
        wrap = int(n.get("wrap", max(6, int(w * 0.9))))
        txt = textwrap.fill(label, wrap) if wrap else label
        t = ax.text(x, y, txt, ha="center", va="center", fontsize=fs,
                    zorder=3)
        t.set_gid("node__%s" % nid)
    from matplotlib.patches import FancyArrowPatch
    arrow_map = {"->": "-|>", "-[": "-[", "--": "-|>", "line": "-"}

    def boundary(x, y, w, h, shape, dx, dy, margin=1.5):
        """Point where the ray (dx,dy) leaves the node, in data units."""
        if dx == 0 and dy == 0:
            return x, y
        if shape == "circle":
            r = max(w, h) / 2.0 + margin
            L = math.hypot(dx, dy)
            return x + dx / L * r, y + dy / L * r
        grow = 1.4 if shape == "diamond" else 1.0
        tx = (w / 2 * grow + margin) / abs(dx) if dx else float("inf")
        ty = (h / 2 * grow + margin) / abs(dy) if dy else float("inf")
        t = min(tx, ty)
        return x + dx * t, y + dy * t

    for ei, e in enumerate(edges):
        a = str(e.get("from")); b = str(e.get("to"))
        if a not in pos or b not in pos:
            warnings.append("edge %d references unknown node (%s -> %s); "
                            "skipped" % (ei, a, b))
            continue
        xa, ya, wa, ha, sa = pos[a]
        xb, yb, wb, hb, sb = pos[b]
        dx, dy = xb - xa, yb - ya
        p0 = boundary(xa, ya, wa, ha, sa, dx, dy)
        p1 = boundary(xb, yb, wb, hb, sb, -dx, -dy)
        style = arrow_map.get(e.get("style", "->"), "-|>")
        ls = "--" if e.get("style") == "--" else "-"
        arr = FancyArrowPatch(p0, p1, arrowstyle=style,
                              mutation_scale=8, lw=0.9, color="#333333",
                              linestyle=ls, zorder=1,
                              shrinkA=0, shrinkB=0)
        arr.set_gid("edge__%d" % ei)
        ax.add_patch(arr)
        if e.get("label"):
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            t = ax.text(mx, my - 1.5, str(e["label"]), ha="center",
                        va="bottom", fontsize=fs - 1, zorder=3,
                        style="italic")
            t.set_gid("edgelabel__%d" % ei)
    if plan.get("title"):
        ax.set_title(str(plan["title"]), fontsize=fs + 1)
    return fig, {}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", default="/app/output/figure")
    ap.add_argument("--formats", default="svg,png,pdf")
    ap.add_argument("--log", default="/app/work/draw_log.json")
    args = ap.parse_args()

    with open(args.plan, "r", encoding="utf-8") as f:
        raw = f.read()
    plan = json.loads(raw)
    plan_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    warnings = []
    style_name = plan.get("style", "default_pub")
    preset = STYLE_PRESETS.get(style_name)
    if preset is None:
        warnings.append("unknown style %r -> default_pub" % style_name)
        preset = STYLE_PRESETS["default_pub"]

    # base rcParams
    plt.rcParams.update({
        "svg.fonttype": "none",   # keep text as real <text> (editable)
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": preset["font_size"],
        "axes.linewidth": 0.8,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    })

    # CJK handling
    font_used = "DejaVu Sans"
    texts = collect_plan_text(plan)
    if any(contains_nonascii(t) for t in texts):
        cjk = pick_cjk_font()
        if cjk:
            plt.rcParams["font.family"] = [cjk, "DejaVu Sans"]
            font_used = cjk
        else:
            warnings.append(
                "cjk_font_missing: labels contain non-ASCII text but no CJK "
                "font found among %s; glyphs may render as tofu (口). "
                "Install one or transliterate labels." % CJK_FONT_CANDIDATES)

    mode = plan.get("mode", "chart")
    try:
        if mode == "diagram":
            fig, series_order = draw_diagram(plan, preset, warnings)
        else:
            fig, series_order = draw_chart(plan, preset, warnings)
    except ValueError as e:
        log_err(str(e))
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".",
                exist_ok=True)
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    files = {}
    for fmt in formats:
        path = "%s.%s" % (args.out, fmt)
        try:
            if fmt == "png":
                fig.savefig(path, dpi=int(plan.get("png_dpi", 300)))
            elif fmt in ("svg", "pdf"):
                fig.savefig(path)
            else:
                warnings.append("unknown format %r skipped" % fmt)
                continue
            files[fmt] = path
        except Exception as e:  # export failure must be recorded, not crash
            warnings.append("export_failure: %s: %s" % (fmt, e))
    plt.close(fig)

    log = {
        "plan_hash": plan_hash,
        "plan_path": os.path.abspath(args.plan),
        "files": files,
        "font_used": font_used,
        "warnings": warnings,
        "series_order": series_order,
        "style": style_name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)) or ".",
                    exist_ok=True)
        with open(args.log, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log_err("could not write draw log %s: %s" % (args.log, e))
    print(json.dumps({"files": files, "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
