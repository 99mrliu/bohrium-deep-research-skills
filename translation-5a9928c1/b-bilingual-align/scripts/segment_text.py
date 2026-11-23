#!/usr/bin/env python3
r"""segment_text.py — deterministic source segmentation into paragraphs.jsonl.

Reads .pdf (via `pdftotext -layout`, page separator = form-feed \f) or
.txt/.md directly, and emits one JSON object per paragraph:
  {"seg_id": "P0001", "page_start": 1, "page_end": 2,
   "char_count": 123, "text": "..."}

Rules (see references/segmentation_rules.md for the full spec):
  * split raw text into pages by \f
  * hyphenation repair: a line ending with '-' followed by a line starting
    lowercase (within the same paragraph) is joined, counting hyphen_joins
  * soft unwrap: consecutive non-empty lines merge into one paragraph
  * blank line = paragraph boundary
  * running header/footer: an identical non-empty line appearing as the
    first or last non-empty line of >=3 pages is dropped
  * pure page-number lines (^\d{1,4}$) are skipped
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

PAGE_NUM_RE = re.compile(r"^\d{1,4}$")


def read_source(path):
    """Return (text, warnings). PDF goes through pdftotext -layout."""
    warnings = []
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        if subprocess.call(["which", "pdftotext"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) != 0:
            sys.stderr.write(
                "ERROR: pdftotext not found. Install poppler, or pass a "
                ".txt/.md file extracted beforehand.\n")
            sys.exit(2)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tmp_path = tf.name
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", path, tmp_path],
                capture_output=True, text=True)
            if proc.returncode != 0:
                sys.stderr.write("ERROR: pdftotext failed: %s\n"
                                 % proc.stderr.strip())
                sys.exit(2)
            with open(tmp_path, "r", encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
        finally:
            os.unlink(tmp_path)
        if not text.strip():
            warnings.append(
                "pdftotext produced empty text: the PDF may be a scanned "
                "image with no text layer (OCR required).")
    elif ext in (".txt", ".md"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        sys.stderr.write("ERROR: unsupported source extension: %s\n" % ext)
        sys.exit(2)
    return text, warnings


def is_lower_start(line):
    """True if the first alphabetic character of the line is lowercase."""
    for ch in line.strip():
        if ch.isalpha():
            return ch.islower()
        if ch.isdigit():
            return False
    return False


def segment(text):
    """Segment raw text into pages/lines/paragraphs + a report dict."""
    pages = text.split("\f")
    # A trailing \f may create an empty final chunk; drop fully empty pages
    # only at the very end, but keep count of non-trivial pages.
    all_lines = []  # (page_no, line)
    for pno, page in enumerate(pages, start=1):
        for line in page.split("\n"):
            all_lines.append((pno, line.rstrip()))

    # --- running header/footer detection -------------------------------
    # key: line string; value: set of pages where it is first-or-last
    edge_pages = {}
    page_map = {}
    for pno, line in all_lines:
        page_map.setdefault(pno, []).append(line)
    for pno in sorted(page_map):
        nonempty = [ln.strip() for ln in page_map[pno] if ln.strip()]
        if not nonempty:
            continue
        for edge in (nonempty[0], nonempty[-1]):
            edge_pages.setdefault(edge, set()).add(pno)

    repeated = {ln for ln, ps in edge_pages.items() if len(ps) >= 3}
    dropped_repeated = sorted(repeated)

    # --- per-page line processing --------------------------------------
    hyphen_joins = 0
    page_number_lines_dropped = 0
    paragraphs = []  # dicts: {page_start, page_end, parts:[...], pending:str}
    warnings = []
    cur = None

    def flush():
        nonlocal cur
        if cur is not None and cur["parts"]:
            text_parts = []
            for p in cur["parts"]:
                text_parts.append(p)
            full = " ".join(text_parts)
            paragraphs.append({
                "page_start": cur["page_start"],
                "page_end": cur["page_end"],
                "text": full,
            })
        cur = None

    for pno, raw in all_lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if line in repeated:
            continue  # running header/footer
        if PAGE_NUM_RE.match(line):
            page_number_lines_dropped += 1
            continue
        # --- start new paragraph if page turned ------------------------
        if cur is None:
            cur = {"page_start": pno, "page_end": pno, "parts": []}
        # --- hyphenation repair (only within same paragraph) -----------
        if cur["parts"] and cur["page_end"] == pno:
            prev = cur["parts"][-1]
            nxt = line
            if prev.endswith("-") and is_lower_start(nxt):
                cur["parts"][-1] = prev[:-1] + nxt
                hyphen_joins += 1
                cur["page_end"] = pno
                continue
        cur["parts"].append(line)
        cur["page_end"] = pno
    flush()

    # --- assign stable seg ids ------------------------------------------
    out = []
    for i, para in enumerate(paragraphs, start=1):
        out.append({
            "seg_id": "P%04d" % i,
            "page_start": para["page_start"],
            "page_end": para["page_end"],
            "char_count": len(para["text"]),
            "text": para["text"],
        })

    nonempty_pages = sum(1 for p in page_map.values()
                         if any(ln.strip() for ln in p))
    report = {
        "pages": max(nonempty_pages, 1) if text.strip() else 0,
        "paragraphs": len(out),
        "hyphen_joins": hyphen_joins,
        "dropped_repeated_lines": dropped_repeated,
        "page_number_lines_dropped": page_number_lines_dropped,
        "warnings": warnings,
    }
    return out, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="source .pdf/.txt/.md file")
    ap.add_argument("--out", required=True, help="paragraphs.jsonl output")
    ap.add_argument("--report", required=True, help="seg_report.json output")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.stderr.write("ERROR: source not found: %s\n" % args.src)
        sys.exit(2)

    text, warnings = read_source(args.src)
    paras, report = segment(text)
    report["warnings"] = warnings + report["warnings"]
    if report["paragraphs"] == 0:
        report["warnings"].append("0 paragraphs produced; check text layer.")

    with open(args.out, "w", encoding="utf-8") as fh:
        for para in paras:
            fh.write(json.dumps(para, ensure_ascii=False) + "\n")
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("segmented %d paragraphs from %d page(s) -> %s"
          % (len(paras), report["pages"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
