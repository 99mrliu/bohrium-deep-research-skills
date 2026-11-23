#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_with_mpl.py — render the SAME figure primitives as
mini_svg_builder.compute_layout() to PNG (300 dpi, metadata embedded) and
PDF using matplotlib. Convenience exporter so the closed loop can be
exercised end-to-end; any other exporter that preserves the claims is fine.

Usage:
  python3 export_with_mpl.py --claims claims.json [--png figure.png] [--pdf figure.pdf]

Exit 0 on success; if matplotlib is unavailable, prints a note and exits 2
(a skipped export must never be reported as a success).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402
import mini_svg_builder as B  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
    except ImportError:
        print("NOTE: matplotlib not available; export skipped "
              "(not a pass, just skipped).", file=sys.stderr)
        return 2

    claims = B.load_claims(args.claims)
    lay = B.compute_layout(claims)
    W, H = lay["canvas"]["w"], lay["canvas"]["h"]

    fig = plt.figure(figsize=(W / 100.0, H / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)  # SVG-like: y grows downward
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H, facecolor="white", edgecolor="none"))
    ax.text(30, 44, lay["title"], fontsize=22, va="center", ha="left")

    for b in lay["bands"]:
        ax.add_patch(Rectangle((b["x"], b["y"]), b["w"], b["h"],
                               facecolor="#f4f6f8", edgecolor="#c8ced4",
                               linestyle=(0, (2, 3))))
        ax.text(b["x"] + 8, b["y"] + 16, b["name"], fontsize=12,
                color="#66707a", va="center", ha="left")

    for e in lay["edges"]:
        color = "#c0392b" if e["kind"] == "inhibits" else "#333333"
        ls = (0, (6, 4)) if e["evidence"] == "uncertain" else "solid"
        ax.plot([e["x1"], e["x2"]], [e["y1"], e["y2"]], color=color, lw=2,
                linestyle=ls, solid_capstyle="butt", zorder=2)
        if e["kind"] in ("activates", "phosphorylates", "ubiquitinates",
                         "transports", "recruits", "modifies"):
            dx, dy = e["x2"] - e["x1"], e["y2"] - e["y1"]
            ax.annotate("", xy=(e["x2"], e["y2"]),
                        xytext=(e["x2"] - dx * 0.02, e["y2"] - dy * 0.02),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=2),
                        zorder=3)
        elif e["kind"] == "inhibits":
            # T-bar perpendicular to the line at the target end
            dx, dy = e["x2"] - e["x1"], e["y2"] - e["y1"]
            L = max(1e-6, (dx ** 2 + dy ** 2) ** 0.5)
            px, py = -dy / L * 9, dx / L * 9
            ax.plot([e["x2"] - px, e["x2"] + px],
                    [e["y2"] - py, e["y2"] + py], color=color, lw=3,
                    solid_capstyle="butt", zorder=3)
        if e["badge"]:
            mx, my = (e["x1"] + e["x2"]) / 2.0, (e["y1"] + e["y2"]) / 2.0
            ax.add_patch(Circle((mx, my), 10, facecolor="white",
                                edgecolor="#333333", zorder=4))
            ax.text(mx, my, e["badge"], fontsize=11, ha="center",
                    va="center", zorder=5)

    for n in lay["nodes"].values():
        ax.add_patch(FancyBboxPatch(
            (n["cx"] - n["w"] / 2, n["cy"] - n["h"] / 2), n["w"], n["h"],
            boxstyle="round,pad=0,rounding_size=8",
            facecolor=n["fill"], edgecolor="#45505a", lw=1.2, zorder=6))
        ax.text(n["cx"], n["cy"], n["label"], fontsize=13, ha="center",
                va="center",
                style="italic" if n["type"] == "gene" else "normal",
                zorder=7)

    lb = lay["legend_box"]
    ax.add_patch(Rectangle((lb["x"], lb["y"]), lb["w"], lb["h"],
                           facecolor="white", edgecolor="#9aa4ad", zorder=8))
    for li in lay["legend_items"]:
        ax.add_patch(Rectangle((li["x"], li["y"]), 18, 14,
                               facecolor=li["color"], edgecolor="#555555",
                               zorder=9))
        txt = ("%s: %s" % (li["item"], li["meaning"])) if li["meaning"] \
            else li["item"]
        ax.text(li["x"] + 26, li["y"] + 7, txt, fontsize=11, va="center",
                ha="left", zorder=9)

    if args.png:
        fig.savefig(args.png, dpi=300)  # pHYs chunk carries 300 dpi
        print("wrote %s (300 dpi)" % args.png)
    if args.pdf:
        fig.savefig(args.pdf)  # matplotlib embeds its fonts in PDF
        print("wrote %s" % args.pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
