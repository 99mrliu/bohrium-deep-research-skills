#!/usr/bin/env python3
"""export_check.py -- export-format compliance checks (pure stdlib).

  PNG : IHDR width/height in px, pHYs chunk -> dpi (fail if dpi unspecified
        or < required, default 300).
  PDF : /MediaBox -> page size in mm; page count.
  SVG : width/height/viewBox present; contains real <text> (editable);
        font-family fallback list present.

Usage:
  python3 export_check.py figure.svg figure.png figure.pdf \
      --report export_report.json [--dpi 300]
Always exits 0.
"""
import sys
import os
import re
import json
import struct
import argparse


def check_png(path, need_dpi, checks):
    cid = "png"
    if not os.path.isfile(path):
        checks.append({"id": cid, "status": "fail",
                       "detail": "file missing: %s" % path})
        return
    with open(path, "rb") as f:
        data = f.read(65536)
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        checks.append({"id": cid, "status": "fail",
                       "detail": "not a PNG (bad magic)"})
        return
    w, h = struct.unpack(">II", data[16:24])
    checks.append({"id": "png_size", "status": "pass",
                   "detail": "%d x %d px" % (w, h)})
    # find pHYs chunk
    off = 8
    dpi = None
    while off + 8 <= len(data):
        (length,) = struct.unpack(">I", data[off:off + 4])
        ctype = data[off + 4:off + 8]
        if ctype == b"pHYs":
            ppu_x, ppu_y, unit = struct.unpack(">IIB",
                                               data[off + 8:off + 8 + 9])
            if unit == 1 and ppu_x:
                dpi = ppu_x * 0.0254
            break
        off += 12 + length
    if dpi is None:
        checks.append({"id": "png_dpi", "status": "fail",
                       "detail": "pHYs chunk missing -> dpi unspecified; "
                                 "re-save with explicit dpi metadata",
                       "repair": {"action": "redraw", "target": "png",
                                  "suggestion": "fig.savefig(path, dpi=300)"}})
    elif dpi + 0.5 < need_dpi:
        checks.append({"id": "png_dpi", "status": "fail",
                       "detail": "dpi=%.0f < required %d" % (dpi, need_dpi),
                       "repair": {"action": "redraw", "target": "png",
                                  "suggestion": "re-export at dpi=%d" %
                                  need_dpi}})
    else:
        checks.append({"id": "png_dpi", "status": "pass",
                       "detail": "dpi=%.0f >= %d" % (dpi, need_dpi)})


def check_pdf(path, checks):
    cid = "pdf"
    if not os.path.isfile(path):
        checks.append({"id": cid, "status": "fail",
                       "detail": "file missing: %s" % path})
        return
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"%PDF"):
        checks.append({"id": cid, "status": "fail",
                       "detail": "not a PDF (bad header)"})
        return
    m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
                  rb"([\d.]+)\s*\]", data)
    if m:
        x0, y0, x1, y1 = (float(v) for v in m.groups())
        w_mm = (x1 - x0) * 25.4 / 72.0
        h_mm = (y1 - y0) * 25.4 / 72.0
        checks.append({"id": "pdf_pagesize", "status": "pass",
                       "detail": "MediaBox %.1f x %.1f mm" % (w_mm, h_mm)})
    else:
        checks.append({"id": "pdf_pagesize", "status": "warn",
                       "detail": "MediaBox not found (compressed/xref "
                                 "streams?); page size unverified"})
    n_pages = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    checks.append({"id": "pdf_pages", "status": "pass",
                   "detail": "%d page(s)" % max(n_pages, 1)})
    if b"Font" not in data:
        checks.append({"id": "pdf_fonts", "status": "warn",
                       "detail": "no font objects found (all outlines?)"})
    else:
        checks.append({"id": "pdf_fonts", "status": "pass",
                       "detail": "font objects present"})


def check_svg(path, checks):
    cid = "svg"
    if not os.path.isfile(path):
        checks.append({"id": cid, "status": "fail",
                       "detail": "file missing: %s" % path})
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        head = f.read(200000)
    has_wh = re.search(r"<svg[^>]*\bwidth=\"[^\"]+\"[^>]*\bheight=\"[^\"]+\"",
                       head)
    has_vb = "viewBox" in head
    checks.append({"id": "svg_geometry", "status":
                   "pass" if (has_wh and has_vb) else "fail",
                   "detail": "width/height %s, viewBox %s" %
                   ("present" if has_wh else "MISSING",
                    "present" if has_vb else "MISSING")})
    n_text = head.count("<text")
    checks.append({"id": "svg_editable_text", "status":
                   "pass" if n_text > 0 else "fail",
                   "detail": "%d <text> elements (editable)" % n_text
                   if n_text else "no <text>: glyphs converted to outlines",
                   "repair": None if n_text else {
                       "action": "redraw", "target": "svg",
                       "suggestion": "set svg.fonttype='none'"}})
    fams = re.findall(r"font-family:\s*([^;\"]+)", head)
    has_fallback = any("," in f for f in fams)
    checks.append({"id": "svg_font_fallback", "status":
                   "pass" if (fams and has_fallback) else "warn",
                   "detail": ("%d font-family decls, fallback list %s" %
                              (len(fams), "present" if has_fallback
                               else "absent")) if fams else
                   "no font-family declarations found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--report", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    checks = []
    for p in args.files:
        low = p.lower()
        if low.endswith(".png"):
            check_png(p, args.dpi, checks)
        elif low.endswith(".pdf"):
            check_pdf(p, checks)
        elif low.endswith(".svg"):
            check_svg(p, checks)
        else:
            checks.append({"id": "unknown", "status": "warn",
                           "detail": "unrecognized file type: %s" % p})
    n_fail = sum(1 for c in checks if c["status"] == "fail")
    n_warn = sum(1 for c in checks if c["status"] == "warn")
    report = {"files": args.files,
              "checks": checks,
              "status": "fail" if n_fail else
                        ("pass_with_warnings" if n_warn else "pass")}
    outdir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(outdir or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("export_check: %s (fail=%d warn=%d)" %
          (report["status"], n_fail, n_warn))
    for c in checks:
        if c["status"] != "pass":
            print("  [%s] %s: %s" % (c["status"].upper(), c["id"],
                                     c["detail"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
