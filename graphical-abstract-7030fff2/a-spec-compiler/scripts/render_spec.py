#!/usr/bin/env python3
"""render_spec.py -- Bundle A (ga-spec-compiler), deterministic compiler, step 3.

Compile a GATE-PASSING figure_spec.json into:
  <out>/graphical_abstract.svg   editable, layered (one <g> per panel/element,
                                 ids = spec element ids, real <text> elements)
  <out>/graphical_abstract.png   raster preview at canvas.dpi (default 300)
  <out>/graphical_abstract.pdf   vector export for print
  <out>/render_report.json       what was written, sizes, matplotlib version

The model never writes SVG by hand: it authors the spec; this program draws.
Determinism: fixed rcParams, no timestamps in SVG, PNG metadata stripped;
same spec + same matplotlib version -> same layout (PDF carries a CreationDate
by design; see render_report for the exact versions used).

Usage:
  python3 render_spec.py --spec /app/work/figure_spec.json --outdir /app/output
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm

SAFE_TOKENS = {
    "black": "#000000", "orange": "#E69F00", "sky_blue": "#56B4E9",
    "bluish_green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
    "vermillion": "#D55E00", "reddish_purple": "#CC79A7",
    "grey": "#999999", "white": "#FFFFFF",
}
ROLE_STYLE = {  # role -> (default fill token, box style)
    "entity": ("sky_blue", "round,pad=0.02,rounding_size=0.05"),
    "process": ("bluish_green", "round,pad=0.02,rounding_size=0.05"),
    "outcome": ("orange", "round,pad=0.02,rounding_size=0.05"),
    "condition": ("yellow", "round,pad=0.02,rounding_size=0.05"),
    "intervention": ("vermillion", "round,pad=0.02,rounding_size=0.05"),
    "note": ("white", "square,pad=0.01"),
}
EDGE_STYLE = {"arrow": "-|>", "inhibit": "-[", "dashed": "-|>", "plain": "-"}


def colour(c, fallback="grey"):
    if not c:
        return SAFE_TOKENS[fallback]
    return SAFE_TOKENS.get(c, c)


def setup_rc():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "svg.fonttype": "none",          # keep <text> editable in the SVG
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.linewidth": 0.8,
        "savefig.bbox": None,
        "figure.dpi": 100,
    })


def draw_schematic(fig, panel, rect):
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    pid = panel.get("id", "panel")
    ax.set_gid("panel_%s" % pid)
    if panel.get("title"):
        ax.set_title(panel["title"], fontsize=panel.get("title_pt", 10),
                     loc="left", pad=4)

    node_centers = {}
    for node in panel.get("nodes", []):
        x, y, w, h = node["xywh_frac"]
        role = node.get("role", "entity")
        fill, boxstyle = ROLE_STYLE.get(role, ROLE_STYLE["entity"])
        fc = colour(node.get("fill"), fill)
        ec = colour(node.get("edge"), "black")
        y_top = 1.0 - y - h  # spec uses top-left origin; mpl uses bottom-left
        patch = FancyBboxPatch((x, y_top), w, h, boxstyle=boxstyle,
                               linewidth=1.0, edgecolor=ec, facecolor=fc,
                               mutation_aspect=1.0, zorder=2)
        patch.set_gid("node_%s" % node["id"])
        ax.add_patch(patch)
        label = node.get("label", "")
        sub = node.get("sublabel", "")
        text = label if not sub else label + "\n" + sub
        t = ax.text(x + w / 2, y_top + h / 2, text,
                    ha="center", va="center",
                    fontsize=node.get("font_pt", 9), zorder=3,
                    color=node.get("text_color", "#000000"))
        t.set_gid("text_%s" % node["id"])
        node_centers[node["id"]] = (x, y_top, w, h)

    for edge in panel.get("edges", []):
        a = node_centers.get(edge.get("from"))
        b = node_centers.get(edge.get("to"))
        if not a or not b:
            continue
        pa = (a[0] + a[2] / 2, a[1] + a[3] / 2)
        pb = (b[0] + b[2] / 2, b[1] + b[3] / 2)
        style = EDGE_STYLE.get(edge.get("style", "arrow"), "-|>")
        ls = "--" if edge.get("style") == "dashed" else "-"
        arr = FancyArrowPatch(pa, pb, arrowstyle=style, linestyle=ls,
                              mutation_scale=12, linewidth=1.2,
                              color=colour(edge.get("color"), "black"),
                              shrinkA=18, shrinkB=18, zorder=1)
        arr.set_gid("edge_%s_%s" % (edge.get("from"), edge.get("to")))
        ax.add_patch(arr)
        if edge.get("label"):
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            t = ax.text(mx, my + 0.02, edge["label"], ha="center",
                        va="bottom", fontsize=edge.get("font_pt", 8),
                        zorder=3)
            t.set_gid("edgelabel_%s_%s" % (edge.get("from"), edge.get("to")))

    for ann in panel.get("annotations", []):
        x, y = ann.get("xy_frac", [0.02, 0.05])
        t = ax.text(x, 1.0 - y, ann.get("text", ""),
                    fontsize=ann.get("font_pt", 8), ha="left", va="top",
                    style="italic" if ann.get("italic") else "normal")
        t.set_gid("annotation_%s" % pid)
    return ax


def draw_chart(fig, panel, rect):
    ax = fig.add_axes(rect)
    pid = panel.get("id", "panel")
    ax.set_gid("panel_%s" % pid)
    kind = panel.get("kind", "bar")
    if panel.get("title"):
        ax.set_title(panel["title"], fontsize=panel.get("title_pt", 10),
                     loc="left")
    for i, s in enumerate(panel.get("series", [])):
        c = colour(s.get("color"), None) or None
        if kind == "bar":
            xs = s.get("x", list(range(len(s.get("y", [])))))
            n = len(panel.get("series", []))
            width = 0.8 / max(n, 1)
            offset = (i - (n - 1) / 2.0) * width
            pos = [xi + offset if isinstance(xi, (int, float)) else xi
                   for xi in range(len(xs))]
            labels = s.get("x_labels")
            ax.bar([p for p in pos], s.get("y", []), width=width * 0.9,
                   color=c, label=s.get("name"))
            if labels:
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, fontsize=8)
        elif kind == "line":
            ax.plot(s.get("x", list(range(len(s.get("y", []))))),
                    s.get("y", []), marker="o", ms=3, lw=1.4,
                    color=c, label=s.get("name"))
        elif kind == "scatter":
            ax.scatter(s.get("x", []), s.get("y", []), s=18,
                       color=c, label=s.get("name"))
        if s.get("yerr"):
            xs = s.get("x", list(range(len(s.get("y", [])))))
            ax.errorbar(xs, s.get("y", []), yerr=s["yerr"], fmt="none",
                        ecolor=c or "black", elinewidth=0.9, capsize=2)
    if panel.get("x_label"):
        ax.set_xlabel(panel["x_label"], fontsize=9)
    if panel.get("y_label"):
        ax.set_ylabel(panel["y_label"], fontsize=9)
    series = panel.get("series", [])
    if len(series) > 1 and panel.get("legend", True):
        ax.legend(fontsize=8, frameon=False)
    ax.tick_params(labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return ax


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    os.makedirs(args.outdir, exist_ok=True)
    setup_rc()

    cv = spec.get("canvas", {})
    W, H = cv.get("width_in", 7.2), cv.get("height_in", 4.0)
    dpi = int(cv.get("dpi", 300))
    fig = plt.figure(figsize=(W, H))
    fig.set_gid("graphical_abstract")

    if spec.get("title"):
        fig.suptitle(spec["title"], fontsize=spec.get("title_pt", 12),
                     x=0.02, ha="left", y=0.98)

    written_panels = []
    for panel in spec.get("panels", []):
        x, y, w, h = panel["rect_in"]
        rect = [x / W, 1.0 - (y + h) / H, w / W, h / H]  # -> mpl figure frac
        if panel.get("kind") == "schematic":
            draw_schematic(fig, panel, rect)
        else:
            draw_chart(fig, panel, rect)
        written_panels.append(panel.get("id"))

    svg_path = os.path.join(args.outdir, "graphical_abstract.svg")
    png_path = os.path.join(args.outdir, "graphical_abstract.png")
    pdf_path = os.path.join(args.outdir, "graphical_abstract.pdf")
    fig.savefig(svg_path, format="svg")
    fig.savefig(png_path, format="png", dpi=dpi, metadata={"Software": None})
    fig.savefig(pdf_path, format="pdf")
    plt.close(fig)

    report = {
        "spec": args.spec,
        "matplotlib": matplotlib.__version__,
        "canvas_in": [W, H], "png_dpi": dpi,
        "panels_drawn": written_panels,
        "outputs": {p: os.path.getsize(p) for p in (svg_path, png_path, pdf_path)},
        "determinism_note": "same spec + same matplotlib version -> same "
                            "layout; PDF CreationDate metadata varies by run.",
    }
    with open(os.path.join(args.outdir, "render_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
