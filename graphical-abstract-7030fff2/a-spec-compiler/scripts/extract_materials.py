#!/usr/bin/env python3
"""extract_materials.py -- Bundle A (ga-spec-compiler), step 1.

Read the ACTUAL case inputs and build the only source-of-truth text pool the
spec checker will trust later. Never assumes content from file labels.

Usage:
  python3 extract_materials.py --input /input --outdir /app/work

Outputs in <outdir>:
  source_pool.txt        all extracted text, one block per file, formfeed between PDF pages
  sources_index.json     per-file: path, sha256, bytes, kind, pages/blocks, extraction tool
  data_files.json        parsed preview of CSV/JSON data files (headers, row counts)

Extraction chain (honest degradation, recorded per file):
  PDF : pdftotext -layout (pdf-text-tool) -> pypdf -> mark "unextracted"
  TXT/MD/CSV/TSV/JSON: direct read (utf-8, errors="replace")
  PNG/JPG/TIFF: not parsed here; if ocr-tool exists the agent may run it and
                append the transcript with tool="ocr" (see SKILL.md).
Exit code is 0 even with partial failures; failures are recorded, not hidden.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys

TEXT_EXT = {".txt", ".md", ".markdown", ".tex", ".bib", ".xml", ".html"}
DATA_EXT = {".csv", ".tsv", ".json"}
PDF_EXT = {".pdf"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_text(path, workdir):
    """Return (text, tool). Try pdftotext, then pypdf."""
    if shutil.which("pdftotext"):
        out = os.path.join(workdir, "_pdftotext_out.txt")
        proc = subprocess.run(
            ["pdftotext", "-layout", path, out],
            capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 and os.path.exists(out):
            with open(out, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
            if txt.strip():
                return txt, "pdftotext -layout"
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(path)
        pages = [(pg.extract_text() or "") for pg in reader.pages]
        txt = "\f".join(pages)
        if txt.strip():
            return txt, "pypdf"
    except Exception:
        pass
    return "", "unextracted"


def read_text_file(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def preview_data_file(path):
    """Small structural preview of a data file; full content is NOT copied."""
    ext = os.path.splitext(path)[1].lower()
    info = {"path": path, "kind": ext.lstrip(".")}
    try:
        if ext in (".csv", ".tsv"):
            dialect = "excel-tab" if ext == ".tsv" else "excel"
            with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                rows = list(csv.reader(fh, dialect=dialect))
            info["n_rows"] = max(len(rows) - 1, 0)
            info["header"] = rows[0] if rows else []
            info["first_data_row"] = rows[1] if len(rows) > 1 else []
        elif ext == ".json":
            with open(path, encoding="utf-8", errors="replace") as fh:
                obj = json.load(fh)
            if isinstance(obj, dict):
                info["top_keys"] = list(obj)[:20]
            elif isinstance(obj, list):
                info["n_items"] = len(obj)
                info["first_item_type"] = type(obj[0]).__name__ if obj else "empty"
    except Exception as exc:  # honest record, not a crash
        info["parse_error"] = str(exc)
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="/input directory (or a single file)")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    if os.path.isfile(args.input):
        files = [args.input]
    else:
        files = []
        for root, _dirs, names in os.walk(args.input):
            for name in sorted(names):
                files.append(os.path.join(root, name))
        files.sort()

    pool_blocks = []
    index = {"files": [], "tool_versions": {}}
    data_previews = []
    pdftotext_ver = subprocess.run(["pdftotext", "-v"], capture_output=True,
                                   text=True).stderr.strip().splitlines()
    index["tool_versions"]["pdftotext"] = (pdftotext_ver[0] if pdftotext_ver
                                           else "not found")

    for path in files:
        ext = os.path.splitext(path)[1].lower()
        rec = {"path": path, "bytes": os.path.getsize(path),
               "sha256": sha256_of(path)}
        if ext in PDF_EXT:
            text, tool = pdf_text(path, args.outdir)
            rec["kind"] = "pdf"
            rec["extraction"] = tool
            rec["pages"] = text.count("\f") + 1 if text else 0
            if text:
                pool_blocks.append(
                    "===== SOURCE: %s (tool: %s) =====\n%s" % (path, tool, text))
        elif ext in TEXT_EXT or ext in DATA_EXT:
            text = read_text_file(path)
            rec["kind"] = "data" if ext in DATA_EXT else "text"
            rec["extraction"] = "direct-read"
            pool_blocks.append(
                "===== SOURCE: %s (tool: direct-read) =====\n%s" % (path, text))
            if ext in DATA_EXT:
                data_previews.append(preview_data_file(path))
        elif ext in IMG_EXT:
            rec["kind"] = "image"
            rec["extraction"] = "not-parsed (run ocr-tool if it carries text)"
        else:
            rec["kind"] = "other"
            rec["extraction"] = "skipped"
        index["files"].append(rec)

    with open(os.path.join(args.outdir, "source_pool.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n\n".join(pool_blocks))
    with open(os.path.join(args.outdir, "sources_index.json"), "w",
              encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(args.outdir, "data_files.json"), "w",
              encoding="utf-8") as fh:
        json.dump(data_previews, fh, indent=2, ensure_ascii=False)

    n_ok = sum(1 for b in pool_blocks if b)
    print(json.dumps({"files_seen": len(files), "text_blocks": n_ok,
                      "data_files": len(data_previews),
                      "unextracted": [r["path"] for r in index["files"]
                                      if r.get("extraction") == "unextracted"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
