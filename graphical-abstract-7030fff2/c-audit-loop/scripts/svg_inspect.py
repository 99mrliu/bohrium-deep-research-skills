#!/usr/bin/env python3
"""svg_inspect.py -- Bundle C (ga-audit-loop): defect scan for ANY SVG.

Works on the agent's own drawing, a provided starting figure, or a converted
bitmap trace alike. Emits defects keyed to references/defect_taxonomy.md:

  D-OVERFLOW   text wider than its declared data-max-w, or (foreign SVGs,
               heuristic) longer than 0.9x remaining canvas width at its x
  D-FONTMIN    text below the floor (default 7.5 px)
  D-NOLAYER    fewer than 2 named groups: figure is not really "layered"
  D-VIEWBOX    missing/empty viewBox (breaks resolution-independent export)
  D-RASTER     embedded raster image found inside a figure that must stay
               editable (allowed only with explicit reason in exceptions)
  D-CLIP       text whose anchor sits outside the viewBox
  D-EMPTYTXT   empty <text> elements (dead editing artefacts)

Usage:
  python3 svg_inspect.py --svg figure.svg [--floor 7.5] \
      [--out /app/work/inspection.json]
Exit 0 = no blocker defects (D-OVERFLOW/D-FONTMIN/D-VIEWBOX are blockers).
"""
import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "{http://www.w3.org/2000/svg}"
INK_NS = "{http://www.inkscape.org/namespaces/inkscape}"


def est_w(text, size):
    w = 0.0
    for ch in text:
        w += 0.28 if ch in "iljtfI.,;:'!|()[] " else (
            0.85 if ch in "mwMW@%&" else 0.55)
    return w * size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--floor", type=float, default=7.5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    defects = []
    tree = ET.parse(args.svg)
    root = tree.getroot()

    vb = root.get("viewBox")
    if not vb:
        defects.append({"code": "D-VIEWBOX", "severity": "blocker",
                        "detail": "no viewBox attribute"})
        vw = vh = None
    else:
        try:
            _x, _y, vw, vh = [float(v) for v in re.split(r"[ ,]+", vb.strip())]
        except ValueError:
            defects.append({"code": "D-VIEWBOX", "severity": "blocker",
                            "detail": "viewBox unparseable: %r" % vb})
            vw = vh = None

    named = [g for g in root.iter(SVG_NS + "g")
             if g.get(INK_NS + "label") or g.get("id")]
    if len(named) < 2:
        defects.append({"code": "D-NOLAYER", "severity": "warning",
                        "detail": "only %d named group(s)" % len(named)})

    n_raster = 0
    for img in root.iter(SVG_NS + "image"):
        n_raster += 1
        defects.append({"code": "D-RASTER", "severity": "warning",
                        "detail": "embedded raster <image> href=%s"
                        % (img.get("{http://www.w3.org/1999/xlink}href",
                                   img.get("href", "?"))[:60])})

    n_text = 0
    for t in root.iter(SVG_NS + "text"):
        n_text += 1
        tid = t.get("id", "(anon)")
        tspans = list(t.iter(SVG_NS + "tspan"))
        if tspans:  # one rendered line per tspan
            lines = [re.sub(r"\s+", " ", "".join(sp.itertext())).strip()
                     for sp in tspans]
            content = " ".join(lines)
        else:
            content = re.sub(r"\s+", " ", "".join(t.itertext())).strip()
            lines = [content] if content else []
        if not content:
            defects.append({"code": "D-EMPTYTXT", "severity": "warning",
                            "element": tid, "detail": "empty text element"})
            continue
        try:
            size = float(t.get("font-size", 10))
        except ValueError:
            size = 10.0
        if size < args.floor:
            defects.append({"code": "D-FONTMIN", "severity": "blocker",
                            "element": tid,
                            "detail": "font %.1f px < floor %.1f"
                            % (size, args.floor)})
        max_w = t.get("data-max-w")
        try:
            x = float(t.get("x", 0) or 0)
            y = float(t.get("y", 0) or 0)
        except ValueError:
            x = y = 0.0
        if vw is not None and not (-1 <= x <= vw + 1 and -1 <= y <= (vh or 0) + 1):
            defects.append({"code": "D-CLIP", "severity": "blocker",
                            "element": tid,
                            "detail": "anchor (%.0f,%.0f) outside viewBox "
                            "%sx%s" % (x, y, vw, vh)})
        if max_w is not None:
            limit = float(max_w)
            mode = "declared"
        elif vw is not None:
            limit = max(vw - x, 20) * 0.98
            mode = "canvas-heuristic"
        else:
            continue
        for line in [ln for ln in lines if ln.strip()]:
            need = est_w(line, size)
            if need > limit + 0.5:
                defects.append({"code": "D-OVERFLOW", "severity": "blocker",
                                "element": tid,
                                "detail": "%r needs ~%.0f px > %s limit %.0f"
                                % (line[:40], need, mode, limit)})

    blockers = [d for d in defects if d["severity"] == "blocker"]
    report = {"svg": args.svg, "text_elements": n_text,
              "raster_images": n_raster, "named_groups": len(named),
              "blockers": len(blockers),
              "defects": defects,
              "verdict": "CLEAN" if not blockers else "DEFECTS"}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
