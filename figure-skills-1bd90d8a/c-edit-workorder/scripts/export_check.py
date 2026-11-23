#!/usr/bin/env python3
"""export_check.py - compliance check of exported figure files vs a preset.

PURE STDLIB.  Always exits 0; the report carries per-check status
(pass / warn / fail / skipped).  Checks:
  svg_width_mm    SVG root width == preset width_mm (tolerance +/-1 mm)
  png_dpi         PNG pHYs chunk dpi >= preset dpi (skipped if PNG absent)
  pdf_mediabox    PDF MediaBox width ~= preset width_mm (skipped if absent)
  editable_text   SVG contains real <text> elements (not all outlines)
  font_family     text elements declare a font-family (fallback list noted)
  background      transparent background only if preset allows it
  font_floor      text sizes at final scale within [font_min_pt, font_max_pt]

Usage:
  python3 export_check.py figure.svg figure.pdf figure.png \
      --preset nature_double --report export_check.json
"""
import argparse
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

NUM = r"-?\d+\.?\d*(?:[eE][-+]?\d+)?"
UNIT_TO_MM = {"mm": 1.0, "pt": 25.4 / 72, "in": 25.4, "cm": 10.0,
              "px": 25.4 / 96, "": 25.4 / 96}


def local(tag):
    return tag.split("}")[-1]


def parse_len_mm(s):
    if not s:
        return None
    m = re.match(r"^\s*(%s)\s*([a-z]*)\s*$" % NUM, s)
    if not m:
        return None
    return float(m.group(1)) * UNIT_TO_MM.get(m.group(2), 25.4 / 96)


def png_dpi(path):
    with open(path, "rb") as fh:
        data = fh.read(8)
        if data != b"\x89PNG\r\n\x1a\n":
            return None
        while True:
            hdr = fh.read(8)
            if len(hdr) < 8:
                return None
            length, ctype = struct.unpack(">I4s", hdr)
            body = fh.read(length + 4)
            if ctype == b"pHYs" and length >= 9:
                xppm, yppm, unit = struct.unpack(">IIB", body[:9])
                if unit == 1:
                    return xppm * 0.0254
                return None
            if ctype == b"IEND":
                return None


