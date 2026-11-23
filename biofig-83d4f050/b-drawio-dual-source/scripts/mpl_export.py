#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mpl_export.py -- render drawing primitives to PNG (dpi=300) and vector PDF.

The matplotlib canvas exactly matches the geometry canvas: figure size is
(width/dpi, height/dpi) inches at dpi=300, axes fill the whole figure, y axis is
inverted so geometry pixel coordinates map 1:1 to output pixels. That makes
verify_exports.py pixel probes (legend swatch color vs node fill color) exact.
PDF export sets pdf.fonttype=42 (TrueType, fonts embedded as Type 42).

CJK handling: we try a list of common CJK fonts; if none is available we keep the
default font and record a warning in the JSON summary (glyphs may show as boxes).

If matplotlib is not installed this script writes an honest failure JSON to stdout
and exits 2 -- the pipeline then ships drawio+SVG only and marks status partial.

CLI: python3 mpl_export.py --geometry FILE --out-dir DIR --basename NAME
"""
import argparse
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import geometry as G  # noqa: E402

DPI = 300
CJK_CANDIDATES = ["PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
                  "Source Han Sans SC", "SimHei", "WenQuanYi Zen Hei",
                  "Arial Unicode MS", "Heiti SC"]


def _pick_font(warnings):
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in CJK_CANDIDATES:
            if name in available:
                return name
        warnings.append("no CJK font found; Chinese glyphs may render as boxes")
    except Exception as exc:  # pragma: no cover
        warnings.append("font detection failed: %s" % exc)
    return None


def _draw_arrow(ax, x0, y0, x1, y1, kind, color, lw):
    from matplotlib.patches import FancyArrowPatch
    import math
    if kind == "bar":  # T-bar inhibition: shaft + perpendicular cap
        ax.plot([x0, x1], [y0, y1], color=color, lw=lw, solid_capstyle="round")
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        ux, uy = -dy / L, dx / L
        half = 8.0
        ax.plot([x1 - ux * half, x1 + ux * half], [y1 - uy * half, y1 + uy * half],
                color=color, lw=lw + 0.6, solid_capstyle="butt")
        return
    style = "-|>" if kind == "classic" else ("-|>" if kind == "open" else "-")
    patch = FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style,
                            mutation_scale=16, color=color, lw=lw,
                            fill=(kind != "open"), shrinkA=0, shrinkB=2)
    ax.add_patch(patch)


def render_primitives(prims, width, height, png_path, pdf_path):
    """Render primitives; returns (ok, summary_dict)."""
    warnings = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle, FancyBboxPatch, Ellipse
    except ImportError:
        return False, {"status": "failed",
                       "reason": "matplotlib not installed; PNG/PDF export unavailable",
                       "exports": []}
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    font = _pick_font(warnings)
    if font:
        matplotlib.rcParams["font.family"] = [font, "DejaVu Sans"]

    fig = plt.figure(figsize=(width / DPI, height / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)  # inverted: geometry y grows downward
    ax.axis("off")
    for p in prims:
        k = p["kind"]
        if k == "rect":
            if p.get("rounded"):
                ax.add_patch(FancyBboxPatch(
                    (p["x"], p["y"]), p["w"], p["h"],
                    boxstyle="round,pad=0,rounding_size=9",
                    facecolor=p.get("fill", "#ffffff"),
                    edgecolor=p.get("stroke", "#000000"),
                    linewidth=p.get("stroke_w", 1.5)))
            else:
                ax.add_patch(Rectangle((p["x"], p["y"]), p["w"], p["h"],
                                       facecolor=p.get("fill", "#ffffff"),
                                       edgecolor=p.get("stroke", "#000000"),
                                       linewidth=p.get("stroke_w", 1.5)))
            if p.get("double"):
                ax.add_patch(Rectangle((p["x"] + 5, p["y"] + 5), p["w"] - 10, p["h"] - 10,
                                       facecolor="none",
                                       edgecolor=p.get("stroke", "#000000"),
                                       linewidth=1.1))
        elif k == "ellipse":
            ax.add_patch(Ellipse((p["cx"], p["cy"]), p["rx"] * 2, p["ry"] * 2,
                                 facecolor=p.get("fill", "#ffffff"),
                                 edgecolor=p.get("stroke", "#000000"),
                                 linewidth=p.get("stroke_w", 1.5)))
        elif k == "polyline":
            pts = p["points"]
            if len(pts) < 2:
                continue
            ls = (0, (6, 4)) if p.get("dashed") else "solid"
            for i in range(len(pts) - 2):
                ax.plot([pts[i][0], pts[i + 1][0]], [pts[i][1], pts[i + 1][1]],
                        color=p.get("stroke", "#000"), lw=p.get("stroke_w", 2.0),
                        linestyle=ls, solid_capstyle="round")
            x0, y0 = pts[-2]
            x1, y1 = pts[-1]
            arrow = p.get("arrow", "none")
            if p.get("dashed"):
                ax.plot([x0, x1], [y0, y1], color=p.get("stroke", "#000"),
                        lw=p.get("stroke_w", 2.0), linestyle=ls)
            if arrow and arrow != "none":
                _draw_arrow(ax, x0, y0, x1, y1, arrow,
                            p.get("stroke", "#000"), p.get("stroke_w", 2.0))
            else:
                ax.plot([x0, x1], [y0, y1], color=p.get("stroke", "#000"),
                        lw=p.get("stroke_w", 2.0), linestyle=ls)
        elif k == "text":
            # geometry units are canvas pixels; at dpi=300 one pixel is 72/300 pt
            ax.text(p["x"], p["y"], str(p.get("text", "")),
                    fontsize=p.get("size", 12) * 72.0 / DPI,
                    fontstyle="italic" if p.get("italic") else "normal",
                    fontweight="bold" if p.get("bold") else "normal",
                    color=p.get("color", "#000"),
                    ha={"start": "left", "middle": "center", "end": "right"}.get(
                        p.get("anchor", "middle"), "center"),
                    va="center")
    exports = []
    if png_path:
        fig.savefig(png_path, dpi=DPI, facecolor="white")
        exports.append(png_path)
    if pdf_path:
        fig.savefig(pdf_path, facecolor="white")
        exports.append(pdf_path)
    plt.close(fig)
    return True, {"status": "ok", "exports": exports, "warnings": warnings,
                  "dpi": DPI, "size": [width, height]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="render geometry to PNG/PDF via matplotlib")
    ap.add_argument("--geometry", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--basename", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    model = G.load_geometry(args.geometry)
    W, H, prims, _ = G.primitives(model)
    png = os.path.join(args.out_dir, args.basename + ".png")
    pdf = os.path.join(args.out_dir, args.basename + ".pdf")
    ok, summary = render_primitives(prims, W, H, png, pdf)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
