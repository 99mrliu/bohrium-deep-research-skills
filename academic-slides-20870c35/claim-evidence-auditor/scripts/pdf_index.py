#!/usr/bin/env python3
"""Build a source index for a PDF: per-page text plus registries of figure/table
captions, section headings and bracket citations.

Usage:
  python3 pdf_index.py paper.pdf --out source_index.json [--pdftotext /path/to/pdftotext]

Requires poppler's pdftotext (discovered on PATH unless --pdftotext is given).
Stdlib otherwise. Missing tools produce a nonzero exit and a clear message —
record that as a limitation instead of guessing.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

EXHIBIT_RE = re.compile(
    r"^\s*(Figure|Fig\.?|Table|FIGURE|TABLE)\s*(?:S?\d+[A-Za-z]?)", re.MULTILINE)
CAPTION_RE = re.compile(
    r"(?m)^\s*((?:Figure|Fig\.?|Table|FIGURE|TABLE)\s*(?:S?\d+[A-Za-z]?))"
    r"[.:]?\s*([^\n]{0,300})")
SECTION_RE = re.compile(
    r"(?m)^\s*((?:\d+\.)+(?:\d+)?)\s+([A-Z][^\n]{3,80})$")
CITE_RE = re.compile(r"\[\d+(?:[-,]\s*\d+)*\]")
FOOTER_RE = re.compile(r"^\s*(\d{1,3})\s*$")


def run_pdftotext(pdftotext, pdf):
    try:
        out = subprocess.run(
            [pdftotext, "-layout", pdf, "-"],
            capture_output=True, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        sys.exit(f"pdftotext failed on {pdf}: {exc}")
    return out.stdout.decode("utf-8", errors="replace")


def guess_printed_page(page_text):
    lines = [ln for ln in page_text.strip().splitlines() if ln.strip()]
    for ln in (lines[-3:] + lines[:3]):
        m = FOOTER_RE.match(ln)
        if m:
            return int(m.group(1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdftotext", default=shutil.which("pdftotext"))
    args = ap.parse_args()
    if not args.pdftotext:
        sys.exit("pdftotext not found on PATH; pass --pdftotext or record the limitation")

    full = run_pdftotext(args.pdftotext, args.pdf)
    raw_pages = full.split("\f")
    if raw_pages and not raw_pages[-1].strip():
        raw_pages.pop()

    pages, exhibits, sections, citations = [], [], [], []
    seen_exhibits = set()
    for i, text in enumerate(raw_pages, 1):
        pages.append({"pdf_page": i, "text": text})
        printed = guess_printed_page(text)
        for m in CAPTION_RE.finditer(text):
            label = re.sub(r"\s+", " ", m.group(1)).replace("Fig.", "Figure").strip()
            label = re.sub(r"^(FIGURE|TABLE)", lambda g: g.group(1).title(), label)
            if label.lower() in seen_exhibits:
                continue
            seen_exhibits.add(label.lower())
            exhibits.append({
                "kind": "table" if label.lower().startswith("table") else "figure",
                "id": label, "pdf_page": i, "printed_page": printed,
                "caption": re.sub(r"\s+", " ", m.group(0)).strip()[:400]})
        for m in SECTION_RE.finditer(text):
            title = f"{m.group(1)} {m.group(2).strip()}"
            sections.append({"title": title, "pdf_page": i})
        for m in CITE_RE.finditer(text):
            citations.append({"raw": m.group(0), "pdf_page": i})

    index = {"file": args.pdf, "page_count": len(raw_pages), "pages": pages,
             "exhibits": exhibits, "sections": sections, "citations": citations}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    print(f"indexed {len(raw_pages)} pages, {len(exhibits)} exhibits, "
          f"{len(sections)} section headings, {len(citations)} citations -> {args.out}")
    if not exhibits:
        print("WARNING: no figure/table captions detected; check for scanned PDF "
              "or two-column layout and complete the registry manually", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
