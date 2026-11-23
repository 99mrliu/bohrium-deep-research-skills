#!/usr/bin/env python3
"""render_diff.py -- Bundle C (ga-audit-loop): export check + visual diff.

Two jobs:
  1) rasterise an SVG with the first available exporter (rsvg-convert,
     inkscape, soffice->pdftoppm) so the figure has a REAL rendered preview;
  2) optionally pixel-diff two PNGs (before/after an edit) and report the
     changed pixel fraction and bounding box, proving an edit touched only
     the intended region (or catching collateral damage).

Usage:
  python3 render_diff.py --svg figure.svg --png out.png [--dpi 300]
  python3 render_diff.py --before a.png --after b.png [--tolerance 0.02]
PNG reading uses matplotlib.image (scientific-python), no PIL required.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def rasterise(svg, png, dpi):
    attempts = []
    if shutil.which("rsvg-convert"):
        p = subprocess.run(["rsvg-convert", "-f", "png", "-d", str(dpi),
                            "-p", str(dpi), "-o", png, svg],
                           capture_output=True, text=True, timeout=180)
        attempts.append({"tool": "rsvg-convert", "rc": p.returncode})
        if p.returncode == 0 and os.path.exists(png):
            return "rsvg-convert", attempts
    if shutil.which("inkscape"):
        p = subprocess.run(["inkscape", svg, "--export-type=png",
                            "--export-dpi=%d" % dpi,
                            "--export-filename=%s" % png],
                           capture_output=True, text=True, timeout=240)
        attempts.append({"tool": "inkscape", "rc": p.returncode})
        if p.returncode == 0 and os.path.exists(png):
            return "inkscape", attempts
    if shutil.which("soffice") and shutil.which("pdftoppm"):
        outdir = os.path.dirname(os.path.abspath(png)) or "."
        p = subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, svg],
                           capture_output=True, text=True, timeout=240)
        pdf = os.path.join(outdir,
                           os.path.splitext(os.path.basename(svg))[0] + ".pdf")
        attempts.append({"tool": "soffice->pdf", "rc": p.returncode})
        if p.returncode == 0 and os.path.exists(pdf):
            prefix = os.path.splitext(png)[0]
            p2 = subprocess.run(["pdftoppm", "-r", str(dpi), "-png",
                                 "-singlefile", pdf, prefix],
                                capture_output=True, text=True, timeout=120)
            attempts.append({"tool": "pdftoppm", "rc": p2.returncode})
            if p2.returncode == 0 and os.path.exists(png):
                return "soffice+pdftoppm", attempts
    return None, attempts


def png_diff(before, after, tolerance):
    import matplotlib.image as mpimg
    import numpy as np
    a = mpimg.imread(before)
    b = mpimg.imread(after)
    if a.shape != b.shape:
        return {"error": "shape mismatch %s vs %s; cannot claim "
                "localised edit" % (a.shape, b.shape)}
    if a.dtype != np.uint8:
        a = (a * 255).round().astype("uint8")
    if b.dtype != np.uint8:
        b = (b * 255).round().astype("uint8")
    delta = np.abs(a.astype(int) - b.astype(int)).sum(axis=-1)
    mask = delta > 24  # ignore sub-quantisation noise
    frac = float(mask.mean())
    ys, xs = np.nonzero(mask)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] \
        if len(xs) else None
    h, w = mask.shape
    return {"changed_fraction": frac, "changed_bbox_px": bbox,
            "canvas_px": [w, h],
            "bbox_area_fraction": (None if bbox is None else
                                   ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
                                   / float(w * h)),
            "within_tolerance": frac <= tolerance}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--before", default=None)
    ap.add_argument("--after", default=None)
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    report = {}
    rc = 0
    if args.svg and args.png:
        tool, attempts = rasterise(args.svg, args.png, args.dpi)
        report["rasterise"] = {"tool": tool, "attempts": attempts,
                               "png": args.png if tool else None}
        if not tool:
            report["rasterise"]["status"] = "failed-no-exporter"
            rc = 1
    if args.before and args.after:
        report["diff"] = png_diff(args.before, args.after, args.tolerance)
        if report["diff"].get("error") or not report["diff"].get(
                "within_tolerance", False):
            rc = 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
