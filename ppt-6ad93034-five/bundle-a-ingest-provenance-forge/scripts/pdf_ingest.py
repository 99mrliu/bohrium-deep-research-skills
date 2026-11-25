#!/usr/bin/env python3
"""Forensic PDF ingest for ingest-provenance-forge.

Renders every page to PNG (pdftoppm), extracts text spans WITH coordinates
(pdftotext -bbox-layout, XHTML parsed into spans.jsonl), falls back to
line-level spans without coordinates (pdftotext -layout), detects multi-column
pages and re-serializes reading order, and runs extraction forensics
(replacement chars, control chars, empty/low-yield pages, 1-char-span storms).

Every downstream artifact must trace back to the span ids produced here.

Usage:
    python3 pdf_ingest.py --pdf <paper.pdf>
    # dirs via flags or env CASE_INPUT_DIR / CASE_WORK_DIR / CASE_OUTPUT_DIR
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def log(msg):
    print(f"[pdf_ingest] {msg}", flush=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def localname(tag):
    return tag.split("}")[-1]


def parse_bbox_xhtml(path):
    """Parse pdftotext -bbox-layout XHTML into line-level spans.

    Returns list of pages: {"width","height","spans":[span,...]}.
    Coordinates are PDF points, origin TOP-LEFT (as emitted by pdftotext).
    """
    root = ET.parse(path).getroot()
    pages = []
    for page in root.iter():
        if localname(page.tag) != "page":
            continue
        spans = []
        idx = 0
        pageno = len(pages) + 1
        for line in page.iter():
            if localname(line.tag) != "line":
                continue
            words = [w for w in line if localname(w.tag) == "word"]
            if not words:
                continue
            text = " ".join("".join(w.itertext()) for w in words).strip()
            if not text:
                continue
            idx += 1
            spans.append({
                "span_id": f"p{pageno}-s{idx:04d}",
                "page": pageno,
                "x0": round(min(float(w.get("xMin")) for w in words), 2),
                "y0": round(min(float(w.get("yMin")) for w in words), 2),
                "x1": round(max(float(w.get("xMax")) for w in words), 2),
                "y1": round(max(float(w.get("yMax")) for w in words), 2),
                "text": text,
                "method": "pdftotext-bbox",
            })
        pages.append({
            "width": float(page.get("width", 0)),
            "height": float(page.get("height", 0)),
            "spans": spans,
        })
    return pages


def parse_layout_text(txt):
    """Fallback: pdftotext -layout plain text -> line spans, bbox null."""
    pages = []
    for pageno, ptxt in enumerate(txt.split("\f"), start=1):
        spans = []
        idx = 0
        for raw in ptxt.splitlines():
            text = raw.strip()
            if not text:
                continue
            idx += 1
            spans.append({
                "span_id": f"p{pageno}-s{idx:04d}",
                "page": pageno,
                "x0": None, "y0": None, "x1": None, "y1": None,
                "text": text,
                "method": "pdftotext-layout",
            })
        pages.append({"width": None, "height": None, "spans": spans})
    # trailing formfeed yields an empty phantom page
    if pages and not pages[-1]["spans"] and len(pages) > 1:
        pages.pop()
    return pages


def detect_columns_and_order(pages, issues):
    """Cluster span x0 per page; 2+ clusters with vertical overlap => multi-column.

    Assigns global 'reading_order' per span (column-major on multi-column
    pages, top-to-bottom otherwise).
    """
    order = 0
    for page in pages:
        spans = page["spans"]
        pageno = 0
        if spans:
            pageno = spans[0]["page"]
        geo = [s for s in spans if s["x0"] is not None]
        multicolumn = False
        if len(geo) >= 6:
            xs = sorted(s["x0"] for s in geo)
            clusters = [[xs[0]]]
            for x in xs[1:]:
                if x - clusters[-1][-1] > 40:
                    clusters.append([x])
                else:
                    clusters[-1].append(x)
            clusters = [c for c in clusters if len(c) >= 3]
            if len(clusters) >= 2:
                # vertical overlap between left-most and right-most cluster extents
                groups = []
                for c in clusters:
                    lo, hi = c[0] - 40, c[-1] + 40
                    members = [s for s in geo if lo <= s["x0"] <= hi]
                    groups.append((lo, members))
                groups.sort(key=lambda g: g[0])
                overlap_pairs = 0
                for i in range(len(groups)):
                    for j in range(i + 1, len(groups)):
                        yi = (min(s["y0"] for s in groups[i][1]), max(s["y1"] for s in groups[i][1]))
                        yj = (min(s["y0"] for s in groups[j][1]), max(s["y1"] for s in groups[j][1]))
                        ov = min(yi[1], yj[1]) - max(yi[0], yj[0])
                        if ov > 0.5 * min(yi[1] - yi[0], yj[1] - yj[0]):
                            overlap_pairs += 1
                if overlap_pairs > 0:
                    multicolumn = True
                    issues.append({
                        "kind": "multi-column",
                        "page": pageno,
                        "detail": f"{len(groups)} x0 clusters with vertical overlap; "
                                  "reading order serialized column-major",
                    })
                    for _, members in groups:
                        for s in sorted(members, key=lambda s: (s["y0"], s["x0"])):
                            order += 1
                            s["reading_order"] = order
                    # spans without geometry (should not happen on bbox pages)
                    for s in spans:
                        if "reading_order" not in s:
                            order += 1
                            s["reading_order"] = order
        if not multicolumn:
            for s in sorted(spans, key=lambda s: ((s["y0"] is None), s["y0"] or 0, s["x0"] or 0)):
                order += 1
                s["reading_order"] = order


def forensics(pages, issues):
    """Extraction forensics: garbled text, empty pages, low yield, 1-char storms."""
    for page in pages:
        spans = page["spans"]
        pageno = spans[0]["page"] if spans else None
        if pageno is None:
            continue
        if not spans:
            issues.append({
                "kind": "empty-page",
                "page": pageno,
                "detail": "no text extracted; likely image-only page -> recommend OCR or crop-embed",
            })
            continue
        chars = sum(len(s["text"]) for s in spans)
        if chars < 200:
            issues.append({
                "kind": "low-text-yield",
                "page": pageno,
                "detail": f"{chars} chars on page (<200); possible image-only page -> "
                          "recommend OCR or crop-embed",
            })
        fffd = [s["span_id"] for s in spans if "\ufffd" in s["text"]]
        if fffd:
            issues.append({
                "kind": "replacement-char",
                "page": pageno,
                "detail": f"U+FFFD in {len(fffd)} span(s) e.g. {fffd[:5]}; extraction garbled, "
                          "do not trust affected spans",
            })
        ctrl = [s["span_id"] for s in spans if CTRL_RE.search(s["text"])]
        if ctrl:
            issues.append({
                "kind": "control-chars",
                "page": pageno,
                "detail": f"control characters in {len(ctrl)} span(s) e.g. {ctrl[:5]}",
            })
        one_char = [s for s in spans if len(s["text"].strip()) <= 1]
        if len(spans) >= 10 and len(one_char) / len(spans) > 0.2:
            issues.append({
                "kind": "font-encoding-anomaly",
                "page": pageno,
                "detail": f"{len(one_char)}/{len(spans)} spans are 1-char; probable font "
                          "encoding/CID mapping problem",
            })


def main():
    ap = argparse.ArgumentParser(description="Forensic PDF ingest with coordinate-level provenance")
    ap.add_argument("--pdf", required=True, help="path to the paper PDF")
    ap.add_argument("--input-dir", default=os.environ.get("CASE_INPUT_DIR", "/input"))
    ap.add_argument("--work-dir", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--output-dir", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args()
    work = os.path.abspath(args.work_dir)
    pages_dir = os.path.join(work, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    pdftotext = shutil.which("pdftotext")
    pdftoppm = shutil.which("pdftoppm")
    report = {
        "pdf": os.path.abspath(args.pdf),
        "tools": {"pdftotext": pdftotext, "pdftoppm": pdftoppm},
        "missing_tools": [t for t, p in (("pdftotext", pdftotext), ("pdftoppm", pdftoppm)) if not p],
        "pages": [],
        "span_count": 0,
        "issues": [],
    }
    if not os.path.isfile(args.pdf):
        log(f"FATAL: pdf not found: {args.pdf}")
        report["issues"].append({"kind": "missing-input", "page": None,
                                 "detail": f"pdf not found: {args.pdf}"})
        _write(work, report, [], [])
        return 2

    # 1) render pages (cross-validation substrate + figure crops later)
    if pdftoppm:
        r = run([pdftoppm, "-r", "150", "-png", args.pdf, os.path.join(pages_dir, "page")])
        if r.returncode != 0:
            report["issues"].append({"kind": "render-failed", "page": None,
                                     "detail": r.stderr.strip()[:400]})
        else:
            for f in sorted(glob.glob(os.path.join(pages_dir, "page-*.png"))):
                m = re.search(r"page-(\d+)\.png$", f)
                if m:
                    os.replace(f, os.path.join(pages_dir, f"page-{int(m.group(1)):03d}.png"))
            log(f"rendered {len(glob.glob(os.path.join(pages_dir, 'page-*.png')))} page PNGs at 150dpi")
    else:
        report["issues"].append({"kind": "tool-missing", "page": None,
                                 "detail": "pdftoppm not found; page renders skipped"})

    # 2) text with coordinates, with graceful fallback
    pages = []
    method = None
    if pdftotext:
        xhtml_path = os.path.join(work, "_bbox.xhtml")
        r = run([pdftotext, "-bbox-layout", args.pdf, xhtml_path])
        if r.returncode == 0 and os.path.isfile(xhtml_path):
            try:
                pages = parse_bbox_xhtml(xhtml_path)
                method = "pdftotext-bbox"
            except Exception as e:  # malformed XHTML -> fall back
                report["issues"].append({"kind": "bbox-parse-failed", "page": None,
                                         "detail": f"{type(e).__name__}: {e}; fell back to -layout"})
        if not pages:
            r = run([pdftotext, "-layout", args.pdf, "-"])
            if r.returncode == 0:
                pages = parse_layout_text(r.stdout)
                method = "pdftotext-layout"
                report["issues"].append({"kind": "no-coordinates", "page": None,
                                         "detail": "bbox extraction unavailable; spans have bbox:null "
                                                   "and figure zoning is disabled"})
    if not pages:
        report["issues"].append({"kind": "no-text-extraction", "page": None,
                                 "detail": "no text extractor available; ingest incomplete -> partial"})
        _write(work, report, [], pages)
        return 2

    detect_columns_and_order(pages, report["issues"])
    forensics(pages, report["issues"])

    all_spans = []
    for pageno, page in enumerate(pages, start=1):
        report["pages"].append({
            "page": pageno,
            "width": page["width"],
            "height": page["height"],
            "span_count": len(page["spans"]),
            "char_count": sum(len(s["text"]) for s in page["spans"]),
        })
        all_spans.extend(page["spans"])
    all_spans.sort(key=lambda s: s["reading_order"])
    report["span_count"] = len(all_spans)
    report["method"] = method

    _write(work, report, all_spans, pages)
    log(f"{len(all_spans)} spans from {len(pages)} pages via {method}; "
        f"{len(report['issues'])} issue(s)")
    return 0


def _write(work, report, all_spans, pages):
    with open(os.path.join(work, "spans.jsonl"), "w", encoding="utf-8") as f:
        for s in all_spans:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(os.path.join(work, "paper.txt"), "w", encoding="utf-8") as f:
        by_page = {}
        for s in all_spans:
            by_page.setdefault(s["page"], []).append(s)
        for pageno in sorted(by_page):
            f.write(f"[[page {pageno}]]\n")
            for s in sorted(by_page[pageno], key=lambda s: s["reading_order"]):
                f.write(s["text"] + "\n")
            f.write("\n")
    with open(os.path.join(work, "ingest_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
