#!/usr/bin/env python3
"""export_previews.py -- export a compiled PDF figure to PNG and/or SVG using
whatever exporters are on PATH, verify PNG pixels, print a JSON report.

Usage:
    python3 export_previews.py --pdf FILE --out-dir DIR --basename NAME [--dpi 300]

Detection (shutil.which), honest degradation:
  PNG : pdftoppm -r DPI -png            (preferred)
        pdftocairo -r DPI -png          (fallback)
  SVG : pdftocairo -svg | pdf2svg | dvisvgm (first found)
Missing PNG exporter -> no PNG, status "partial"/"failed", recorded.
Missing SVG exporter -> SVG skipped with explicit note (partial, not error).
PIL is OPTIONAL: if importable, PNG width/height and DPI metadata are verified;
if not, a note is recorded instead.

Exit codes: 0 all requested artifacts produced, 1 partial, 2 bad args,
3 no usable exporter at all.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

try:
    from PIL import Image  # optional
    HAVE_PIL = True
except Exception:
    Image = None
    HAVE_PIL = False


def which(name):
    return shutil.which(name)


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, text=True, errors="replace")
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def probe_png(png_path):
    """Return dict with size/dpi info; honest about PIL absence."""
    info = {"path": os.path.abspath(png_path),
            "bytes": os.path.getsize(png_path)}
    if HAVE_PIL:
        try:
            with Image.open(png_path) as im:
                info["width"], info["height"] = im.size
                dpi = im.info.get("dpi")
                if dpi:
                    info["dpi"] = [round(dpi[0], 1), round(dpi[1], 1)]
                info["mode"] = im.mode
        except Exception as exc:  # corrupt file etc.
            info["pil_error"] = str(exc)
    else:
        info["note"] = "PIL not available; pixel size not verified"
    return info


def export_png(pdf, out_prefix, dpi):
    """Try pdftoppm then pdftocairo. Return (path|None, exporter|None, notes)."""
    notes = []
    if which("pdftoppm"):
        rc, out = run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile",
                       pdf, out_prefix])
        cand = out_prefix + ".png"
        if rc == 0 and os.path.isfile(cand):
            return cand, "pdftoppm", notes
        notes.append("pdftoppm failed rc=%s: %s" % (rc, out.strip()[:300]))
    else:
        notes.append("pdftoppm not on PATH")
    if which("pdftocairo"):
        rc, out = run(["pdftocairo", "-r", str(dpi), "-png", "-singlefile",
                       pdf, out_prefix])
        cand = out_prefix + ".png"
        if rc == 0 and os.path.isfile(cand):
            return cand, "pdftocairo", notes
        notes.append("pdftocairo failed rc=%s: %s" % (rc, out.strip()[:300]))
    else:
        notes.append("pdftocairo not on PATH (PNG fallback unavailable)")
    return None, None, notes


def export_svg(pdf, svg_path):
    """Try pdftocairo -svg, pdf2svg, dvisvgm. Return (path|None, exporter|None, notes)."""
    notes = []
    if which("pdftocairo"):
        rc, out = run(["pdftocairo", "-svg", pdf, svg_path])
        if rc == 0 and os.path.isfile(svg_path):
            return svg_path, "pdftocairo", notes
        notes.append("pdftocairo -svg failed rc=%s: %s" % (rc, out.strip()[:300]))
    else:
        notes.append("pdftocairo not on PATH")
    if which("pdf2svg"):
        rc, out = run(["pdf2svg", pdf, svg_path])
        if rc == 0 and os.path.isfile(svg_path):
            return svg_path, "pdf2svg", notes
        notes.append("pdf2svg failed rc=%s: %s" % (rc, out.strip()[:300]))
    else:
        notes.append("pdf2svg not on PATH")
    if which("dvisvgm"):
        # dvisvgm handles PDF natively in recent versions.
        rc, out = run(["dvisvgm", "--pdf", "-o", svg_path, pdf])
        if rc == 0 and os.path.isfile(svg_path):
            return svg_path, "dvisvgm", notes
        notes.append("dvisvgm failed rc=%s: %s" % (rc, out.strip()[:300]))
    else:
        notes.append("dvisvgm not on PATH")
    return None, None, notes


def main():
    ap = argparse.ArgumentParser(description="Export PDF figure to PNG/SVG.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--basename", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    pdf = os.path.abspath(args.pdf)
    if not os.path.isfile(pdf):
        print(json.dumps({"success": False, "error": "pdf not found: %s" % pdf}))
        return 2
    os.makedirs(args.out_dir, exist_ok=True)
    prefix = os.path.join(args.out_dir, args.basename)

    artifacts, notes = [], []
    png_path, png_exporter, png_notes = export_png(pdf, prefix, args.dpi)
    notes += png_notes
    if png_path:
        a = probe_png(png_path)
        a["type"] = "png"
        a["exporter"] = png_exporter
        artifacts.append(a)

    svg_path = prefix + ".svg"
    svg_out, svg_exporter, svg_notes = export_svg(pdf, svg_path)
    notes += svg_notes
    if svg_out:
        artifacts.append({"type": "svg",
                          "path": os.path.abspath(svg_out),
                          "bytes": os.path.getsize(svg_out),
                          "exporter": svg_exporter})
    else:
        notes.append("SVG not produced: no working SVG exporter "
                     "(pdftocairo/pdf2svg/dvisvgm all unavailable or failed); "
                     "PDF remains the vector deliverable.")

    if not artifacts:
        status, rc = "failed", 3
    elif png_path is None or svg_out is None:
        status, rc = "partial", 1
    else:
        status, rc = "success", 0

    print(json.dumps({
        "status": status,
        "requested_dpi": args.dpi,
        "artifacts": artifacts,
        "notes": notes,
        "pil_available": HAVE_PIL,
    }, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
