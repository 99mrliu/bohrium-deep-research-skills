#!/usr/bin/env python3
"""chunk_source.py -- window-chunk a paper for evidence retrieval.

Anchor scheme: ``c<page>-<seq>`` (1-based page, 1-based chunk sequence within
the page). Chunks are character windows (default 1200 chars, 200 overlap)
over the page text, with byte offsets recorded so any quote can be
byte-located. Pages come from form-feed splits or pdftotext output.

Output chunks.json:
  {"doc_id", "sha256", "backend", "chunk_chars", "overlap",
   "chunks": [{"anchor", "page", "seq", "start", "end", "text"}]}

Standard library only. Failure -> status unreadable + handover, never a crash.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


def extract(args):
    if args.text_file:
        with open(args.text_file, "rb") as fh:
            raw = fh.read()
        return raw.decode("utf-8", errors="replace"), raw, "text-file", None
    with open(args.pdf, "rb") as fh:
        raw = fh.read()
    if not shutil.which("pdftotext"):
        return None, raw, None, "pdftotext unavailable; export text with platform tools"
    out_txt = os.path.join(args.out, "plain.txt")
    proc = subprocess.run(["pdftotext", args.pdf, out_txt],
                          capture_output=True, text=True, timeout=240)
    if proc.returncode != 0:
        return None, raw, None, "pdftotext failed: " + proc.stderr.strip()[:300]
    with open(out_txt, encoding="utf-8", errors="replace") as fh:
        return fh.read(), raw, "pdftotext-plain", None


def chunk_pages(text, size, overlap):
    chunks = []
    for pno, page in enumerate(text.split("\f"), start=1):
        page = page.strip("\n")
        if not page.strip():
            continue
        seq = 0
        start = 0
        while start < len(page):
            seq += 1
            end = min(len(page), start + size)
            piece = page[start:end]
            chunks.append({"anchor": "c%d-%d" % (pno, seq), "page": pno, "seq": seq,
                           "start": start, "end": end, "text": piece})
            if end == len(page):
                break
            start = end - overlap
    return chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--text-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", default="doc")
    ap.add_argument("--chunk-chars", type=int, default=1200)
    ap.add_argument("--overlap", type=int, default=200)
    args = ap.parse_args()
    if not args.pdf and not args.text_file:
        ap.error("one of --pdf / --text-file is required")
    os.makedirs(args.out, exist_ok=True)
    text, raw, backend, error = extract(args)
    if text is None:
        result = {"doc_id": args.case_id, "sha256": hashlib.sha256(raw).hexdigest(),
                  "backend": None, "status": "unreadable", "reason": error,
                  "handover": "export text with the platform PDF/OCR tools and rerun "
                              "with --text-file", "chunks": []}
    else:
        chunks = chunk_pages(text, args.chunk_chars, args.overlap)
        result = {"doc_id": args.case_id, "sha256": hashlib.sha256(raw).hexdigest(),
                  "backend": backend, "status": "ok",
                  "chunk_chars": args.chunk_chars, "overlap": args.overlap,
                  "chunks": chunks}
    with open(os.path.join(args.out, "chunks.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    print(json.dumps({"status": result["status"],
                      "chunks": len(result.get("chunks", []))}, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 3


if __name__ == "__main__":
    sys.exit(main())