def pdf_mediabox_mm(path):
    with open(path, "rb") as fh:
        data = fh.read()
    m = re.search(rb"/MediaBox\s*\[([\d.\s]+)\]", data)
    if not m:
        return None
    nums = [float(t) for t in m.group(1).split()]
    if len(nums) != 4:
        return None
    return [(nums[2] - nums[0]) * 25.4 / 72, (nums[3] - nums[1]) * 25.4 / 72]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg")
    ap.add_argument("pdf", nargs="?", default=None)
    ap.add_argument("png", nargs="?", default=None)
    ap.add_argument("--preset", default="generic")
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "presets", "journal_presets.json"),
              encoding="utf-8") as fh:
        presets = json.load(fh)["presets"]
    preset = presets.get(args.preset, presets["generic"])

    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})
        print("%-16s %-7s %s" % (name, status, detail))

    # svg width
    try:
        tree = ET.parse(args.svg)
        root = tree.getroot()
        w_mm = parse_len_mm(root.get("width"))
        target = float(preset["width_mm"])
        if w_mm is None:
            add("svg_width_mm", "warn", "SVG width attribute unparseable")
        elif abs(w_mm - target) <= 1.0:
            add("svg_width_mm", "pass", "%.2f mm vs preset %.2f mm"
                % (w_mm, target))
        else:
            add("svg_width_mm", "fail", "%.2f mm vs preset %.2f mm (>1mm off)"
                % (w_mm, target))
    except ET.ParseError as exc:
        add("svg_width_mm", "fail", "SVG unparseable: %s" % exc)
        root = None

    # editable text + fonts + background
    if root is not None:
        texts = [el for el in root.iter() if local(el.tag) == "text"]
        paths = sum(1 for el in root.iter() if local(el.tag) == "path")
        if texts:
            add("editable_text", "pass",
                "%d <text> elements present (%d paths)" % (len(texts), paths))
        else:
            add("editable_text", "fail",
                "no <text> elements; labels are outlined and not editable")
        fams = set()
        single_only = True
        for t in texts:
            m = re.search(r"font-family:\s*([^;]+)", t.get("style") or "")
            if m:
                fams.add(m.group(1).strip())
                if "," in m.group(1):
                    single_only = False
        if not fams:
            add("font_family", "warn", "no font-family declared on <text>")
        elif single_only:
            add("font_family", "warn",
                "font-family present but without fallback list: %s"
                % sorted(fams)[:3])
        else:
            add("font_family", "pass", "families with fallbacks: %s"
                % sorted(fams)[:2])
        # font floor at final scale.  matplotlib writes pt-based user units
        # (1 unit = 1/72 in); generic SVG uses px (1/96 in) - sniff which.
        vb = (root.get("viewBox") or "").split()
        if w_mm and len(vb) == 4 and float(vb[2]) > 0:
            with open(args.svg, "rb") as fh:
                head = fh.read(4096)
            unit_in = 25.4 / 72 if b"matplotlib" in head.lower() \
                else 25.4 / 96
            scale = w_mm / (float(vb[2]) * unit_in)
            sizes = []
            for t in texts:
                m = re.search(r"font-size:\s*(%s)" % NUM, t.get("style") or "")
                if m:
                    sizes.append(float(m.group(1)) * scale)
            fmin, fmax = preset.get("font_min_pt"), preset.get("font_max_pt")
            bad = [round(s, 2) for s in sizes
                   if (fmin and s < fmin) or (fmax and s > fmax)]
            if not sizes:
                add("font_floor", "warn", "no font-size attributes found")
            elif bad:
                add("font_floor", "warn",
                    "sizes outside [%s, %s] pt: %s" % (fmin, fmax, bad))
            else:
                add("font_floor", "pass",
                    "all %d sizes within [%s, %s] pt" % (len(sizes), fmin, fmax))
        else:
            add("font_floor", "skipped", "cannot determine final scale")
        # background
        bg_rect = None
        if len(vb) == 4:
            vw, vh = float(vb[2]), float(vb[3])
            for el in root.iter():
                if local(el.tag) == "rect":
                    try:
                        rw = float(el.get("width", 0))
                        rh = float(el.get("height", 0))
                    except ValueError:
                        continue
                    if rw >= 0.98 * vw and rh >= 0.98 * vh:
                        st = el.get("style", "") + " " + (el.get("fill") or "")
                        bg_rect = st
                        break
        transparent_allowed = preset.get("transparent_allowed", False)
        if bg_rect is None:
            if transparent_allowed:
                add("background", "pass",
                    "no full-canvas rect; transparent allowed by preset")
            else:
                add("background", "warn",
                    "no full-canvas background rect (likely transparent); "
                    "preset expects %s - add a white rect if the journal "
                    "requires it" % preset.get("background", "white"))
        else:
            add("background", "pass",
                "full-canvas background rect found (%s)" % bg_rect[:60])

    # png dpi
    if args.png and os.path.exists(args.png):
        try:
            dpi = png_dpi(args.png)
            if dpi is None:
                add("png_dpi", "warn", "no pHYs chunk; dpi unknown")
            elif dpi >= float(preset["dpi"]) - 1.0:  # ppm->dpi rounding slack
                add("png_dpi", "pass", "%.0f dpi >= preset %s"
                    % (dpi, preset["dpi"]))
            else:
                add("png_dpi", "fail", "%.0f dpi < preset %s"
                    % (dpi, preset["dpi"]))
        except OSError as exc:
            add("png_dpi", "fail", "cannot read PNG: %s" % exc)
    else:
        add("png_dpi", "skipped", "PNG not present")

    # pdf mediabox
    if args.pdf and os.path.exists(args.pdf):
        try:
            mb = pdf_mediabox_mm(args.pdf)
            if mb is None:
                add("pdf_mediabox", "warn", "MediaBox not found in PDF")
            elif abs(mb[0] - float(preset["width_mm"])) <= 2.0:
                add("pdf_mediabox", "pass",
                    "MediaBox %.1fx%.1f mm" % (mb[0], mb[1]))
            else:
                add("pdf_mediabox", "warn",
                    "MediaBox width %.1f mm vs preset %.1f mm"
                    % (mb[0], float(preset["width_mm"])))
        except OSError as exc:
            add("pdf_mediabox", "fail", "cannot read PDF: %s" % exc)
    else:
        add("pdf_mediabox", "skipped", "PDF not present")

    counts = {s: sum(1 for c in checks if c["status"] == s)
              for s in ("pass", "warn", "fail", "skipped")}
    report = {"preset": args.preset, "checks": checks, "summary": counts}
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("summary: %s -> %s" % (counts, args.report))
    sys.exit(0)


if __name__ == "__main__":
    main()
