#!/usr/bin/env python3
"""compose_svg.py - compose a semantically-layered SVG figure plus a figmap.json sidecar.

Requires: python3 + matplotlib + numpy (headless, Agg backend).
Everything else in this skill is stdlib-only; THIS script is the only one that
needs matplotlib.

The SVG uses svg.fonttype='none' so all text stays editable (<text>, never
outlined).  Artists get stable semantic gids:
    axes, figure, legend,
    series/<name>/bar-<i>   (one <path> per bar)
    series/<name>/line      (one <path> polyline)
    series/<name>/pts       (scatter group; one <use>/<path> per point)
    annotation/<id>
    label/title, label/x, label/y
matplotlib additionally auto-ids tick groups as xtick_N / ytick_N.

The figmap.json sidecar records the data<->pixel transform, SELF-CALIBRATED
against the actual SVG geometry (not merely predicted), so that later
workorder ops can re-derive geometry from source values instead of
hand-computed pixels.

Usage:
    python3 compose_svg.py plan.json --out-svg /app/work/figure.svg \
        --figmap /app/work/figmap.json

Plan JSON (chart mode):
{
  "mode": "chart",
  "chart_type": "bar" | "line" | "scatter",
  "title": "...", "x_label": "...", "y_label": "...",
  "width_mm": 120, "height_mm": 90,
  "categories": ["ctrl", "drug"],            # optional; else linear x
  "x_range": [0, 10], "y_range": [0, 5],     # optional
  "baseline": 0.0,                            # bar baseline
  "series": [
    {"name": "wt", "x": [...], "y": [...], "yerr": [...],
     "source": "data.csv", "source_locator": "data.csv#column=rate",
     "color": "#0072B2", "linestyle": "-", "marker": "o"}
  ],
  "annotations": [{"id": "n1", "x": "drug", "y": 3.2, "text": "..."}]
}

Plan JSON (diagram mode) - for mechanism/flow schematics:
{
  "mode": "diagram",
  "title": "...",
  "nodes": [{"id": "ligand", "shape": "box|circle|diamond",
             "x": 2, "y": 8, "w": 2.4, "h": 1.2, "label": "Ligand",
             "color": "#DDEEFF"}],
  "edges": [{"from": "ligand", "to": "receptor", "label": "binds",
             "style": "-|>"}]
}
Diagram canvas is a 0-10 x 0-10 grid; the figmap still records the (linear)
grid->pixel transform so annotation placement ops keep working.
"""
import argparse
import json
import math
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Okabe-Ito colorblind-safe palette
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00",
           "#CC79A7", "#56B4E9", "#F0E442", "#000000"]

CJK_CANDIDATES = [
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
    "Source Han Sans CN", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
    "SimHei", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
    "Arial Unicode MS",
]

MM_PER_IN = 25.4


