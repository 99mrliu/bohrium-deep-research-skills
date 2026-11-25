#!/usr/bin/env python3
"""pdf_text.py — tiny PDF text extractor producing work/paper.txt.

Primary path: external `pdftotext` (found via shutil.which).
Fallback: pure-stdlib extraction of `( ... ) Tj` strings from uncompressed
content streams — enough to ground plan evidence in simple PDFs.

Not this bundle's center of gravity; kept deliberately small.
Writes work/paper.txt plus work/paper.txt.meta.json recording the method.
"""
import json
import os
import re
import shutil
import subprocess
import sys

INPUT_DIR = os.environ.get("CASE_INPUT_DIR", "/input")
WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
TJ_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)\s*Tj")


def find_pdf():
    for root, _dirs, files in os.walk(INPUT_DIR):
        for name in sorted(files):
            if name.lower().endswith(".pdf"):
                return os.path.join(root, name)
    return None


def unescape_pdf_string(raw: bytes) -> str:
    out, i = [], 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            mapping = {b"n": "\n", b"r": "\r", b"t": "\t", b"(": "(", b")": ")", b"\\": "\\"}
            out.append(mapping.get(nxt, nxt.decode("latin-1")))
            i += 2
        else:
            out.append(ch.decode("latin-1"))
            i += 1
    return "".join(out)


def fallback_extract(pdf_path):
    with open(pdf_path, "rb") as f:
        data = f.read()
    lines = [unescape_pdf_string(m.group(1)) for m in TJ_RE.finditer(data)]
    return "\n".join(lines)


def main():
    pdf = find_pdf()
    if not pdf:
        print(f"pdf_text: ERROR no PDF found under {INPUT_DIR}", file=sys.stderr)
        return 1
    os.makedirs(WORK_DIR, exist_ok=True)
    out_path = os.path.join(WORK_DIR, "paper.txt")
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        p = subprocess.run([pdftotext, pdf, "-"], capture_output=True, timeout=300)
        text = p.stdout.decode("utf-8", errors="replace")
        method = f"pdftotext ({pdftotext})"
    else:
        text = fallback_extract(pdf)
        method = "stdlib-fallback (literal Tj strings; pdftotext not available)"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    meta = {"source_pdf": pdf, "method": method, "chars": len(text)}
    with open(out_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"pdf_text: {pdf} -> {out_path} ({len(text)} chars, method: {method})")
    if not text.strip():
        print("pdf_text: WARNING extracted text is empty — plan evidence cannot be grounded", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
