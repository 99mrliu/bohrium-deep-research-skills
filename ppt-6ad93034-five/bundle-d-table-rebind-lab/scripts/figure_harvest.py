#!/usr/bin/env python3
"""figure_harvest.py - harvest figures from a paper PDF as verified crops.

Method
------
1. `pdftotext -bbox-layout <pdf> -` gives every word's bounding box in PDF pts
   with TOP-LEFT origin (y grows downward), plus block/line structure.
2. Caption lines matching ^(Figure|Fig\\.)?\\s*\\d+ are located.
3. Crop zone (deterministic heuristic): the region directly ABOVE the caption
   (smaller y). The zone extends upward from the caption until the first text
   line with >= 6 words (body text); shorter lines count as in-figure labels
   and are included. Horizontal extent = union of all word boxes inside the
   band, expanded by 20 pt (min 150 pt wide). If the zone looks wrong, re-crop
   with --override fig-N=x0,y0,x1,y1 (PDF pts, TOP-LEFT origin).
4. Crop with `pdftoppm -f N -l N -r 200 -x/-y/-W/-H` (top-left pixel coords at
   200 dpi = pts * 200/72).

Classification (deterministic, see references/rebind_policy.md):
  "replot-candidate" iff a mined table's caption or column headers share at
  least one quantity word (len >= 4, not a stopword) with the figure caption;
  otherwise "bitmap-embed". A replot-candidate is NEVER pixel-estimated: it is
  replotted from the mined CSV by replot.py, or embedded as a crop if no CSV
  covers it.

Outputs: work/figures/fig-N.png, work/figures.json
  [{fig_id, caption, page, crop_path, classification}]

Pure stdlib. No network. Invocation:
    python3 /skills/weekly-skill/scripts/figure_harvest.py --pdf /input/paper.pdf
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

CAP_START_RE = re.compile(r"^(Figure|Fig\.?)\s*(\d+)", re.IGNORECASE)
STOPWORDS = {
    "figure", "fig", "the", "and", "for", "with", "from", "across", "over",
    "under", "between", "versus", "vs", "our", "ours", "their", "this",
    "that", "these", "those", "each", "synthetic", "shown", "shows", "plot",
    "plots", "plotted", "curve", "curves", "panel", "left", "right", "top",
    "bottom", "different", "various", "using", "used", "results", "result",
}
DPI = 200
SCALE = DPI / 72.0


def fail(msg: str, code: int = 1) -> "None":
    print(f"[figure_harvest] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def words_of(elem):
    out = []
    for w in elem.iter():
        if local(w.tag) == "word":
            out.append({
                "xMin": float(w.get("xMin")), "yMin": float(w.get("yMin")),
                "xMax": float(w.get("xMax")), "yMax": float(w.get("yMax")),
                "text": (w.text or ""),
            })
    return out


def bbox(words):
    return (min(w["xMin"] for w in words), min(w["yMin"] for w in words),
            max(w["xMax"] for w in words), max(w["yMax"] for w in words))


def quantity_words(text: str):
    words = set()
    for tok in re.split(r"[^A-Za-z]+", text.lower()):
        if len(tok) >= 4 and tok not in STOPWORDS:
            words.add(tok)
    return words


def parse_override(s: str):
    """fig-1=x0,y0,x1,y1 in PDF pts (top-left origin)."""
    fid, _, coords = s.partition("=")
    vals = [float(v) for v in coords.split(",")]
    if len(vals) != 4:
        fail(f"bad --override {s!r}; expected fig-N=x0,y0,x1,y1", 2)
    return fid.strip(), vals


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest figure crops from a paper PDF.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--override", action="append", default=[],
                    help="fig-N=x0,y0,x1,y1 in PDF pts (bottom-left); repeatable")
    args = ap.parse_args()

    work = os.environ.get("CASE_WORK_DIR", "/app/work")
    fig_dir = os.path.join(work, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    if not os.path.isfile(args.pdf):
        fail(f"pdf not found: {args.pdf}", 2)
    pdftotext = shutil.which("pdftotext")
    pdftoppm = shutil.which("pdftoppm")
    if not pdftotext or not pdftoppm:
        fail("pdftotext/pdftoppm not found in PATH; cannot harvest figures", 2)

    overrides = dict(parse_override(o) for o in args.override)

    proc = subprocess.run([pdftotext, "-bbox-layout", args.pdf, "-"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        fail(f"pdftotext -bbox-layout failed: {proc.stderr.strip()}", 2)
    try:
        root = ET.fromstring(proc.stdout)
    except ET.ParseError as e:
        fail(f"could not parse bbox XML: {e}", 2)

    # Table words for classification (mined tables, if present).
    table_words = set()
    tables_json = os.path.join(work, "tables.json")
    if os.path.isfile(tables_json):
        with open(tables_json, encoding="utf-8") as f:
            for rec in json.load(f):
                table_words |= quantity_words(rec.get("caption", ""))
                csv_path = rec.get("csv_path") or ""
                if csv_path and os.path.isfile(csv_path):
                    with open(csv_path, encoding="utf-8") as cf:
                        table_words |= quantity_words(cf.readline())

    page_els = [el for el in root.iter() if local(el.tag) == "page"]
    records = []
    seen = set()
    for page_idx, page_el in enumerate(page_els, start=1):
        page_no = page_idx
        pw = float(page_el.get("width"))
        ph = float(page_el.get("height"))
        blocks = []
        lines = []
        for el in page_el.iter():
            t = local(el.tag)
            if t == "block":
                blocks.append(el)
            elif t == "line":
                lines.append(el)

        for line_el in lines:
            ws = words_of(line_el)
            if len(ws) < 2:
                continue
            first2 = " ".join(w["text"] for w in ws[:2])
            m = CAP_START_RE.match(first2)
            if not m:
                continue
            fig_id = f"fig-{m.group(2)}"
            if fig_id in seen:
                print(f"[figure_harvest] WARNING: duplicate {fig_id}, skipping")
                continue
            seen.add(fig_id)
            caption = " ".join(w["text"] for w in ws)
            cap_top = min(w["yMin"] for w in ws)
            cap_x0 = min(w["xMin"] for w in ws)
            cap_x1 = max(w["xMax"] for w in ws)

            if fig_id in overrides:
                x0, y0, x1, y1 = overrides[fig_id]
                src = "override"
            else:
                # Zone (PDF pts, TOP-LEFT origin, y grows downward): the
                # region ABOVE the caption, i.e. smaller y. Bottom edge = just
                # above the caption; top edge = just below the first line with
                # >= 6 words (body text) above; shorter lines count as
                # in-figure labels and stay inside the zone.
                zone_bottom = cap_top - 2.0
                zone_top = 36.0  # default: page top margin
                above = []
                for le in lines:
                    lws = words_of(le)
                    if not lws or le is line_el:
                        continue
                    lb = bbox(lws)
                    if lb[3] <= cap_top + 1.0:  # entirely above the caption
                        above.append((lb, len(lws)))
                above.sort(key=lambda t: -t[0][3])  # nearest first (largest yMax)
                for lb, nwords in above:
                    if nwords >= 6:
                        zone_top = lb[3] + 2.0
                        break
                if zone_bottom <= zone_top:
                    zone_bottom = zone_top + 60.0
                band_words = [w for le in lines for w in words_of(le)
                              if w["yMin"] >= zone_top - 1.0
                              and w["yMax"] <= zone_bottom + 1.0]
                if band_words:
                    x0 = min(w["xMin"] for w in band_words) - 20.0
                    x1 = max(w["xMax"] for w in band_words) + 20.0
                else:
                    x0, x1 = cap_x0 - 20.0, cap_x1 + 20.0
                y0, y1 = zone_top, zone_bottom
                x0 = max(0.0, x0); x1 = min(pw, x1)
                y0 = max(0.0, y0); y1 = min(ph, y1)
                if x1 - x0 < 150.0:
                    cx = (x0 + x1) / 2.0
                    x0, x1 = max(0.0, cx - 75.0), min(pw, cx + 75.0)
                if y1 - y0 < 60.0:
                    y1 = min(ph, y0 + 60.0)
                src = "auto"

            # PDF pts (top-left) -> px (top-left) at DPI.
            px_x = int(round(x0 * SCALE))
            px_y = int(round(y0 * SCALE))
            px_w = max(1, int(round((x1 - x0) * SCALE)))
            px_h = max(1, int(round((y1 - y0) * SCALE)))

            prefix = os.path.join(fig_dir, f"_{fig_id}_tmp")
            for old in glob.glob(prefix + "-*.png"):
                os.remove(old)
            proc2 = subprocess.run(
                [pdftoppm, "-f", str(page_no), "-l", str(page_no),
                 "-r", str(DPI), "-png",
                 "-x", str(px_x), "-y", str(px_y),
                 "-W", str(px_w), "-H", str(px_h), args.pdf, prefix],
                capture_output=True, text=True)
            if proc2.returncode != 0:
                fail(f"pdftoppm crop failed for {fig_id}: {proc2.stderr.strip()}", 2)
            produced = sorted(glob.glob(prefix + "-*.png"))
            if not produced:
                fail(f"pdftoppm produced no crop for {fig_id}", 2)
            crop_path = os.path.join(fig_dir, f"{fig_id}.png")
            os.replace(produced[0], crop_path)

            fig_qw = quantity_words(caption)
            classification = ("replot-candidate"
                              if fig_qw & table_words else "bitmap-embed")
            size_kb = os.path.getsize(crop_path) / 1024.0
            print(f"[figure_harvest] {fig_id} (p.{page_no}) [{src}] "
                  f"{classification}, crop {px_w}x{px_h}px, {size_kb:.1f} KB")
            records.append({
                "fig_id": fig_id,
                "caption": caption,
                "page": page_no,
                "crop_path": crop_path,
                "classification": classification,
            })

    if not records:
        print("[figure_harvest] WARNING: no figure captions found")
    out = os.path.join(work, "figures.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"[figure_harvest] wrote {out} ({len(records)} figure(s))")


if __name__ == "__main__":
    main()