def setup_fonts(warnings):
    """Prefer a CJK-capable font; warn honestly if none is installed."""
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = [c for c in CJK_CANDIDATES if c in available]
    if chosen:
        plt.rcParams["font.sans-serif"] = chosen + ["DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    else:
        warnings.append(
            "no CJK font found (looked for: %s); CJK labels will be written "
            "as editable <text> but may render as boxes in raster previews" %
            ", ".join(CJK_CANDIDATES))
    plt.rcParams["svg.fonttype"] = "none"  # keep text editable, never outline


def parse_floats(d_attr):
    return [float(t) for t in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", d_attr)]


def find_by_id(root, eid):
    for el in root.iter():
        if el.get("id") == eid:
            return el
    return None


def calibrate_from_svg(svg_path, series_records, warnings):
    """Fit svg_px = a*value + b from the ACTUAL written geometry.

    Returns (y_a, y_b, x_calib) where x_calib is either
    {"kind": "linear", "a": .., "b": ..} or {"kind": "category",
    "centers": {cat: px}, "step_px": ..}.  Returns Nones on failure.
    """
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    y_a = y_b = None
    x_calib = None
    for rec in series_records:
        name, kind = rec["name"], rec["kind"]
        if kind == "bar" and y_a is None:
            # use the tallest |val - baseline| bar for a well-conditioned fit
            base = rec["baseline"]
            order = sorted(range(len(rec["y"])),
                           key=lambda i: -abs(rec["y"][i] - base))
            fitted = False
            for i in order:
                if abs(rec["y"][i] - base) < 1e-12:
                    continue
                el = find_by_id(root, "series/%s/bar-%d" % (name, i))
                if el is None:
                    continue
                path = el.find("{%s}path" % SVG_NS)
                if path is None:
                    continue
                nums = parse_floats(path.get("d", ""))
                xs, ys = nums[0::2], nums[1::2]
                if len(xs) < 4:
                    continue
                ytop, ybot = min(ys), max(ys)
                val = rec["y"][i]
                if val >= base:
                    y_val, y_base = ytop, ybot
                else:
                    y_val, y_base = ybot, ytop
                y_a = (y_val - y_base) / (val - base)
                y_b = y_base - y_a * base
                fitted = True
                break
            if fitted and x_calib is None:
                # category x: bar centers, in category order
                centers, xs_seen = {}, []
                cats = rec["x"]
                for i, cat in enumerate(cats):
                    el = find_by_id(root, "series/%s/bar-%d" % (name, i))
                    if el is None:
                        continue
                    path = el.find("{%s}path" % SVG_NS)
                    if path is None:
                        continue
                    nums = parse_floats(path.get("d", ""))
                    xs = nums[0::2]
                    if xs:
                        centers[str(cat)] = (min(xs) + max(xs)) / 2.0
                        xs_seen.append((min(xs) + max(xs)) / 2.0)
                if len(xs_seen) >= 2:
                    xs_seen.sort()
                    step = np.mean(np.diff(xs_seen))
                else:
                    step = None
                x_calib = {"kind": "category", "centers": centers,
                           "step_px": step}
        elif kind == "line":
            el = find_by_id(root, "series/%s/line" % name)
            if el is not None:
                path = el.find("{%s}path" % SVG_NS)
                if path is not None:
                    nums = parse_floats(path.get("d", ""))
                    xs, ys = nums[0::2], nums[1::2]
                    n = min(len(xs), len(rec["y"]))
                    if n >= 2:
                        if y_a is None:
                            A = np.polyfit(rec["y"][:n], ys[:n], 1)
                            y_a, y_b = float(A[0]), float(A[1])
                        if x_calib is None:
                            try:
                                xf = [float(v) for v in rec["x"][:n]]
                                A = np.polyfit(xf, xs[:n], 1)
                                x_calib = {"kind": "linear", "a": float(A[0]),
                                           "b": float(A[1])}
                            except (TypeError, ValueError):
                                pass
        elif kind == "scatter":
            el = find_by_id(root, "series/%s/pts" % name)
            if el is not None:
                pts = []
                for use in el.iter():
                    tag = use.tag.split("}")[-1]
                    if tag == "use" and use.get("x") is not None:
                        pts.append((float(use.get("x")), float(use.get("y"))))
                n = min(len(pts), len(rec["y"]))
                if n >= 2:
                    if y_a is None:
                        A = np.polyfit(rec["y"][:n], [p[1] for p in pts[:n]], 1)
                        y_a, y_b = float(A[0]), float(A[1])
                    if x_calib is None:
                        try:
                            xf = [float(v) for v in rec["x"][:n]]
                            A = np.polyfit(xf, [p[0] for p in pts[:n]], 1)
                            x_calib = {"kind": "linear", "a": float(A[0]),
                                       "b": float(A[1])}
                        except (TypeError, ValueError):
                            pass
    return y_a, y_b, x_calib


def compose_chart(plan, out_svg, warnings):
    ctype = plan.get("chart_type", "bar")
    w_mm = float(plan.get("width_mm", 120))
    h_mm = float(plan.get("height_mm", round(w_mm * 0.75)))
    fig, ax = plt.subplots(figsize=(w_mm / MM_PER_IN, h_mm / MM_PER_IN))
    fig.set_gid("figure")
    ax.set_gid("axes")

    categories = plan.get("categories")
    series = plan.get("series", [])
    if not series:
        raise SystemExit("compose plan has no series")
    if categories is None:
        # infer categorical x when any x value is non-numeric
        xs0 = series[0].get("x", [])
        if xs0 and not all(isinstance(v, (int, float)) for v in xs0):
            categories = [str(v) for v in xs0]
    baseline = float(plan.get("baseline", 0.0))
    series_records = []

    for si, s in enumerate(series):
        name = s.get("name", "series%d" % si)
        color = s.get("color", PALETTE[si % len(PALETTE)])
        y = [float(v) for v in s["y"]]
        yerr = s.get("yerr")
        if yerr is not None:
            yerr = [float(v) for v in yerr]
        if categories is not None:
            xraw = s.get("x", categories)
            xpos = [categories.index(str(v)) if str(v) in categories else i
                    for i, v in enumerate(xraw)]
            xstore = [str(v) for v in xraw]
        else:
            xpos = [float(v) for v in s.get("x", range(len(y)))]
            xstore = [float(v) for v in xpos]
        rec = {"name": name, "kind": ctype, "x": xstore, "y": y,
               "yerr": yerr, "baseline": baseline,
               "source": s.get("source"),
               "source_locator": s.get("source_locator"),
               "element_ids": []}

        if ctype == "bar":
            n = len(series)
            bw = 0.8 / n
            offsets = (np.arange(len(xpos)) + (si - (n - 1) / 2.0) * bw)
            cont = ax.bar(offsets, y, width=bw * 0.9, bottom=baseline,
                          color=color, label=name,
                          yerr=yerr, capsize=3 if yerr else 0,
                          error_kw={"linewidth": 1})
            for i, patch in enumerate(cont.patches):
                gid = "series/%s/bar-%d" % (name, i)
                patch.set_gid(gid)
                rec["element_ids"].append(gid)
        elif ctype == "line":
            (ln,) = ax.plot(xpos, y, marker=s.get("marker", "o"), color=color,
                            linestyle=s.get("linestyle", "-"), label=name,
                            linewidth=1.5, markersize=4)
            gid = "series/%s/line" % name
            ln.set_gid(gid)
            rec["element_ids"].append(gid)
            if yerr:
                ax.errorbar(xpos, y, yerr=yerr, fmt="none", ecolor=color,
                            elinewidth=1, capsize=3)
        elif ctype == "scatter":
            coll = ax.scatter(xpos, y, color=color, label=name, s=36,
                              marker=s.get("marker", "o"))
            gid = "series/%s/pts" % name
            coll.set_gid(gid)
            rec["element_ids"].append(gid)
            if yerr:
                ax.errorbar(xpos, y, yerr=yerr, fmt="none", ecolor=color,
                            elinewidth=1, capsize=3)
        else:
            raise SystemExit("unknown chart_type: %s" % ctype)
        series_records.append(rec)

    if categories is not None:
        ax.set_xticks(range(len(categories)))
        ax.set_xticklabels([str(c) for c in categories])
    if plan.get("x_range"):
        ax.set_xlim(*plan["x_range"])
    if plan.get("y_range"):
        ax.set_ylim(*plan["y_range"])

    title = ax.set_title(plan.get("title", ""), fontsize=9)
    title.set_gid("label/title")
    ax.set_xlabel(plan.get("x_label", ""), fontsize=8)
    ax.xaxis.label.set_gid("label/x")
    ax.set_ylabel(plan.get("y_label", ""), fontsize=8)
    ax.yaxis.label.set_gid("label/y")
    ax.tick_params(labelsize=7)
    if len(series) > 1 or plan.get("show_legend", True):
        leg = ax.legend(fontsize=7, frameon=False)
        leg.set_gid("legend")

    for ann in plan.get("annotations", []):
        aid = ann.get("id", "ann%d" % len(ax.texts))
        x = ann["x"]
        if categories is not None and not isinstance(x, (int, float)):
            x = categories.index(str(x))
        a = ax.annotate(ann["text"], xy=(x, float(ann["y"])),
                        xytext=(8, 10), textcoords="offset points",
                        fontsize=7,
                        arrowprops={"arrowstyle": "->", "lw": 0.8,
                                    "color": "#555555"})
        a.set_gid("annotation/%s" % aid)

    fig.tight_layout()
    fig.canvas.draw()

    # predicted transform (fallback): svg_pt = display_px * 72 / dpi,
    # y flipped around the canvas height in pt.
    dpi = fig.dpi
    h_pt = fig.get_size_inches()[1] * 72.0
    d00 = ax.transData.transform((0.0, 0.0))
    d11 = ax.transData.transform((1.0, 1.0))
    k = 72.0 / dpi
    pred = {
        "y": {"a": -(d11[1] - d00[1]) * k, "b": h_pt - d00[1] * k},
        "x": {"a": (d11[0] - d00[0]) * k, "b": d00[0] * k},
    }

    fig.savefig(out_svg, format="svg")
    return fig, ax, series_records, categories, baseline, pred


def compose_diagram(plan, out_svg, warnings):
    w_mm = float(plan.get("width_mm", 120))
    h_mm = float(plan.get("height_mm", round(w_mm * 0.75)))
    fig, ax = plt.subplots(figsize=(w_mm / MM_PER_IN, h_mm / MM_PER_IN))
    fig.set_gid("figure")
    ax.set_gid("axes")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    nodes = plan.get("nodes", [])
    pos = {}
    for nd in nodes:
        nid = nd.get("id", "node%d" % len(pos))
        x, y = float(nd.get("x", 5)), float(nd.get("y", 5))
        w, h = float(nd.get("w", 2.2)), float(nd.get("h", 1.2))
        color = nd.get("color", "#DDEEFF")
        shape = nd.get("shape", "box")
        if shape == "circle":
            patch = Circle((x, y), radius=min(w, h) / 2.0, fc=color,
                           ec="#333333", lw=1.2)
        elif shape == "diamond":
            patch = Polygon([(x, y + h / 2), (x + w / 2, y), (x, y - h / 2),
                             (x - w / 2, y)], fc=color, ec="#333333", lw=1.2)
        else:
            patch = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                   boxstyle="round,pad=0.08", fc=color,
                                   ec="#333333", lw=1.2)
        patch.set_gid("node/%s" % nid)
        ax.add_patch(patch)
        t = ax.text(x, y, nd.get("label", nid), ha="center", va="center",
                    fontsize=8)
        t.set_gid("node/%s/label" % nid)
        pos[nid] = (x, y)
    for ed in plan.get("edges", []):
        a, b = ed.get("from"), ed.get("to")
        if a not in pos or b not in pos:
            warnings.append("edge %s->%s skipped: unknown node" % (a, b))
            continue
        arr = FancyArrowPatch(pos[a], pos[b], arrowstyle=ed.get("style", "-|>"),
                              mutation_scale=12, lw=1.2, color="#333333",
                              shrinkA=22, shrinkB=22)
        arr.set_gid("edge/%s__%s" % (a, b))
        ax.add_patch(arr)
        if ed.get("label"):
            mx, my = (pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2
            t = ax.text(mx, my + 0.25, ed["label"], ha="center", fontsize=7,
                        color="#333333")
            t.set_gid("edge/%s__%s/label" % (a, b))
    if plan.get("title"):
        t = ax.set_title(plan["title"], fontsize=9)
        t.set_gid("label/title")
    fig.tight_layout()
    fig.canvas.draw()
    dpi = fig.dpi
    h_pt = fig.get_size_inches()[1] * 72.0
    d00 = ax.transData.transform((0.0, 0.0))
    d11 = ax.transData.transform((1.0, 1.0))
    k = 72.0 / dpi
    pred = {"y": {"a": -(d11[1] - d00[1]) * k, "b": h_pt - d00[1] * k},
            "x": {"a": (d11[0] - d00[0]) * k, "b": d00[0] * k}}
    fig.savefig(out_svg, format="svg")
    return fig, ax, [], None, 0.0, pred


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan")
    ap.add_argument("--out-svg", required=True)
    ap.add_argument("--figmap", required=True)
    args = ap.parse_args()

    warnings = []
    setup_fonts(warnings)
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_svg)), exist_ok=True)

    mode = plan.get("mode", "chart")
    if mode == "diagram":
        fig, ax, records, categories, baseline, pred = compose_diagram(
            plan, args.out_svg, warnings)
    else:
        fig, ax, records, categories, baseline, pred = compose_chart(
            plan, args.out_svg, warnings)

    # canvas from the actual file
    tree = ET.parse(args.out_svg)
    root = tree.getroot()
    vb = (root.get("viewBox") or "0 0 0 0").split()
    canvas = {"width_px": float(vb[2]), "height_px": float(vb[3]),
              "width_attr": root.get("width"), "height_attr": root.get("height")}

    y_a = y_b = None
    x_calib = None
    calibrated = False
    if records:
        y_a, y_b, x_calib = calibrate_from_svg(args.out_svg, records, warnings)
    if y_a is not None:
        calibrated = True
    else:
        y_a, y_b = pred["y"]["a"], pred["y"]["b"]
        if records:
            warnings.append("figmap y-transform is PREDICTED (self-calibration "
                            "failed); treat geometry edits with caution")
    if x_calib is None:
        if categories is not None and records:
            # derive category centers from predicted linear transform
            centers = {str(c): pred["x"]["a"] * i + pred["x"]["b"]
                       for i, c in enumerate(categories)}
            step = abs(pred["x"]["a"]) if len(categories) > 1 else None
            x_calib = {"kind": "category", "centers": centers, "step_px": step}
        else:
            x_calib = {"kind": "linear", "a": pred["x"]["a"],
                       "b": pred["x"]["b"]}

    ymin, ymax = ax.get_ylim()
    plot_area = {
        "y_bottom_px": y_a * ymin + y_b,
        "y_top_px": y_a * ymax + y_b,
    }
    if x_calib["kind"] == "linear":
        xmin, xmax = ax.get_xlim()
        plot_area["x_left_px"] = x_calib["a"] * xmin + x_calib["b"]
        plot_area["x_right_px"] = x_calib["a"] * xmax + x_calib["b"]
        axes_x = {"kind": "linear", "a": x_calib["a"], "b": x_calib["b"],
                  "min": xmin, "max": xmax}
    else:
        cs = sorted(x_calib["centers"].values())
        half = (x_calib["step_px"] or 0) / 2.0
        plot_area["x_left_px"] = cs[0] - half if cs else None
        plot_area["x_right_px"] = cs[-1] + half if cs else None
        axes_x = {"kind": "category", "categories": [str(c) for c in
                  (categories or [])],
                  "centers": {k: v for k, v in x_calib["centers"].items()},
                  "step_px": x_calib["step_px"]}

    figmap = {
        "figmap_version": "1.0",
        "created_with": "compose_svg.py 1.0.0 (matplotlib %s)" %
                        matplotlib.__version__,
        "mode": mode,
        "calibrated": calibrated,
        "canvas": canvas,
        "plot_area": plot_area,
        "baseline_y_px": y_a * baseline + y_b,
        "axes": {
            "x": axes_x,
            "y": {"kind": "linear", "a": y_a, "b": y_b,
                  "min": ymin, "max": ymax},
        },
        "series": {r["name"]: {k: r[k] for k in
                               ("kind", "element_ids", "x", "y", "yerr",
                                "baseline", "source", "source_locator")}
                   for r in records},
        "warnings": warnings,
    }
    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr)
    with open(args.figmap, "w", encoding="utf-8") as fh:
        json.dump(figmap, fh, ensure_ascii=False, indent=2)
    print("wrote %s and %s (mode=%s, calibrated=%s, series=%d)" %
          (args.out_svg, args.figmap, mode, calibrated, len(records)))


if __name__ == "__main__":
    main()
