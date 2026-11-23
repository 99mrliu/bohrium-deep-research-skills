#!/usr/bin/env python3
"""mine_sources.py -- Bundle C (ga-audit-loop), phase 0: evidence pool.

Builds a citable evidence pool from the case materials. Unlike a plain text
dump, every block is keyed (FILE#BLOCK) so ledger entries can point at an
exact, stable location, and every numeric token is indexed so the verifier
can ask "where does this number live?" in one lookup.

Usage:
  python3 mine_sources.py --materials /input --work /app/work

Outputs in <work>:
  evidence_pool.jsonl   one JSON per line: {key, file, sha8, block, text}
  number_index.json     {"12.5": [{"key": ..., "context": "..."}], ...}
  pool_report.json      counts, per-file sha256, tools used, files that could
                        not be mined (listed, never silently dropped)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")
MINABLE = {".txt", ".md", ".csv", ".tsv", ".json", ".tex", ".xml", ".html"}


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf(path, work):
    if shutil.which("pdftotext"):
        dst = os.path.join(work, "_mine_pdf.txt")
        p = subprocess.run(["pdftotext", "-layout", path, dst],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0 and os.path.exists(dst):
            with open(dst, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
            if txt.strip():
                return txt, "pdftotext"
    return "", "failed"


def blocks_of(text, kind):
    """Split into citable blocks: formfeed pages for PDFs, paragraphs else."""
    if kind == "pdf":
        raw = text.split("\f")
        return [("page-%d" % (i + 1), t) for i, t in enumerate(raw) if t.strip()]
    raw = re.split(r"\n\s*\n", text)
    return [("para-%d" % (i + 1), t) for i, t in enumerate(raw) if t.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--materials", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    paths = []
    if os.path.isfile(args.materials):
        paths = [args.materials]
    else:
        for root, _d, names in os.walk(args.materials):
            for n in sorted(names):
                paths.append(os.path.join(root, n))
        paths.sort()

    pool_fh = open(os.path.join(args.work, "evidence_pool.jsonl"), "w",
                   encoding="utf-8")
    number_index = {}
    report = {"files": [], "tools": {}, "unminable": []}

    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        sha = file_sha(path)
        frep = {"file": path, "sha256": sha, "bytes": os.path.getsize(path)}
        if ext == ".pdf":
            text, tool = extract_pdf(path, args.work)
            kind = "pdf"
        elif ext in MINABLE:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text, tool, kind = fh.read(), "direct", ext.lstrip(".")
        else:
            report["unminable"].append({"file": path,
                                        "reason": "extension %s not minable; "
                                        "use ocr-tool for scans" % ext})
            report["files"].append(frep)
            continue
        frep["tool"] = tool
        report["tools"][tool] = report["tools"].get(tool, 0) + 1
        if not text.strip():
            report["unminable"].append({"file": path,
                                        "reason": "no text extracted"})
            report["files"].append(frep)
            continue
        base = os.path.basename(path)
        for bi, (btag, btext) in enumerate(blocks_of(text, kind)):
            key = "%s#%s" % (base, btag)
            pool_fh.write(json.dumps({
                "key": key, "file": path, "sha8": sha[:8],
                "block": btag, "text": btext}, ensure_ascii=False) + "\n")
            for m in NUM.finditer(btext):
                tok = m.group(0).replace(",", "")
                ctx = btext[max(0, m.start() - 60):m.end() + 60]
                number_index.setdefault(tok, []).append(
                    {"key": key, "context": ctx.strip()[:140]})
        frep["blocks"] = bi + 1 if text.strip() else 0
        report["files"].append(frep)

    pool_fh.close()
    with open(os.path.join(args.work, "number_index.json"), "w",
              encoding="utf-8") as fh:
        json.dump(number_index, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(args.work, "pool_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps({"files": len(report["files"]),
                      "blocks": sum(f.get("blocks", 0)
                                    for f in report["files"]),
                      "numbers_indexed": len(number_index),
                      "unminable": len(report["unminable"])}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
