#!/usr/bin/env python3
"""Figure/table zone detection and crop extraction.

Finds caption spans (regex ^(Figure|Fig\\.?|Table)\\s*\\d+) in spans.jsonl,
derives a zone rectangle ABOVE the caption on the same page (up to the nearest
text block above it, full content width), and re-renders that region with
pdftoppm at 200dpi into work/figures/fig-<n>.png.

Coordinate note: pdftotext -bbox-layout emits TOP-LEFT origin points, and
pdftoppm -x/-y are TOP-LEFT origin pixels at the requested -r, so conversion
is a pure scale (pt * dpi/72); no bottom-left flip is needed. If you ever
consume PyMuPDF-style bottom-left boxes you must flip y first.

Tables are detected but NOT cropped: they are marked
"prefer native/CSV transcription".

Usage:
    python3 figure_zones.py [--pdf paper.pdf] [--dpi 200]
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

CAPTION_RE = re.compile(r"^(Figure|Fig\.?|Table)\s*(\d+)")
MARGIN_X = 36.0  # pt; zones span the full content width


def log(msg):
    print(f"[figure_zones] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Locate caption zones and crop figure regions")
    ap.add_argument("--pdf", default=None, help="paper PDF (default: from ingest_report.json)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--zone-override", default=None,
                    help='JSON {"fig_id":[x0,y0,x1,y1]} to override a zone in PDF pt '
                         "(top-left origin) when the heuristic crops wrong")
    ap.add_argument("--input-dir", default=os.environ.get("CASE_INPUT_DIR", "/input"))
    ap.add_argument("--work-dir", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--output-dir", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args()
    work = os.path.abspath(args.work_dir)
    fig_dir = os.path.join(work, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    spans_path = os.path.join(work, "spans.jsonl")
    if not os.path.isfile(spans_path):
        log("FATAL: spans.jsonl not found; run pdf_ingest.py first")
        return 2
    spans = [json.loads(l) for l in open(spans_path, encoding="utf-8") if l.strip()]

    report_path = os.path.join(work, "ingest_report.json")
    page_sizes = {}
    pdf = args.pdf
    if os.path.isfile(report_path):
        rep = json.load(open(report_path, encoding="utf-8"))
        for p in rep.get("pages", []):
            page_sizes[p["page"]] = (p.get("width"), p.get("height"))
        pdf = pdf or rep.get("pdf")
    overrides = json.loads(args.zone_override) if args.zone_override else {}

    issues = []
    figures = []
    pdftoppm = shutil.which("pdftoppm")
    captions = [s for s in spans if CAPTION_RE.match(s["text"])]
    n_fig = n_tab = 0
    for cap in sorted(captions, key=lambda s: (s["page"], s.get("reading_order", 0))):
        kind = "table" if cap["text"].lower().startswith("table") else "figure"
        if kind == "table":
            n_tab += 1
            fid = f"table-{n_tab}"
        else:
            n_fig += 1
            fid = f"fig-{n_fig}"
        entry = {
            "fig_id": fid,
            "caption": cap["text"],
            "caption_span_id": cap["span_id"],
            "page": cap["page"],
            "zone_bbox_pdf": None,
            "crop_path": None,
            "kind": kind,
        }
        if kind == "table":
            entry["note"] = "prefer native/CSV transcription; not cropped as an image"
            figures.append(entry)
            continue
        if cap["x0"] is None:
            entry["note"] = "spans have no coordinates (pdftotext-layout fallback); cannot zone"
            issues.append({"kind": "no-coordinates", "fig_id": fid})
            figures.append(entry)
            continue
        # zone: from the nearest text block above the caption up top, down to the caption
        same_page = [s for s in spans
                     if s["page"] == cap["page"] and s["x0"] is not None
                     and s["span_id"] != cap["span_id"]]
        above = [s for s in same_page if s["y1"] <= cap["y0"] - 2]
        top = max((s["y1"] for s in above), default=max(0.0, cap["y0"] - 400)) + 4
        pw, ph = page_sizes.get(cap["page"], (612.0, 792.0))
        pw = pw or 612.0
        zone = [MARGIN_X, round(top, 2), round(pw - MARGIN_X, 2), round(cap["y0"] - 2, 2)]
        if fid in overrides:
            zone = [float(v) for v in overrides[fid]]
            entry["zone_override"] = True
        if zone[3] - zone[1] < 30:
            entry["note"] = ("zone too small (<30pt tall); nothing to crop - "
                             "re-run with --zone-override")
            issues.append({"kind": "zone-too-small", "fig_id": fid})
            entry["zone_bbox_pdf"] = zone
            figures.append(entry)
            continue
        entry["zone_bbox_pdf"] = zone
        if not pdftoppm:
            entry["note"] = "pdftoppm missing; zone recorded but crop skipped"
            issues.append({"kind": "tool-missing", "fig_id": fid})
            figures.append(entry)
            continue
        if not pdf or not os.path.isfile(pdf):
            entry["note"] = "pdf path unknown; crop skipped"
            figures.append(entry)
            continue
        scale = args.dpi / 72.0
        x, y = int(round(zone[0] * scale)), int(round(zone[1] * scale))
        w, h = int(round((zone[2] - zone[0]) * scale)), int(round((zone[3] - zone[1]) * scale))
        tmp_prefix = os.path.join(fig_dir, f"_crop-{fid}")
        r = subprocess.run(
            [pdftoppm, "-f", str(cap["page"]), "-l", str(cap["page"]), "-r", str(args.dpi),
             "-png", "-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h), pdf, tmp_prefix],
            capture_output=True, text=True)
        if r.returncode != 0:
            entry["note"] = f"pdftoppm crop failed: {r.stderr.strip()[:300]}"
            issues.append({"kind": "crop-failed", "fig_id": fid})
        else:
            outs = glob.glob(tmp_prefix + "*.png")
            if outs:
                dest = os.path.join(fig_dir, f"{fid}.png")
                os.replace(sorted(outs)[0], dest)
                for extra in outs[1:]:
                    os.remove(extra)
                entry["crop_path"] = dest
            else:
                entry["note"] = "pdftoppm produced no output"
                issues.append({"kind": "crop-failed", "fig_id": fid})
        figures.append(entry)

    for f in glob.glob(os.path.join(fig_dir, "_crop-*.png")):
        os.remove(f)
    with open(os.path.join(work, "figures.json"), "w", encoding="utf-8") as f:
        json.dump({"figures": figures, "issues": issues}, f, ensure_ascii=False, indent=2)
    log(f"{n_fig} figure zone(s), {n_tab} table(s); {len(issues)} issue(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
