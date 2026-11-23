#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_pixels.py — pixel probes on the exported PNG.

Checks:
  png.openable          file exists and PIL can decode it          [error]
  png.dimensions        min dimension >= 100 px, aspect within 5%  [error]
                        of the SVG canvas aspect (if --svg given)
  png.nonempty          >= 6 distinct colors (blank-render guard)  [error]
  png.background        corner patches not unexpectedly dark       [warning]
  color.check           for each claims.color_checks entry: the    [error]
                        element's region (bbox found via --svg, or
                        explicit fractional "region" in the check)
                        is sampled and compared to expect_color_hex
                        within --tolerance (per channel)
  ocr.key_labels        if tesseract is on PATH: up to 3           [warning]
                        expected_labels must be OCR-detected.
                        If tesseract is missing -> SKIPPED WITH NOTE
                        (a skipped check is never counted as passed)

If PIL is unavailable the whole auditor reports itself skipped — never a
silent pass.

Usage:
  audit_pixels.py --png figure.png [--svg figure.svg] [--claims claims.json]
                  [--tolerance 24] --out violations.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402


def viol(check, severity, detail, element=None, source=None):
    return {"auditor": "pixels", "check": check, "severity": severity,
            "detail": detail, "element": element, "source": source}


def skip(check, note):
    return {"check": check, "note": note}


