#!/usr/bin/env python3
"""preview_render.py -- render layout.json geometry to per-slide preview images.

Stdlib path (always): preview/slide-NN.svg with exact EMU->px geometry, the
wrapped lines from layout.json as positioned <text> elements, and theme colors.
Optional path (if matplotlib is importable): preview/slide-NN.png raster
previews drawn from the SAME geometry -- real pixels for visual inspection
without any office suite installed.

    preview_render.py --layout work/layout.json --theme work/theme.json \
        --out /app/output/preview/
"""
import argparse
import json
import os
import sys
from xml.sax.saxutils import escape

EMU_PER_PT = 12700


def _hex(colors, key, fallback):
    v = (colors or {}).get(key, fallback)
    return "#" + v if v and not v.startswith("#") else (v or fallback)


def _slide_boxes(slide):
    """Yield (kind, box, size_pt, lines) for every text element of a slide."""
    for kind, key in (("title", "title_box"), ("body", "body_box"),
                      ("source", "source_box")):
        box = slide.get(key)
        if not box:
            continue
        if kind == "body":
            lines = []
            for item in box.get("items", []):
                lines.extend(item.get("lines", []))
        else:
            lines = box.get("lines", [])
        yield kind, box, box.get("size_pt", 14), lines
    if slide.get("image_box"):
        yield "image", slide["image_box"], 11, ["[image] %s" % (slide.get("image") or "")]


def render_svg(layout, theme, out_dir):
    w_pt = layout["slide_w_emu"] / EMU_PER_PT
    h_pt = layout["slide_h_emu"] / EMU_PER_PT
    colors = layout.get("colors") or theme.get("colors", {})
    bg = _hex(colors, "bg", "#FFFFFF")
    txt = _hex(colors, "text", "#000000")
    acc1 = _hex(colors, "accent1", "#4472C4")
    acc3 = _hex(colors, "accent3", "#A5A5A5")
    body_font = (layout.get("fonts") or theme.get("fonts", {})).get("body", "sans-serif")
    title_font = (layout.get("fonts") or theme.get("fonts", {})).get("title", body_font)
    paths = []
    for slide in layout.get("slides", []):
        n = slide.get("slide_no", 0)
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" '
            'viewBox="0 0 %.0f %.0f">' % (w_pt, h_pt, w_pt, h_pt),
            '<rect x="0" y="0" width="%.0f" height="%.0f" fill="%s"/>' % (w_pt, h_pt, bg),
        ]
        for kind, box, size_pt, lines in _slide_boxes(slide):
            x = box["x"] / EMU_PER_PT
            y = box["y"] / EMU_PER_PT
            w = box["w"] / EMU_PER_PT
            h = box["h"] / EMU_PER_PT
            if kind == "image":
                parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                             'fill="#EEEEEE" stroke="%s" stroke-width="1"/>'
                             % (x, y, w, h, acc3))
            color = acc1 if kind == "title" else (acc3 if kind == "source" else txt)
            font = title_font if kind == "title" else body_font
            line_h = size_pt * 1.25
            for i, ln in enumerate(lines):
                ty = y + 4 + (i + 0.8) * line_h
                if ty > y + h + line_h:
                    break
                parts.append('<text x="%.1f" y="%.1f" font-family="%s" '
                             'font-size="%.1f" fill="%s">%s</text>'
                             % (x + 4, ty, escape(font), size_pt, color,
                                escape(ln)))
        foot = slide.get("footer") or ""
        if foot:
            parts.append('<text x="44" y="%.1f" font-family="%s" font-size="9" '
                         'fill="%s">%s</text>'
                         % (h_pt - 12, escape(body_font), acc3, escape(foot[:80])))
        parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="9" '
                     'fill="%s" text-anchor="end">%s</text>'
                     % (w_pt - 30, h_pt - 12, escape(body_font), acc3,
                        slide.get("slide_no", "")))
        parts.append("</svg>")
        path = os.path.join(out_dir, "slide-%02d.svg" % n)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(parts) + "\n")
        paths.append(path)
    return paths


def render_png(layout, theme, out_dir):
    """Rasterize the same geometry with matplotlib. Returns [] if unavailable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    w_pt = layout["slide_w_emu"] / EMU_PER_PT
    h_pt = layout["slide_h_emu"] / EMU_PER_PT
    colors = layout.get("colors") or theme.get("colors", {})
    bg = _hex(colors, "bg", "#FFFFFF")
    txt = _hex(colors, "text", "#000000")
    acc1 = _hex(colors, "accent1", "#4472C4")
    acc3 = _hex(colors, "accent3", "#A5A5A5")
    paths = []
    for slide in layout.get("slides", []):
        n = slide.get("slide_no", 0)
        fig = plt.figure(figsize=(w_pt / 72.0, h_pt / 72.0), dpi=110)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, w_pt)
        ax.set_ylim(h_pt, 0)
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), w_pt, h_pt, color=bg, zorder=0))
        for kind, box, size_pt, lines in _slide_boxes(slide):
            x = box["x"] / EMU_PER_PT
            y = box["y"] / EMU_PER_PT
            w = box["w"] / EMU_PER_PT
            h = box["h"] / EMU_PER_PT
            if kind == "image":
                ax.add_patch(plt.Rectangle((x, y), w, h, facecolor="#EEEEEE",
                                           edgecolor=acc3, lw=0.8, zorder=1))
            color = acc1 if kind == "title" else (acc3 if kind == "source" else txt)
            line_h = size_pt * 1.25
            for i, ln in enumerate(lines):
                ty = y + 4 + (i + 0.8) * line_h
                if ty > y + h + line_h:
                    break
                ax.text(x + 4, ty, ln, fontsize=size_pt * 0.92, color=color,
                        ha="left", va="baseline", zorder=2,
                        fontweight="bold" if kind == "title" else "normal")
        foot = slide.get("footer") or ""
        if foot:
            ax.text(44, h_pt - 12, foot[:80], fontsize=8, color=acc3,
                    ha="left", va="baseline")
        ax.text(w_pt - 30, h_pt - 12, str(slide.get("slide_no", "")),
                fontsize=8, color=acc3, ha="right", va="baseline")
        path = os.path.join(out_dir, "slide-%02d.png" % n)
        fig.savefig(path, dpi=110)
        plt.close(fig)
        paths.append(path)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render layout geometry previews.")
    ap.add_argument("--layout", required=True)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("CASE_OUTPUT_DIR", "/app/output"), "preview"))
    args = ap.parse_args(argv)

    with open(args.layout, encoding="utf-8") as fh:
        layout = json.load(fh)
    with open(args.theme, encoding="utf-8") as fh:
        theme = json.load(fh)
    os.makedirs(args.out, exist_ok=True)
    svgs = render_svg(layout, theme, args.out)
    pngs = render_png(layout, theme, args.out)
    print("preview_render: %d SVG(s)%s -> %s"
          % (len(svgs),
             ", %d PNG(s) via matplotlib" % len(pngs) if pngs
             else ", matplotlib unavailable (SVG only)", args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
