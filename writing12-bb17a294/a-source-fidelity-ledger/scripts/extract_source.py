#!/usr/bin/env python3
"""extract_source.py — provenance-anchored source extraction.

Input PDF or plain text/markdown -> an output directory (e.g. /app/work)
containing:
  source.txt               full extracted text (PDF pages joined by form feed)
  pages.json               page-anchored line map (single pseudo-page for text)
  extraction_manifest.json extraction method, file size, page count, and a
                           coverage checksum (char count per page + sha256)

Graceful degradation: if pdftotext is unavailable, or the PDF has an empty
text layer, this script exits NON-ZERO with an honest message. The skill then
marks extraction as degraded in result.json instead of fabricating content.

Stdlib only; pdftotext (Poppler) is invoked via subprocess when present.

Exit codes:
  0  success
  2  usage / input error (missing file, unsupported extension)
  3  pdftotext not found on PATH
  4  pdftotext invocation failed
  5  empty text layer / empty input
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def die(code, msg):
    print(f"extract_source: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def build_pages(text_pages):
    """Page-anchored line map. Line numbers are 1-based and continuous across
    pages, matching source.txt when the form-feed separators are read as line
    breaks."""
    pages, line_no = [], 1
    for i, ptext in enumerate(text_pages, start=1):
        n_lines = len(ptext.splitlines())
        pages.append({
            "page": i,
            "start_line": line_no,
            "end_line": line_no + max(n_lines - 1, 0),
            "char_count": len(ptext),
        })
        line_no += n_lines
    return pages


def main():
    ap = argparse.ArgumentParser(
        description="Extract source text with page-level provenance anchors.")
    ap.add_argument("input", help="input .pdf or .txt/.md file")
    ap.add_argument("-o", "--outdir", required=True,
                    help="output directory (e.g. /app/work)")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        die(2, f"input not found: {args.input}")
    size = os.path.getsize(args.input)
    ext = os.path.splitext(args.input)[1].lower()
    os.makedirs(args.outdir, exist_ok=True)

    if ext == ".pdf":
        if shutil.which("pdftotext") is None:
            die(3, "pdftotext (Poppler) not found on PATH; the PDF text layer "
                   "cannot be extracted. Mark extraction as degraded in "
                   "result.json; do NOT fabricate source content.")
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", args.input, "-"],
                capture_output=True, text=True, timeout=300)
        except Exception as exc:  # noqa: BLE001 - report honestly, then exit
            die(4, f"pdftotext invocation failed: {exc}")
        if proc.returncode != 0:
            die(4, f"pdftotext exited {proc.returncode}: "
                   f"{proc.stderr.strip()[:300]}")
        method = "pdftotext -layout"
        raw_pages = proc.stdout.split("\f")
        while raw_pages and raw_pages[-1].strip() == "":
            raw_pages.pop()
        if not raw_pages or "".join(raw_pages).strip() == "":
            die(5, "PDF has an empty text layer (scanned/image PDF?). "
                   "Extraction is degraded; do NOT fabricate source content.")
        source_text = "\f".join(raw_pages)
        text_pages = raw_pages
    elif ext in (".txt", ".md", ".markdown", ".text"):
        with open(args.input, "r", encoding="utf-8") as fh:
            source_text = fh.read()
        method = "text-passthrough (single pseudo-page)"
        if source_text.strip() == "":
            die(5, "input text file is empty.")
        text_pages = [source_text]
    else:
        die(2, f"unsupported extension {ext!r}; provide .pdf, .txt or .md")

    pages = build_pages(text_pages)

    with open(os.path.join(args.outdir, "source.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(source_text)
    with open(os.path.join(args.outdir, "pages.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"page_count": len(pages), "pages": pages},
                  fh, ensure_ascii=False, indent=2)

    manifest = {
        "input_file": os.path.abspath(args.input),
        "method": method,
        "file_size_bytes": size,
        "page_count": len(pages),
        "total_chars": sum(p["char_count"] for p in pages),
        "coverage_checksum": {
            "per_page_char_counts": [p["char_count"] for p in pages],
            "sha256_source_txt": hashlib.sha256(
                source_text.encode("utf-8")).hexdigest(),
        },
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(os.path.join(args.outdir, "extraction_manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"extract_source: method={method} pages={len(pages)} "
          f"chars={manifest['total_chars']} -> {args.outdir}")


if __name__ == "__main__":
    main()
