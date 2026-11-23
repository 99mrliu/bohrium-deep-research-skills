#!/usr/bin/env python3
"""Inspect a PDF's text layer before extraction (upstream authenticity gate).

Reports per-page text yield, flags low-text (probably scanned) pages and
two-column/table risk, and decides whether the PDF is usable as-is.

Exit codes: 0 ok (JSON written); 3 no usable text layer (use OCR, then
textlayer.py --text-file); 4 no PDF extractor available; 2 input missing.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

LOW_TEXT_CHARS = 120  # per-page threshold below which a page is "low text"


def have(cmd):
    return shutil.which(cmd) is not None


def pdftotext(pdf, extra):
    try:
        p = subprocess.run(["pdftotext"] + extra + [pdf, "-"],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if p.returncode != 0:
        return None, (p.stderr or "pdftotext failed").strip()
    return p.stdout, None


def analyze(pdf, out_path):
    if not have("pdftotext"):
        try:
            import pypdf  # noqa: F401
            reader_ok = True
        except ImportError:
            reader_ok = False
        if not reader_ok:
            print("NEXT: no pdftotext/pypdf. Use the environment pdf-text/ocr "
                  "tool (see environment/resources.yaml), save text, then run "
                  "textlayer.py --text-file FILE", file=sys.stderr)
            return 4
        # minimal pypdf path: single string, split on \x0c if present
        from pypdf import PdfReader
        try:
            pages = [pg.extract_text() or "" for pg in PdfReader(pdf).pages]
        except Exception as e:  # noqa: BLE001
            print("NEXT: pypdf failed: %s" % e, file=sys.stderr)
            return 3
        raw_pages, layout_pages = pages, pages
    else:
        raw, err = pdftotext(pdf, [])
        if raw is None:
            print("NEXT: pdftotext failed: %s" % err, file=sys.stderr)
            return 3
        layout, _ = pdftotext(pdf, ["-layout"])
        raw_pages = raw.split("\f")
        layout_pages = (layout or "").split("\f")

    n = max(len(raw_pages), 1)
    page_reports = []
    total_chars = 0
    for i in range(n):
        rt = raw_pages[i] if i < len(raw_pages) else ""
        lt = layout_pages[i] if i < len(layout_pages) else ""
        chars = len(rt.strip())
        total_chars += chars
        lines = [ln for ln in lt.splitlines() if ln.strip()]
        # two-column symptom: many layout lines with a wide interior gap
        gaps = sum(1 for ln in lines if "    " in ln.rstrip() and len(ln) > 60)
        # table symptom: many lines with 3+ interior gap clusters or pipes
        tbl = sum(1 for ln in lines if ln.count("  ") >= 3 or ln.count("|") >= 2)
        page_reports.append({
            "page": i + 1,
            "chars": chars,
            "lines": len(lines),
            "gap_lines": gaps,
            "table_like_lines": tbl,
            "low_text": chars < LOW_TEXT_CHARS,
            "column_risk": bool(lines) and gaps >= max(4, len(lines) // 3),
            "table_risk": tbl >= 4,
        })
    verdict = {
        "pdf": os.path.basename(pdf),
        "pages": len(page_reports),
        "total_chars": total_chars,
        "low_text_pages": [r["page"] for r in page_reports if r["low_text"]],
        "column_risk_pages": [r["page"] for r in page_reports if r["column_risk"]],
        "table_risk_pages": [r["page"] for r in page_reports if r["table_risk"]],
        "page_reports": page_reports,
        "usable": total_chars > 0,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    print("inspect -> %s | pages=%d chars=%d low_text=%s" % (
        out_path, verdict["pages"], total_chars, verdict["low_text_pages"]))
    if total_chars == 0:
        print("NEXT: no text layer (scanned?). Use the environment OCR tool, "
              "save text, then textlayer.py --text-file FILE", file=sys.stderr)
        return 3
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not os.path.isfile(a.pdf):
        print("input missing: %s" % a.pdf, file=sys.stderr)
        return 2
    return analyze(a.pdf, a.out)


if __name__ == "__main__":
    sys.exit(main())
