#!/usr/bin/env python3
"""export_journal.py - preset-driven journal export of a layered SVG.

PURE STDLIB.  Steps:
  1. Load the preset (presets/journal_presets.json next to this script).
  2. Rescale the SVG root width/height to the preset's width_mm, keeping the
     viewBox untouched so all vector geometry scales losslessly.  Text stays
     <text> (editable).
  3. Scan font sizes and compute effective pt at the final scale; record
     deviations below font_min_pt / above font_max_pt.
  4. Export PDF via `soffice --headless --convert-to pdf`; then PNG at the
     preset DPI via `pdftoppm -r <dpi>` from that PDF.  Fallbacks: soffice
     direct PNG; final fallback: status "renderer_unavailable" in the report
     (exit code stays 0 - honest degradation, not a crash).
  5. Write export_report.json {preset, outputs, tool_versions, font_summary,
     deviations}.

Usage:
  python3 export_journal.py /app/output/figure.svg --preset nature_double \
      --out-dir /app/output --report /app/output/export_report.json
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NUM = r"-?\d+\.?\d*(?:[eE][-+]?\d+)?"
UNIT_TO_MM = {"mm": 1.0, "pt": 25.4 / 72, "in": 25.4, "cm": 10.0,
              "px": 25.4 / 96, "": 25.4 / 96}


def local(tag):
    return tag.split("}")[-1]


def tool_version(cmd, args=("--version",)):
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True,
                             timeout=30)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        return "present (version query failed)"


def parse_len_mm(s):
    if s is None:
        return None
    m = re.match(r"^\s*(%s)\s*([a-z]*)\s*$" % NUM, s)
    if not m:
        return None
    return float(m.group(1)) * UNIT_TO_MM.get(m.group(2), 25.4 / 96)


def font_sizes_pt(root, scale):
    """Effective font sizes (pt) at final physical scale."""
    sizes = []
    for el in root.iter():
        if local(el.tag) != "text":
            continue
        style = el.get("style") or ""
        m = re.search(r"font-size:\s*(%s)(px|pt)?" % NUM, style)
        if not m:
            m = re.search(r"font:\s*(?:\S+\s+)*?(%s)(px|pt)?" % NUM, style)
        if m:
            v = float(m.group(1))
            # svg px == pt at 72dpi; scale to final physical size
            sizes.append(v * scale)
    return sizes


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg")
    ap.add_argument("--preset", default="generic")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--basename", default="figure")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    presets_path = os.path.join(here, "..", "presets", "journal_presets.json")
    with open(presets_path, encoding="utf-8") as fh:
        presets = json.load(fh)["presets"]
    preset = presets.get(args.preset)
    if preset is None:
        print("WARNING: unknown preset %r; falling back to 'generic'"
              % args.preset, file=sys.stderr)
        preset = presets["generic"]
        args.preset = "generic"

    os.makedirs(args.out_dir, exist_ok=True)
    out_svg = os.path.join(args.out_dir, args.basename + ".svg")
    out_pdf = os.path.join(args.out_dir, args.basename + ".pdf")
    out_png = os.path.join(args.out_dir, args.basename + ".png")

    report = {"preset": preset, "input_svg": args.svg,
              "outputs": {}, "tool_versions": {}, "font_summary": None,
              "deviations": [], "status": "ok"}

    # ---- 1-2. rescale -------------------------------------------------------
    tree = ET.parse(args.svg)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    root = tree.getroot()
    vb = (root.get("viewBox") or "").split()
    orig_w_mm = parse_len_mm(root.get("width"))
    if len(vb) == 4 and float(vb[2]) > 0:
        aspect = float(vb[3]) / float(vb[2])
    else:
        aspect = 0.75
        report["deviations"].append("no usable viewBox; assumed aspect 0.75")
    target_w_mm = float(preset["width_mm"])
    target_h_mm = target_w_mm * aspect
    root.set("width", "%.3fmm" % target_w_mm)
    root.set("height", "%.3fmm" % target_h_mm)
    if not root.get("viewBox"):
        w = parse_len_mm(root.get("width")) or target_w_mm
        root.set("viewBox", "0 0 %.3f %.3f" % (w, w * aspect))
    tree.write(out_svg, encoding="utf-8", xml_declaration=True)
    report["outputs"]["svg"] = out_svg
    report["outputs"]["svg_size_mm"] = [round(target_w_mm, 3),
                                        round(target_h_mm, 3)]

    # ---- 3. font floor scan --------------------------------------------------
    scale = (target_w_mm / orig_w_mm) if orig_w_mm else 1.0
    sizes = font_sizes_pt(root, scale)
    report["font_summary"] = {
        "sizes_pt_at_final_scale": [round(s, 2) for s in sorted(sizes)],
        "font_min_pt": preset.get("font_min_pt"),
        "font_max_pt": preset.get("font_max_pt"),
        "families": sorted({f for el in root.iter() if local(el.tag) == "text"
                            for f in re.findall(
                                r"font-family:\s*([^;]+)", el.get("style") or "")}),
    }
    fmin, fmax = preset.get("font_min_pt"), preset.get("font_max_pt")
    too_small = [s for s in sizes if fmin and s < fmin]
    too_large = [s for s in sizes if fmax and s > fmax]
    if too_small:
        report["deviations"].append(
            "%d text element(s) below font floor %gpt: %s"
            % (len(too_small), fmin, [round(s, 2) for s in sorted(too_small)]))
    if too_large:
        report["deviations"].append(
            "%d text element(s) above font ceiling %gpt"
            % (len(too_large), fmax))
    fc = shutil.which("fc-list")
    if fc:
        try:
            out = subprocess.run([fc, ":", "family"], capture_output=True,
                                 text=True, timeout=30).stdout
            fams = sorted({ln.split(",")[0].strip() for ln in out.splitlines()
                           if ln.strip()})
            report["font_summary"]["system_families_sample"] = fams[:40]
            cjk = [f for f in fams if re.search(
                r"CJK|Han|Hei|Song|Kai|YaHei|PingFang|Mincho|Gothic", f, re.I)]
            report["font_summary"]["cjk_families"] = cjk
            if not cjk:
                report["deviations"].append(
                    "no CJK font family found via fc-list; CJK labels may "
                    "render as boxes in raster exports")
        except Exception as exc:
            report["deviations"].append("fc-list failed: %s" % exc)
    else:
        report["font_summary"]["system_families_sample"] = None
        report["deviations"].append(
            "fc-list unavailable; system font inventory skipped")

    # ---- 4. render ------------------------------------------------------------
    report["tool_versions"] = {
        "soffice": tool_version("soffice"),
        "pdftoppm": tool_version("pdftoppm", ("-v",)),
        "python": sys.version.split()[0],
    }
    soffice = shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    pdf_ok = False
    if soffice:
        try:
            r = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", args.out_dir, out_svg],
                capture_output=True, text=True, timeout=180)
            pdf_ok = os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0
            if not pdf_ok:
                report["deviations"].append(
                    "soffice pdf conversion failed: %s"
                    % (r.stderr.strip()[:300] or r.stdout.strip()[:300]))
        except Exception as exc:
            report["deviations"].append("soffice invocation failed: %s" % exc)
    else:
        report["deviations"].append(
            "soffice not installed; cannot render PDF via office-renderer")

    png_ok = False
    if pdf_ok:
        report["outputs"]["pdf"] = out_pdf
        if pdftoppm:
            try:
                base = os.path.join(args.out_dir, args.basename)
                r = subprocess.run(
                    [pdftoppm, "-r", str(int(preset["dpi"])), "-png",
                     "-singlefile", out_pdf, base],
                    capture_output=True, text=True, timeout=180)
                png_ok = os.path.exists(out_png) and os.path.getsize(out_png) > 0
                if not png_ok:
                    report["deviations"].append(
                        "pdftoppm failed: %s" % r.stderr.strip()[:300])
            except Exception as exc:
                report["deviations"].append("pdftoppm failed: %s" % exc)
        else:
            report["deviations"].append("pdftoppm not installed; "
                                        "cannot rasterize PDF at preset dpi")
    if not png_ok and soffice:
        try:
            r = subprocess.run(
                [soffice, "--headless", "--convert-to", "png",
                 "--outdir", args.out_dir, out_svg],
                capture_output=True, text=True, timeout=180)
            png_ok = os.path.exists(out_png) and os.path.getsize(out_png) > 0
            if png_ok:
                report["deviations"].append(
                    "PNG came from soffice direct conversion; dpi metadata "
                    "may not match preset %s" % preset["dpi"])
        except Exception as exc:
            report["deviations"].append("soffice png failed: %s" % exc)
    if png_ok:
        report["outputs"]["png"] = out_png
        report["outputs"]["png_dpi_target"] = preset["dpi"]
    if not pdf_ok and not png_ok and not soffice:
        report["status"] = "renderer_unavailable"
        report["deviations"].append(
            "renderer_unavailable: no soffice; SVG is the authoritative "
            "editable source, PDF/PNG previews could not be produced in this "
            "environment")

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("export preset=%s status=%s outputs=%s deviations=%d"
          % (args.preset, report["status"],
             sorted(report["outputs"]), len(report["deviations"])))
    sys.exit(0)


if __name__ == "__main__":
    main()
