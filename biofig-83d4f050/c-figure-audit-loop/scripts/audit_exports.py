#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_exports.py — export-quality checks on the declared artifacts.

  artifact.exists        declared file present & non-trivial size   [error]
  png.dpi                PNG DPI metadata >= --min-dpi              [warning]
                         (missing metadata -> warning, not pass)
  pdf.structure          page count >= 1 and MediaBox parseable     [error]
                         (regex-based stdlib parse; best effort)
  pdf.fonts_embedded     pdffonts: every font emb=yes               [error]
                         pdffonts missing -> SKIPPED WITH NOTE
  pdf.text_present       pdftotext extracts non-empty text          [warning]
                         pdftotext missing -> SKIPPED WITH NOTE
  svg.wellformed         xml.etree parses the SVG                   [error]
  svg.raster_embedded    <image> elements present (editability)     [warning]
  svg.fonts_generic      font-family values in generic family list  [warning]

A skipped check is reported as skipped — never as a pass.

Usage:
  audit_exports.py [--svg f.svg] [--png f.png] [--pdf f.pdf]
                   [--min-dpi 150] --out violations.json
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402

MIN_SIZES = {".svg": 400, ".png": 2000, ".pdf": 800}


def viol(check, severity, detail, element=None, source=None):
    return {"auditor": "exports", "check": check, "severity": severity,
            "detail": detail, "element": element, "source": source}


def skip(check, note):
    return {"check": check, "note": note}


def check_exists(path, violations):
    ext = os.path.splitext(path)[1].lower()
    if not os.path.exists(path):
        violations.append(viol("artifact.exists", "error",
                               "declared artifact missing: %s" % path,
                               element=path))
        return False
    size = os.path.getsize(path)
    if size < MIN_SIZES.get(ext, 100):
        violations.append(viol(
            "artifact.exists", "error",
            "artifact suspiciously small: %s (%d bytes)" % (path, size),
            element=path))
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg")
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--min-dpi", type=int, default=150)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    violations, skipped = [], []

    # ---------------- SVG ----------------
    if args.svg:
        if check_exists(args.svg, violations):
            try:
                root = C.parse_svg(args.svg).getroot()
            except ET.ParseError as exc:
                violations.append(viol("svg.wellformed", "error",
                                       "SVG not well-formed: %s" % exc,
                                       element=args.svg))
                root = None
            if root is not None:
                images = [el for el in C.iter_elements(root, "image")]
                if images:
                    violations.append(viol(
                        "svg.raster_embedded", "warning",
                        "%d embedded raster <image> element(s); figure may "
                        "not be fully editable" % len(images),
                        element=args.svg))
                families = set()
                for el in root.iter():
                    ff = el.get("font-family")
                    if ff:
                        for fam in ff.split(","):
                            families.add(fam.strip().strip("'\"").lower())
                bad = sorted(f for f in families
                             if f and f not in C.GENERIC_FONT_FAMILIES)
                if bad:
                    violations.append(viol(
                        "svg.fonts_generic", "warning",
                        "non-generic font families used: %s (portability "
                        "risk)" % ", ".join(bad), element=args.svg))
    else:
        skipped.append(skip("svg.*", "no --svg declared"))

    # ---------------- PNG ----------------
    if args.png:
        if check_exists(args.png, violations):
            try:
                from PIL import Image
                with Image.open(args.png) as im:
                    dpi = im.info.get("dpi")
                if dpi is None:
                    violations.append(viol(
                        "png.dpi", "warning",
                        "PNG carries no DPI metadata; cannot verify "
                        "resolution", element=args.png))
                elif min(dpi) < args.min_dpi:
                    violations.append(viol(
                        "png.dpi", "warning",
                        "PNG DPI %.0f below minimum %d" % (min(dpi),
                                                           args.min_dpi),
                        element=args.png))
            except ImportError:
                skipped.append(skip("png.dpi",
                                    "PIL not installed; DPI check skipped"))
            except Exception as exc:
                violations.append(viol("png.dpi", "warning",
                                       "could not read PNG metadata: %s"
                                       % exc, element=args.png))
    else:
        skipped.append(skip("png.*", "no --png declared"))

    # ---------------- PDF ----------------
    if args.pdf:
        if check_exists(args.pdf, violations):
            with open(args.pdf, "rb") as fh:
                blob = fh.read()
            pages = len(re.findall(rb"/Type\s*/Page(?!s)", blob))
            mbox = re.search(rb"/MediaBox\s*\[([^\]]+)\]", blob)
            if pages < 1:
                violations.append(viol(
                    "pdf.structure", "error",
                    "no /Type /Page found; PDF may be broken",
                    element=args.pdf))
            if mbox is None:
                violations.append(viol(
                    "pdf.structure", "warning",
                    "no MediaBox found; page size unverifiable",
                    element=args.pdf))
            pdffonts = shutil.which("pdffonts")
            if pdffonts is None:
                skipped.append(skip(
                    "pdf.fonts_embedded",
                    "pdffonts not on PATH; embedded-font check skipped "
                    "(NOT counted as passed)"))
            else:
                try:
                    out = subprocess.run([pdffonts, args.pdf],
                                         capture_output=True, text=True,
                                         timeout=60).stdout
                    bad = []
                    for line in out.splitlines()[2:]:
                        cols = line.split()
                        if len(cols) >= 5 and cols[-4] == "no":
                            bad.append(cols[0])
                    if bad:
                        violations.append(viol(
                            "pdf.fonts_embedded", "error",
                            "fonts not embedded: %s" % ", ".join(bad),
                            element=args.pdf))
                except Exception as exc:
                    skipped.append(skip("pdf.fonts_embedded",
                                        "pdffonts failed: %s" % exc))
            pdftotext = shutil.which("pdftotext")
            if pdftotext is None:
                skipped.append(skip(
                    "pdf.text_present",
                    "pdftotext not on PATH; text-presence check skipped "
                    "(NOT counted as passed)"))
            else:
                try:
                    out = subprocess.run([pdftotext, args.pdf, "-"],
                                         capture_output=True, text=True,
                                         timeout=60).stdout.strip()
                    if len(out) < 3:
                        violations.append(viol(
                            "pdf.text_present", "warning",
                            "pdftotext extracted almost no text; labels may "
                            "be outlined/rasterized", element=args.pdf))
                except Exception as exc:
                    skipped.append(skip("pdf.text_present",
                                        "pdftotext failed: %s" % exc))
    else:
        skipped.append(skip("pdf.*", "no --pdf declared"))

    result = {"auditor": "exports", "violations": violations,
              "skipped": skipped}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    errs = sum(1 for v in violations if v["severity"] == "error")
    print("exports: %d errors, %d warnings, %d skipped" % (
        errs, len(violations) - errs, len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
