#!/usr/bin/env python3
"""export_preview.py - render SVG to PDF + PNG previews, gracefully.

Chain: soffice --headless --convert-to pdf  ->  pdftoppm -r DPI -png.
Fallbacks: soffice direct png; if soffice is absent the manifest records
status "renderer_unavailable" and the script still exits 0 (never crash on
missing tools; disclose in result.json).

Usage:
    python3 export_preview.py figure.svg --out-dir /app/output \
        --manifest /app/output/export_manifest.json [--dpi 300]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

VERSION = "1.0.0"
SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice", "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice", "/snap/bin/libreoffice",
]


def find_tool(names, extra_paths=()):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for p in extra_paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


def run(cmd, timeout):
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), \
            proc.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, "", str(exc)


def tool_version(path, args=("--version",)):
    rc, out, err = run([path] + list(args), 30)
    txt = (out or err).strip().splitlines()
    return txt[0][:120] if txt else "unknown (rc=%s)" % rc


def svg_size_mm(svg_path):
    try:
        with open(svg_path, "r", encoding="utf-8") as fh:
            head = fh.read(4000)
        def dim(attr):
            m = re.search(attr + r'="([\d.]+)mm"', head)
            return float(m.group(1)) if m else None
        return dim("width"), dim("height")
    except OSError:
        return None, None


def font_summary(fc_list):
    if not fc_list:
        return {"available": False,
                "note": "fc-list not found; font check skipped. "
                        "Verify no tofu boxes by inspecting the PNG preview."}
    rc, out, err = run([fc_list, ":", "family"], 30)
    if rc != 0:
        return {"available": False, "note": "fc-list failed: %s" % err[:100]}
    fams = sorted({ln.strip() for ln in out.splitlines() if ln.strip()})
    cjk = [f for f in fams if any(k in f for k in (
        "CJK", "Han", "Hei", "Song", "WenQuanYi", "AR PL", "Noto Sans SC"))]
    return {"available": True, "n_families": len(fams),
            "cjk_families": cjk[:10],
            "note": "no CJK font found; CJK labels will render as tofu boxes"
                    if not cjk else "CJK fonts present"}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Export SVG to PDF+PNG previews; graceful on missing "
                    "renderers; always exits 0.")
    ap.add_argument("svg", help="input SVG")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args(argv)

    t0 = time.time()
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.svg))[0]
    pdf_path = os.path.join(out_dir, base + ".pdf")
    png_path = os.path.join(out_dir, base + ".png")
    w_mm, h_mm = svg_size_mm(args.svg)

    manifest = {
        "tool": "export_preview/" + VERSION,
        "input_svg": os.path.abspath(args.svg),
        "width_mm": w_mm, "height_mm": h_mm, "dpi_requested": args.dpi,
        "tool_versions": {}, "font_summary": None,
        "outputs": [], "deviations": [], "status": "ok",
        "elapsed_sec": None,
    }

    soffice = find_tool(["soffice", "libreoffice"], SOFFICE_CANDIDATES)
    pdftoppm = find_tool(["pdftoppm"])
    fc_list = find_tool(["fc-list"])
    manifest["font_summary"] = font_summary(fc_list)
    manifest["tool_versions"]["soffice"] = (
        tool_version(soffice) if soffice else "NOT FOUND")
    manifest["tool_versions"]["pdftoppm"] = (
        tool_version(pdftoppm, ("-v",)) if pdftoppm else "NOT FOUND")
    manifest["tool_versions"]["fc-list"] = (
        "present" if fc_list else "NOT FOUND")

    pdf_ok, png_ok = False, False
    if not os.path.exists(args.svg):
        manifest["status"] = "failed"
        manifest["deviations"].append("input SVG missing: %s" % args.svg)
    elif not soffice:
        manifest["status"] = "renderer_unavailable"
        manifest["deviations"].append(
            "soffice/libreoffice not found: PDF and PNG previews not "
            "produced. SVG source at %s is the authoritative deliverable; "
            "disclose renderer_unavailable in result.json." % args.svg)
    else:
        rc, out, err = run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", out_dir, args.svg], 180)
        if rc == 0 and os.path.exists(pdf_path) and \
                os.path.getsize(pdf_path) > 0:
            pdf_ok = True
            manifest["outputs"].append(
                {"path": pdf_path, "format": "pdf", "width_mm": w_mm,
                 "height_mm": h_mm, "via": "soffice"})
        else:
            manifest["deviations"].append(
                "soffice pdf conversion failed (rc=%s): %s"
                % (rc, (err or out)[-200:]))
        if pdf_ok and pdftoppm:
            prefix = os.path.join(out_dir, base + "_png")
            rc, out, err = run([pdftoppm, "-r", str(args.dpi), "-png",
                                "-singlefile", pdf_path, prefix], 120)
            cand = prefix + ".png"
            if rc == 0 and os.path.exists(cand):
                if cand != png_path:
                    os.replace(cand, png_path)
                png_ok = True
                manifest["outputs"].append(
                    {"path": png_path, "format": "png", "dpi": args.dpi,
                     "width_mm": w_mm, "height_mm": h_mm,
                     "via": "pdf->pdftoppm"})
            else:
                manifest["deviations"].append(
                    "pdftoppm failed (rc=%s): %s" % (rc, err[-200:]))
        if not png_ok:
            rc, out, err = run([soffice, "--headless", "--convert-to", "png",
                                "--outdir", out_dir, args.svg], 180)
            if rc == 0 and os.path.exists(png_path) and \
                    os.path.getsize(png_path) > 0:
                png_ok = True
                manifest["outputs"].append(
                    {"path": png_path, "format": "png", "dpi": None,
                     "width_mm": w_mm, "height_mm": h_mm,
                     "via": "soffice direct (resolution not guaranteed)"})
                manifest["deviations"].append(
                    "PNG produced directly by soffice; dpi not controlled")
            else:
                manifest["deviations"].append(
                    "PNG export unavailable (rc=%s): %s"
                    % (rc, (err or out)[-200:]))
        if not pdf_ok and not png_ok:
            manifest["status"] = "failed"
        elif not (pdf_ok and png_ok):
            manifest["status"] = "partial"

    manifest["elapsed_sec"] = round(time.time() - t0, 2)
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
    print("export_preview %s: status=%s outputs=%d deviations=%d"
          % (VERSION, manifest["status"], len(manifest["outputs"]),
             len(manifest["deviations"])))
    for d in manifest["deviations"]:
        print("  DEVIATION %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
