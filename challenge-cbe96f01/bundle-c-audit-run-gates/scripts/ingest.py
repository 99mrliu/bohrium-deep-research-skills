#!/usr/bin/env python3
"""ingest.py -- audit-run-gates stage 0 input parsing (gate G0, part 1).

Usage: ingest.py <input> <out pages.jsonl>
Deterministic: same input bytes -> same output bytes (no timestamps).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_pdftotext(src: Path, layout: bool):
    if not shutil.which("pdftotext"):
        return None
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(src), "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:
        return None
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.decode("utf-8", "replace")
    return None


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    text, method = None, None
    if src.suffix.lower() == ".pdf":
        for layout in (True, False):
            text = run_pdftotext(src, layout)
            if text:
                method = "pdftotext -layout" if layout else "pdftotext"
                break
    if text is None:
        try:
            head = src.read_bytes()
        except OSError:
            head = b""
        if head and not head.startswith(b"%PDF-"):
            try:
                text = head.decode("utf-8")
                method = "plain-read"
            except UnicodeDecodeError:
                text = None
    meta = {"input": str(src), "method": method,
            "extract_status": "ok" if text else "failed"}
    if text is None:
        meta["note"] = ("all extractors failed; scanned PDF requires the "
                        "environment OCR tool")
    pages = []
    if text:
        pages = text.split("\f")
        while pages and not pages[-1].strip():
            pages.pop()
        pages = pages or [text]
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            for i, p in enumerate(pages, 1):
                fh.write(json.dumps({"page": i, "text": p},
                                    ensure_ascii=False) + "\n")
    meta["pages"] = len(pages)
    Path(str(out) + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    sys.exit(0 if text else 1)


if __name__ == "__main__":
    main()
