#!/usr/bin/env python3
"""ingest_pages.py -- claim-citation-aligner stage 0.

Usage: ingest_pages.py <input> <pages.jsonl>
PDF -> pdftotext (-layout then raw); otherwise plain-text read.
Writes pages.jsonl plus <pages.jsonl>.meta.json. Exit 1 on failure.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def extract(src: Path):
    if src.suffix.lower() == ".pdf" and shutil.which("pdftotext"):
        for flags, name in ((["-layout"], "pdftotext -layout"),
                            ([], "pdftotext")):
            try:
                r = subprocess.run(["pdftotext", *flags, str(src), "-"],
                                   capture_output=True, timeout=120)
            except Exception:
                continue
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace"), name
        return None, "pdftotext failed (scanned PDF? use environment OCR tool)"
    try:
        raw = src.read_bytes()
    except OSError as e:
        return None, f"read error: {e}"
    if raw[:5] == b"%PDF-":
        return None, "pdftotext unavailable and no text fallback for PDF"
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc), f"plain-read ({enc})"
        except UnicodeDecodeError:
            continue
    return None, "undecodable"


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    text, method = extract(src)
    meta = {"input": str(src), "method": method,
            "extract_status": "ok" if text else "failed", "pages": 0}
    if text:
        parts = [p for p in text.split("\f")]
        while parts and not parts[-1].strip():
            parts.pop()
        parts = parts or [text]
        meta["pages"] = len(parts)
        with out.open("w", encoding="utf-8") as fh:
            for i, p in enumerate(parts, 1):
                fh.write(json.dumps({"page": i, "text": p},
                                    ensure_ascii=False) + "\n")
    out.with_suffix(out.suffix + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    sys.exit(0 if text else 1)


if __name__ == "__main__":
    main()
