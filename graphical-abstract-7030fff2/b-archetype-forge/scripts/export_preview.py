#!/usr/bin/env python3
"""export_preview.py -- Bundle B (ga-archetype-forge): honest export chain.

Export the forged SVG to PDF and PNG with the first available tool, and write
an export report stating EXACTLY which tool ran (or that none did — a missing
exporter is an exception to record in result.json, never a silent skip).

Chain for PDF : rsvg-convert -> inkscape -> soffice (office-renderer)
Chain for PNG : rsvg-convert -> inkscape -> pdftoppm(from the PDF just made)

Usage:
  python3 export_preview.py --svg /app/output/graphical_abstract.svg \
      --outdir /app/output [--dpi 300] [--report /app/work/export_report.json]
Exit 0 if at least the SVG plus one export exists, 1 if everything failed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stderr or "")[-400:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.join(args.outdir, "graphical_abstract")
    pdf_path, png_path = base + ".pdf", base + ".png"
    report = {"svg": args.svg, "dpi": args.dpi, "attempts": [],
              "pdf": None, "png": None}

    # ---- PDF ----
    if shutil.which("rsvg-convert"):
        rc, err = run(["rsvg-convert", "-f", "pdf", "-o", pdf_path, args.svg])
        report["attempts"].append({"tool": "rsvg-convert", "target": "pdf",
                                   "rc": rc, "stderr": err})
    if not os.path.exists(pdf_path) and shutil.which("inkscape"):
        rc, err = run(["inkscape", args.svg, "--export-type=pdf",
                       "--export-filename=%s" % pdf_path])
        report["attempts"].append({"tool": "inkscape", "target": "pdf",
                                   "rc": rc, "stderr": err})
    if not os.path.exists(pdf_path) and shutil.which("soffice"):
        rc, err = run(["soffice", "--headless", "--convert-to", "pdf",
                       "--outdir", args.outdir, args.svg])
        report["attempts"].append({"tool": "soffice", "target": "pdf",
                                   "rc": rc, "stderr": err})
    if os.path.exists(pdf_path):
        report["pdf"] = {"path": pdf_path, "bytes": os.path.getsize(pdf_path)}

    # ---- PNG ----
    if shutil.which("rsvg-convert"):
        rc, err = run(["rsvg-convert", "-d", str(args.dpi), "-p", str(args.dpi),
                       "-f", "png", "-o", png_path, args.svg])
        report["attempts"].append({"tool": "rsvg-convert", "target": "png",
                                   "rc": rc, "stderr": err})
    if not os.path.exists(png_path) and shutil.which("inkscape"):
        rc, err = run(["inkscape", args.svg, "--export-type=png",
                       "--export-dpi=%d" % args.dpi,
                       "--export-filename=%s" % png_path])
        report["attempts"].append({"tool": "inkscape", "target": "png",
                                   "rc": rc, "stderr": err})
    if not os.path.exists(png_path) and os.path.exists(pdf_path) \
            and shutil.which("pdftoppm"):
        prefix = base
        rc, err = run(["pdftoppm", "-r", str(args.dpi), "-png", "-singlefile",
                       pdf_path, prefix])
        report["attempts"].append({"tool": "pdftoppm", "target": "png",
                                   "rc": rc, "stderr": err})
    if os.path.exists(png_path):
        report["png"] = {"path": png_path, "bytes": os.path.getsize(png_path)}

    report["status"] = ("ok" if report["pdf"] and report["png"]
                        else "partial" if (report["pdf"] or report["png"])
                        else "failed")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
