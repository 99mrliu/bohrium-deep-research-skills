#!/usr/bin/env python3
"""render_diff.py -- real render evidence for the finished pptx (pillar 3b).

Chain: soffice -> PDF -> pdftoppm -> PNG. Metrics: page-count match,
per-page PNG bytes, mean brightness, near-blank page detection, sha256
render hashes. When soffice or pdftoppm is missing the report says
rendered=false with tool_missing -- rendering is never faked.

Usage:
    python3 render_diff.py presentation.pptx --out-dir render/ \
        --report render_report.json [--profile /tmp/lo-c] [--dpi 100]
Exit 0 even on tool_missing (honest partial); 1 on render-quality failure.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib

SOFFICE_CANDIDATES = [
    os.environ.get("SOFFICE", ""),
    shutil.which("soffice") or "",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]


def find_soffice():
    for c in SOFFICE_CANDIDATES:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def png_brightness_pil(path):
    from PIL import Image  # soft import
    with Image.open(path) as im:
        g = im.convert("L")
        hist = g.histogram()
        total = sum(hist)
        mean = sum(i * c for i, c in enumerate(hist)) / total
        var = sum(c * (i - mean) ** 2 for i, c in enumerate(hist)) / total
        return mean, var ** 0.5


def png_brightness_stdlib(path):
    """Decode 8-bit RGB/RGBA/gray PNG (non-interlaced) with stdlib only."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, width, height, depth, ctype = 8, b"", 0, 0, 8, 2
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", chunk[:10])
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        pos += 12 + length
    if depth != 8 or ctype not in (0, 2, 6):
        raise ValueError("unsupported PNG (depth=%d ctype=%d)" % (depth, ctype))
    ch = {0: 1, 2: 3, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = width * ch
    prev = bytearray(stride)
    s = s2 = n = 0
    off = 0
    for _y in range(height):
        f = raw[off]
        line = bytearray(raw[off + 1:off + 1 + stride])
        off += 1 + stride
        for x in range(stride):
            a = line[x - ch] if x >= ch else 0
            b = prev[x]
            c = prev[x - ch] if x >= ch else 0
            if f == 1:
                line[x] = (line[x] + a) & 0xFF
            elif f == 2:
                line[x] = (line[x] + b) & 0xFF
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 0xFF
        prev = line
        for x in range(width):
            base = x * ch
            if ch == 1:
                lum = line[base]
            else:
                lum = (299 * line[base] + 587 * line[base + 1]
                       + 114 * line[base + 2]) // 1000
            s += lum
            s2 += lum * lum
            n += 1
    mean = s / n
    var = max(s2 / n - mean * mean, 0.0)
    return mean, var ** 0.5


def png_brightness(path):
    try:
        m, sd = png_brightness_pil(path)
        return m, sd, "PIL"
    except ImportError:
        m, sd = png_brightness_stdlib(path)
        return m, sd, "stdlib-png"


def main():
    ap = argparse.ArgumentParser(description="Render pptx via soffice and "
                                 "measure the output pages.")
    ap.add_argument("pptx")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--profile", default="/tmp/lo-c",
                    help="LibreOffice user profile dir (avoid conflicts)")
    ap.add_argument("--dpi", type=int, default=100)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    report = {"pptx": os.path.abspath(args.pptx), "rendered": False,
              "engine": None, "tool_missing": [], "pages": []}

    soffice = find_soffice()
    if not soffice:
        report["tool_missing"].append("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        report["tool_missing"].append("pdftoppm")
    if report["tool_missing"]:
        report["detail"] = ("render chain unavailable: %s; honestly not "
                            "rendered" % ", ".join(report["tool_missing"]))
        _write(args.report, report)
        print("render_diff: tool_missing=%s rendered=false -> %s"
              % (report["tool_missing"], args.report))
        return 0

    # pptx -> pdf
    env = dict(os.environ)
    cmd = [soffice, "--headless", "--norestore",
           "-env:UserInstallation=file://%s" % args.profile,
           "--convert-to", "pdf", "--outdir", args.out_dir, args.pptx]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                          env=env)
    base = os.path.splitext(os.path.basename(args.pptx))[0]
    pdf_path = os.path.join(args.out_dir, base + ".pdf")
    if proc.returncode != 0 or not os.path.isfile(pdf_path):
        report["detail"] = "soffice failed: %s %s" % (proc.stdout.strip(),
                                                      proc.stderr.strip())
        _write(args.report, report)
        print("render_diff: ERROR soffice conversion failed", file=sys.stderr)
        return 1

    # pdf -> png
    prefix = os.path.join(args.out_dir, "slide")
    subprocess.run([pdftoppm, "-png", "-r", str(args.dpi), pdf_path, prefix],
                   capture_output=True, text=True, timeout=300, check=False)
    pngs = sorted(glob.glob(prefix + "-*.png"))
    if not pngs:
        report["detail"] = "pdftoppm produced no PNGs"
        _write(args.report, report)
        return 1

    # slide count of source pptx
    n_slides = None
    try:
        from pptx import Presentation
        n_slides = len(Presentation(args.pptx).slides._sldIdLst)
    except Exception:
        pass

    near_blank = []
    for p in pngs:
        mean, sd, how = png_brightness(p)
        entry = {"file": os.path.basename(p), "bytes": os.path.getsize(p),
                 "mean_brightness": round(mean, 2), "stddev": round(sd, 2),
                 "brightness_engine": how, "sha256": sha256(p)}
        if mean > 248.0 and sd < 4.0:
            entry["near_blank"] = True
            near_blank.append(entry["file"])
        report["pages"].append(entry)

    report.update({
        "rendered": True,
        "engine": "soffice->pdf->pdftoppm",
        "pdf": os.path.abspath(pdf_path),
        "pdf_sha256": sha256(pdf_path),
        "page_count": len(pngs),
        "slide_count": n_slides,
        "page_match": (n_slides is None or len(pngs) == n_slides),
        "near_blank_pages": near_blank,
        "previews": [os.path.abspath(p) for p in pngs],
    })
    _write(args.report, report)
    fail = near_blank or (n_slides is not None and len(pngs) != n_slides)
    print("render_diff: rendered=true pages=%d slides=%s near_blank=%d -> %s"
          % (len(pngs), n_slides, len(near_blank), args.report))
    return 1 if fail else 0


def _write(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
