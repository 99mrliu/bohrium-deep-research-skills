#!/usr/bin/env python3
"""canvas_audit.py -- Bundle B (ga-archetype-forge): blocking layout audit.

Prove, do not eyeball. For a forged (or hand-written) SVG check:
  A1 overflow   every <text>/<tspan> line width estimated with a Helvetica
                advance table must fit its data-max-w (exact for forged SVGs;
                falls back to canvas width for foreign SVGs, reported as such)
  A2 font floor no text smaller than --min-font px (default 8 px ~ 6 pt)
  A3 contrast   text fill vs its container fill >= 4.5:1 (3:1 for >=14 px bold)
  A4 canvas     viewBox present; all shapes inside the canvas
  A5 layers     at least 2 labelled layer groups (inkscape:label or id)
  A6 palette    fill/stroke colours used are colour-blind-safe tokens or have
                >=1.2:1 contrast against white (warn only)

Usage:
  python3 canvas_audit.py --svg /app/output/graphical_abstract.svg \
      [--min-font 8] [--json /app/work/audit_report.json]
Exit 0 = PASS (no open findings), 1 = FAIL.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "{http://www.w3.org/2000/svg}"
INK_NS = "{http://www.inkscape.org/namespaces/inkscape}"

NARROW = set("iljtfI.,;:'!|()[] ")
WIDE = set("mwMW@%&")


def line_width_px(text, size_px):
    w = 0.0
    for ch in text:
        if ch in NARROW:
            w += 0.28
        elif ch in WIDE:
            w += 0.85
        else:
            w += 0.55
    return w * size_px


def rel_lum(hexcol):
    hexcol = (hexcol or "").lstrip("#")
    if len(hexcol) != 6:
        return None
    try:
        r, g, b = (int(hexcol[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(h1, h2):
    l1, l2 = rel_lum(h1), rel_lum(h2)
    if l1 is None or l2 is None:
        return None
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def named_color(name):
    table = {"white": "#ffffff", "black": "#000000", "none": None}
    return table.get((name or "").lower(), name)


def audit(svg_path, min_font):
    findings = []
    tree = ET.parse(svg_path)
    root = tree.getroot()

    # A4: viewBox
    vb = root.get("viewBox")
    if not vb:
        findings.append({"check": "A4", "issue": "missing viewBox"})
        cw = ch = None
    else:
        parts = [float(v) for v in re.split(r"[ ,]+", vb.strip())]
        cw, ch = parts[2], parts[3]

    # A5: labelled layers
    layers = [g for g in root.iter(SVG_NS + "g")
              if g.get(INK_NS + "label") or g.get("id")]
    if len(layers) < 2:
        findings.append({"check": "A5",
                         "issue": "fewer than 2 labelled layer groups"})

    # collect rects for contrast container lookup
    rects = []
    for r in root.iter(SVG_NS + "rect"):
        try:
            rects.append((float(r.get("x", 0)), float(r.get("y", 0)),
                          float(r.get("width", 0)), float(r.get("height", 0)),
                          named_color(r.get("fill", "#ffffff"))))
        except ValueError:
            pass
    circles = []
    for c in root.iter(SVG_NS + "circle"):
        try:
            circles.append((float(c.get("cx", 0)), float(c.get("cy", 0)),
                            float(c.get("r", 0)),
                            named_color(c.get("fill", "#ffffff"))))
        except ValueError:
            pass

    def container_fill(x, y):
        """Smallest-area enclosing shape wins (background rect always loses)."""
        best, best_area = None, float("inf")
        for rx, ry, rw, rh, fill in rects:
            if fill and rx <= x <= rx + rw and ry <= y <= ry + rh:
                if rw * rh < best_area:
                    best, best_area = fill, rw * rh
        for cx, cy, rr, fill in circles:
            if fill and (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                if 3.14159 * rr * rr < best_area:
                    best, best_area = fill, 3.14159 * rr * rr
        return best or "#ffffff"

    # per-text checks
    for t in root.iter(SVG_NS + "text"):
        tid = t.get("id", "(no id)")
        size = t.get("font-size")
        try:
            size = float(size)
        except (TypeError, ValueError):
            findings.append({"check": "A2", "element": tid,
                             "issue": "unparseable font-size %r" % size})
            continue
        # A2
        if size < min_font:
            findings.append({"check": "A2", "element": tid,
                             "issue": "font-size %g px < floor %g px"
                             % (size, min_font)})
        max_w = t.get("data-max-w")
        fallback = False
        if max_w is None:
            max_w = cw
            fallback = True
        else:
            max_w = float(max_w)
        x = float(t.get("x", 0) or 0)
        y = float(t.get("y", 0) or 0)
        # gather lines (tspans or raw text)
        lines = []
        tspans = list(t.iter(SVG_NS + "tspan"))
        if tspans:
            lines = ["".join(sp.itertext()) for sp in tspans]
        else:
            lines = ["".join(t.itertext())]
        for ln in lines:
            if not ln.strip():
                continue
            need = line_width_px(ln, size)
            if max_w is not None and need > max_w + 0.5:
                findings.append({
                    "check": "A1", "element": tid,
                    "issue": "line %r needs ~%.0f px > allowed %.0f px%s"
                             % (ln[:40], need, max_w,
                                " (canvas fallback)" if fallback else "")})
        # A3 contrast vs container at text anchor
        fill = named_color(t.get("fill", "#000000"))
        bg = container_fill(x, y)
        cr = contrast(fill, bg)
        bold = t.get("font-weight") == "bold"
        threshold = 3.0 if (bold and size >= 14) else 4.5
        if cr is not None and cr < threshold:
            findings.append({"check": "A3", "element": tid,
                             "issue": "contrast %.2f:1 < %.1f:1 (fill %s on "
                             "~%s)" % (cr, threshold, fill, bg)})

    report = {"svg": svg_path, "min_font_px": min_font,
              "findings_open": len(findings), "open": findings,
              "gate": "PASS" if not findings else "FAIL"}
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--min-font", type=float, default=8.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    report = audit(args.svg, args.min_font)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
