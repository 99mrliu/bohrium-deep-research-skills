#!/usr/bin/env python3
"""ingest_text.py -- number-recompute-core stage 0.

Usage: ingest_text.py <input> <pages.jsonl>
Deterministic; pdftotext preferred, plain-text fallback.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    text, method = None, None
    if src.suffix.lower() == ".pdf" and shutil.which("pdftotext"):
        for flags in (["-layout"], []):
            try:
                r = subprocess.run(["pdftotext", *flags, str(src), "-"],
                                   capture_output=True, timeout=120)
            except Exception:
                continue
            if r.returncode == 0 and r.stdout.strip():
                text = r.stdout.decode("utf-8", "replace")
                method = "pdftotext " + (" ".join(flags) or "raw")
                break
    if text is None:
        try:
            raw = src.read_bytes()
            if not raw.startswith(b"%PDF-"):
                text = raw.decode("utf-8")
                method = "plain-read"
        except (OSError, UnicodeDecodeError):
            text = None
    meta = {"input": str(src), "method": method,
            "extract_status": "ok" if text else "failed"}
    n = 0
    if text:
        pages = text.split("\f")
        while pages and not pages[-1].strip():
            pages.pop()
        pages = pages or [text]
        n = len(pages)
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            for i, p in enumerate(pages, 1):
                fh.write(json.dumps({"page": i, "text": p},
                                    ensure_ascii=False) + "\n")
    meta["pages"] = n
    Path(str(out) + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    sys.exit(0 if text else 1)


if __name__ == "__main__":
    main()