def region_median(im, box):
    """Median-ish (mean of center 50%) color of an int box region."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = im.crop((x0, y0, x1, y1)).convert("RGB")
    px = list(crop.getdata())
    px.sort()
    mid = px[len(px) // 2]
    return mid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", required=True)
    ap.add_argument("--svg")
    ap.add_argument("--claims")
    ap.add_argument("--tolerance", type=int, default=24)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    violations, skipped = [], []
    try:
        from PIL import Image
    except ImportError:
        result = {"auditor": "pixels", "violations": [], "skipped": [
            skip("pixels.*", "PIL not installed; all pixel checks skipped "
                             "(NOT counted as passed)")]}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print("pixels: skipped (PIL missing)")
        return 0

    if not os.path.exists(args.png):
        violations.append(viol("png.openable", "error",
                               "PNG not found: %s" % args.png))
        _emit(args.out, violations, skipped)
        return 0
    try:
        im = Image.open(args.png).convert("RGB")
    except Exception as exc:
        violations.append(viol("png.openable", "error",
                               "PIL cannot decode PNG: %s" % exc))
        _emit(args.out, violations, skipped)
        return 0

    # dimensions + aspect
    svg_root = None
    if args.svg and os.path.exists(args.svg):
        try:
            svg_root = C.parse_svg(args.svg).getroot()
        except Exception as exc:
            skipped.append(skip("png.aspect",
                                "SVG unparsable (%s); aspect check skipped"
                                % exc))
    if min(im.width, im.height) < 100:
        violations.append(viol(
            "png.dimensions", "error",
            "PNG too small: %dx%d px" % (im.width, im.height)))
    if svg_root is not None:
        sw, sh = C.svg_canvas_size(svg_root)
        if sw and sh:
            a_svg, a_png = sw / sh, im.width / im.height
            if abs(a_svg - a_png) / a_svg > 0.05:
                violations.append(viol(
                    "png.aspect", "error",
                    "aspect mismatch: SVG %.3f vs PNG %.3f" % (a_svg, a_png)))

    # blank-render guard
    try:
        colors = im.convert("RGB").getcolors(maxcolors=1 << 22)
        ncolors = len(colors) if colors is not None else (1 << 22) + 1
    except Exception:
        ncolors = -1
    if 0 <= ncolors < 6:
        violations.append(viol(
            "png.nonempty", "error",
            "only %d distinct colors; figure may not have rendered" % ncolors))

    # background darkness
    corner = 12
    patches = [(0, 0, corner, corner),
               (im.width - corner, 0, im.width, corner),
               (0, im.height - corner, corner, im.height),
               (im.width - corner, im.height - corner, im.width, im.height)]
    lums = []
    for p in patches:
        c = region_median(im, p)
        if c:
            lums.append(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    if lums and sum(lums) / len(lums) < 80:
        violations.append(viol(
            "png.background", "warning",
            "background unexpectedly dark (corner luminance %.0f)"
            % (sum(lums) / len(lums))))

    # color checks
    claims = {}
    if args.claims and os.path.exists(args.claims):
        with open(args.claims, encoding="utf-8") as fh:
            claims = json.load(fh)
    cchecks = claims.get("color_checks", [])
    if cchecks and svg_root is None:
        skipped.append(skip("color.check",
                            "%d color_checks present but no parseable --svg "
                            "to locate element regions; skipped" % len(cchecks)))
    for cc in cchecks:
        elid, expect = cc.get("element"), cc.get("expect_color_hex")
        exp_rgb = C.hex_to_rgb(expect or "")
        if exp_rgb is None:
            skipped.append(skip("color.check",
                                "color_check for '%s' has no valid "
                                "expect_color_hex" % elid))
            continue
        box = None
        if cc.get("region"):
            # region = [x0,y0,x1,y1] fractions of the canvas
            r = cc["region"]
            box = (r[0] * im.width, r[1] * im.height,
                   r[2] * im.width, r[3] * im.height)
        if box is None and svg_root is not None:
            bb = C.element_bbox(svg_root, elid)
            sw, sh = C.svg_canvas_size(svg_root)
            if bb and sw and sh:
                sx, sy = im.width / sw, im.height / sh
                # shrink sample region to the central 50% to dodge strokes
                x, y, w, h = bb
                box = ((x + w * 0.25) * sx, (y + h * 0.25) * sy,
                       (x + w * 0.75) * sx, (y + h * 0.75) * sy)
        if box is None:
            skipped.append(skip(
                "color.check",
                "could not locate region for element '%s'" % elid))
            continue
        got = region_median(im, box)
        if got is None:
            skipped.append(skip("color.check",
                                "empty sample region for '%s'" % elid))
            continue
        diff = max(abs(got[i] - exp_rgb[i]) for i in range(3))
        if diff > args.tolerance:
            violations.append(viol(
                "color.check", "error",
                "element '%s' (%s): expected %s, sampled #%02x%02x%02x "
                "(channel diff %d > tolerance %d)" % (
                    elid, cc.get("role", "?"), expect,
                    got[0], got[1], got[2], diff, args.tolerance),
                element=elid))

    # OCR presence check (skip-with-note if tesseract absent)
    tess = shutil.which("tesseract")
    key_labels = (claims.get("expected_labels") or [])[:3]
    if not key_labels:
        skipped.append(skip("ocr.key_labels",
                            "no expected_labels in claims; OCR check skipped"))
    elif tess is None:
        skipped.append(skip("ocr.key_labels",
                            "tesseract not on PATH; OCR label check skipped "
                            "(NOT counted as passed)"))
    else:
        try:
            out = subprocess.run([tess, args.png, "stdout"],
                                 capture_output=True, text=True,
                                 timeout=120).stdout
            for lab in key_labels:
                if lab.lower() not in out.lower():
                    violations.append(viol(
                        "ocr.key_labels", "warning",
                        "OCR did not detect key label '%s'" % lab,
                        element=lab))
        except Exception as exc:
            skipped.append(skip("ocr.key_labels",
                                "tesseract failed: %s" % exc))

    _emit(args.out, violations, skipped)
    errs = sum(1 for v in violations if v["severity"] == "error")
    print("pixels: %d errors, %d warnings, %d skipped" % (
        errs, len(violations) - errs, len(skipped)))
    return 0


def _emit(out, violations, skipped):
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"auditor": "pixels", "violations": violations,
                   "skipped": skipped}, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
