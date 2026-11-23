#!/usr/bin/env python3
"""Build a faithful, page/paragraph-anchored text layer from a paper PDF.

Outputs (under --work-dir):
  textlayer.jsonl  one {"pid","page","source","text"} per paragraph
  fulltext.txt     human-readable page/paragraph text (for grep)
  integrity.json   per-page yield + normalization counts + fragility flags

Anchors: pid = p<page>.<paragraph index> (e.g. p002.003). Text is kept
verbatim except documented normalizations (ligatures, soft-hyphen joins,
math-spacing collapse) whose counts are recorded in integrity.json.

Exit codes: 0 ok; 2 input missing; 3 no text layer; 4 no extractor.
"""
import argparse
import json
import os
import re
import subprocess
import sys

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
             "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}
HEADER_RE = re.compile(r"^\s*(\d+\.?\s+[A-Z]|[A-Z][A-Za-z ]{2,30}:)")


def extract_pages(pdf, text_file):
    """Return list of page strings. Prefer pdftotext -layout; fall back to
    pypdf; or read a pre-extracted text file (form-feed separated pages)."""
    if text_file:
        txt = open(text_file, encoding="utf-8").read()
        pages = txt.split("\f")
        return pages if len(pages) > 1 else [txt]
    if not pdf or not os.path.isfile(pdf):
        return None
    try:
        p = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.split("\f")
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        from pypdf import PdfReader
        pages = [pg.extract_text() or "" for pg in PdfReader(pdf).pages]
        if any(pg.strip() for pg in pages):
            return pages
    except ImportError:
        print("NEXT: no pdftotext/pypdf. Use the environment pdf-text/ocr "
              "tool, save text, rerun with --text-file FILE", file=sys.stderr)
        sys.exit(4)
    except Exception:  # noqa: BLE001
        pass
    return None


def normalize(text, counts):
    """Documented normalizations only; every change is counted."""
    for lig, rep in LIGATURES.items():
        n = text.count(lig)
        if n:
            counts["ligatures"] += n
            text = text.replace(lig, rep)
    # soft hyphen / hyphen-newline joins: "perfor-\nmance" -> "performance"
    text, n = re.subn(r"(\w)[\u00ad-]\n(\w)", r"\1\2", text)
    counts["hyphen_joins"] += n
    # collapse intra-line runs of spaces (layout padding) to one space
    text, n = re.subn(r"[ \t]{2,}", " ", text)
    counts["space_collapses"] += n
    # rejoin units split by line breaks: "152\nmAh" -> "152 mAh"
    text, n = re.subn(r"(\d)\n(%|[a-zA-Zµμ°][a-zA-Zµμ°/-]{0,11})\b", r"\1 \2", text)
    counts["unit_joins"] += n
    return text


def split_columns(lines):
    """If most lines contain a wide interior gap, split into left/right
    column parts (two-column symptom); otherwise return lines as-is."""
    gap = [ln for ln in lines if re.search(r"\S\s{4,}\S", ln)]
    if len(lines) >= 6 and len(gap) >= len(lines) * 0.6:
        left, right = [], []
        for ln in lines:
            parts = re.split(r"\s{4,}", ln.rstrip())
            if len(parts) >= 2:
                left.append(parts[0])
                right.append(" ".join(parts[1:]))
            else:
                left.append(ln)
        return left + [""] + right
    return lines


def paragraphs(page_text):
    lines = page_text.splitlines()
    lines = split_columns([ln for ln in lines])
    paras, buf = [], []
    for ln in lines + [""]:
        s = ln.strip()
        if not s:
            if buf:
                paras.append(" ".join(buf))
                buf = []
        elif HEADER_RE.match(s) and buf:
            paras.append(" ".join(buf))
            buf = [s]
        else:
            buf.append(s)
    return [p for p in paras if p]


def run(pdf, text_file, work_dir, si_paths):
    os.makedirs(work_dir, exist_ok=True)
    sources = [("MAIN", pdf, text_file)]
    for i, sp in enumerate(si_paths or [], 1):
        sources.append(("SI%d" % i, sp, None))
    counts = {"ligatures": 0, "hyphen_joins": 0, "space_collapses": 0,
              "unit_joins": 0}
    entries, full_lines, page_stats = [], [], []
    for src, spdf, stext in sources:
        pages = extract_pages(spdf, stext)
        if pages is None:
            print("NEXT: no text in %s; use OCR then --text-file" % (spdf or src),
                  file=sys.stderr)
            sys.exit(3)
        while pages and not pages[-1].strip():
            pages.pop()  # drop trailing empty page from \f split
        for pi, ptxt in enumerate(pages, 1):
            if not ptxt.strip():
                page_stats.append({"source": src, "page": pi, "chars": 0,
                                   "paragraphs": 0, "low_text": True})
                continue
            ptxt = normalize(ptxt, counts)
            paras = paragraphs(ptxt)
            page_stats.append({"source": src, "page": pi,
                               "chars": len(ptxt.strip()),
                               "paragraphs": len(paras),
                               "low_text": len(ptxt.strip()) < 120})
            full_lines.append("===== %s page %d =====" % (src, pi))
            for qi, para in enumerate(paras, 1):
                pid = "p%03d.%03d" % (pi, qi)
                entries.append({"pid": pid, "page": pi, "source": src,
                                "text": para})
                full_lines.append("[%s] %s" % (pid, para))
    with open(os.path.join(work_dir, "textlayer.jsonl"), "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(work_dir, "fulltext.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(full_lines) + "\n")
    integrity = {
        "paragraphs": len(entries),
        "pages": len(page_stats),
        "normalizations": counts,
        "low_text_pages": ["%s:%d" % (s["source"], s["page"])
                           for s in page_stats if s["low_text"]],
        "page_stats": page_stats,
        "note": ("pages in low_text_pages are evidence-fragile: fields only "
                 "supported there must say so in notes, or become "
                 "extraction_failed when unreadable"),
    }
    with open(os.path.join(work_dir, "integrity.json"), "w", encoding="utf-8") as f:
        json.dump(integrity, f, ensure_ascii=False, indent=2)
    print("textlayer -> %d paragraphs, %d pages; low_text=%s" % (
        len(entries), len(page_stats), integrity["low_text_pages"]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--text-file")
    ap.add_argument("--si", action="append", default=[])
    ap.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    if not a.pdf and not a.text_file:
        print("need --pdf or --text-file", file=sys.stderr)
        return 2
    if a.pdf and not os.path.isfile(a.pdf):
        print("input missing: %s" % a.pdf, file=sys.stderr)
        return 2
    return run(a.pdf, a.text_file, a.work_dir, a.si)


if __name__ == "__main__":
    sys.exit(main())
