#!/usr/bin/env python3
"""ingest_text.py -- source-truth-gate stage 0: material -> pages.jsonl

Tries, in order: pdftotext -layout, pdftotext raw, plain-text read.
Writes pages.jsonl (one {"page": n, "text": ...} per line) and a meta file.
Pure stdlib; pdftotext is invoked only if found on PATH.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PAGE_BREAK = "\f"


def try_pdftotext(src: Path, layout: bool):
    if not shutil.which("pdftotext"):
        return None
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(src), "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout.decode("utf-8", errors="replace")


def read_plain(src: Path):
    try:
        data = src.read_bytes()
    except OSError:
        return None
    if b"%PDF" in data[:16]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except Exception:
            return None


def split_pages(text: str):
    parts = text.split(PAGE_BREAK)
    pages = [p for p in parts]
    while pages and not pages[-1].strip():
        pages.pop()
    if not pages:
        pages = [text]
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--meta", default=None)
    args = ap.parse_args()

    src = Path(args.input)
    meta = {"input": str(src), "method": None, "extract_status": "failed",
            "pages": 0, "notes": []}
    text = None
    if not src.exists():
        meta["notes"].append("input file does not exist")
    else:
        if src.suffix.lower() == ".pdf":
            for layout, name in ((True, "pdftotext -layout"), (False, "pdftotext")):
                text = try_pdftotext(src, layout)
                if text:
                    meta["method"] = name
                    break
            if text is None:
                meta["notes"].append(
                    "pdftotext unavailable or yielded empty text; if this is a "
                    "scanned PDF, OCR via the environment OCR tool is required")
        if text is None:
            text = read_plain(src)
            if text:
                meta["method"] = "plain-read"
    if text:
        pages = split_pages(text)
        meta["extract_status"] = "ok"
        meta["pages"] = len(pages)
        with open(args.out, "w", encoding="utf-8") as fh:
            for i, p in enumerate(pages, 1):
                fh.write(json.dumps({"page": i, "text": p},
                                    ensure_ascii=False) + "\n")
    meta_path = args.meta or (args.out + ".meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False))
    sys.exit(0 if meta["extract_status"] == "ok" else 1)


if __name__ == "__main__":
    main()
