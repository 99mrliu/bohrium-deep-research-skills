#!/usr/bin/env python3
"""Cut a document library into addressable anchors (locators).

Anchor granularity: file > physical page (PDF only) > section heading >
paragraph. Every anchor carries a verbatim first sentence and char offsets
into the extracted text so any hit can be re-verified byte-for-byte.

Writes:
  anchors.jsonl       one anchor per line
  ingest_report.json  per-file extraction status (no_pdf_tool, needs_ocr,
                      read_failed, ...)

Usage: pinpoint_ingest.py LIB_ROOT ANCHORS_JSONL REPORT_JSON
"""
import json
import os
import re
import shutil
import subprocess
import sys

HEAD_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
HEAD_NUM = re.compile(r"^(\d+(?:\.\d+){0,3})[、.．\s]\s*(.{0,60}?)\s*$")
HEAD_CAPS = re.compile(r"^([A-Z][A-Z0-9 /\-]{3,60})\s*$")
PRINTED_PAGE = re.compile(r"^\s*(?:第\s*(\d+)\s*页|[-—–]\s*(\d+)\s*[-—–]|Page\s+(\d+))\s*$",
                          re.IGNORECASE)


def extract_pages(path):
    """Return (pages, status): pages is a list of page texts (1-element for
    non-PDF), status is a short string for the ingest report."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".tsv", ".log", ".json", ".tex", ".py"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return [f.read()], "text_direct"
        except OSError as e:
            return [], "read_failed: %s" % e
    if ext == ".pdf":
        exe = shutil.which("pdftotext")
        if not exe:
            return [], "no_pdf_tool"
        try:
            p = subprocess.run([exe, "-layout", path, "-"],
                               capture_output=True, timeout=180)
            if p.returncode != 0:
                return [], "pdftotext_failed"
            pages = p.stdout.decode("utf-8", "replace").split("\f")
            pages = [pg for pg in pages]
            if pages and not pages[-1].strip():
                pages.pop()
            if not any(pg.strip() for pg in pages):
                return pages, "needs_ocr"
            return pages, "pdf_pages:%d" % len(pages)
        except Exception as e:
            return [], "pdf_error: %s" % e
    if ext in (".docx", ".pptx", ".xlsx"):
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                parts = []
                for n in sorted(z.namelist()):
                    if n.endswith(".xml") and ("document" in n or "slide" in n
                                              or "sheet" in n or "shared" in n):
                        xml = z.read(n).decode("utf-8", "replace")
                        xml = re.sub(r"</w:p>|</a:p>", "\n", xml)
                        parts.append(re.sub(r"<[^>]+>", "", xml))
                text = "\n".join(parts)
                return [text], "office_xml"
        except Exception as e:
            return [], "office_failed: %s" % e
    return [], "unsupported_ext"


def detect_heading(line):
    m = HEAD_MD.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    m = HEAD_NUM.match(line)
    if m and len(line) < 70:
        return m.group(1).count(".") + 1, (m.group(1) + " " + m.group(2)).strip()
    m = HEAD_CAPS.match(line)
    if m:
        return 2, m.group(1).strip()
    return None


def printed_page_of(page_text):
    lines = [l for l in page_text.splitlines() if l.strip()]
    for line in lines[-3:]:
        m = PRINTED_PAGE.match(line)
        if m:
            return int(next(g for g in m.groups() if g))
    return None


def cut_anchors(rel, pages):
    anchors = []
    for pno, page_text in enumerate(pages, 1):
        printed = printed_page_of(page_text) if len(pages) > 1 else None
        heading_path = []
        para_buf = []
        para_start = 0
        offset = 0

        def flush(end_off):
            text = "\n".join(para_buf).strip()
            if not text:
                return
            first = re.split(r"(?<=[。！？.!?])\s*", text, 1)[0][:120]
            loc = rel
            if len(pages) > 1:
                loc += " › p%d" % pno
            if heading_path:
                loc += " › §" + "/".join(h[1] for h in heading_path[-3:])
            loc += " › ¶%d" % flush.n
            anchors.append({
                "file": rel, "page_physical": pno if len(pages) > 1 else None,
                "page_printed": printed,
                "heading": heading_path[-1][1] if heading_path else None,
                "locator": loc, "anchor_sentence": first,
                "text": text[:2000], "char_start": para_start,
                "char_end": end_off})
            flush.n += 1

        flush.n = 1
        for line in page_text.splitlines(True):
            stripped = line.strip()
            h = detect_heading(stripped) if stripped else None
            if h:
                flush(offset)
                para_buf = []
                level, title = h
                heading_path = [x for x in heading_path if x[0] < level]
                heading_path.append((level, title))
            elif stripped:
                if not para_buf:
                    para_start = offset
                para_buf.append(line.rstrip("\n"))
            else:
                flush(offset)
                para_buf = []
            offset += len(line)
        flush(offset)
    return anchors


def main():
    lib_root, out_jsonl, report_p = sys.argv[1], sys.argv[2], sys.argv[3]
    report = {}
    total = 0
    with open(out_jsonl, "w", encoding="utf-8") as out:
        for base, dirs, names in os.walk(lib_root):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, lib_root)
                pages, status = extract_pages(path)
                report[rel] = status
                if not pages:
                    continue
                anchors = cut_anchors(rel, pages)
                total += len(anchors)
                for a in anchors:
                    out.write(json.dumps(a, ensure_ascii=False) + "\n")
    with open(report_p, "w", encoding="utf-8") as f:
        json.dump({"library_root": os.path.abspath(lib_root),
                   "n_anchors": total, "files": report},
                  f, ensure_ascii=False, indent=2)
    print(json.dumps({"n_anchors": total, "n_files": len(report)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
