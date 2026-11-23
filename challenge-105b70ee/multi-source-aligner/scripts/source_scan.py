#!/usr/bin/env python3
"""Source scanner (multi-source-aligner skill).

Classifies input PDFs into sources (MAIN, SI1, ...), extracts text, and
segments each source into region-tagged records:
  body    narrative sentences
  table   table lines (kept whole, with the table caption attached)
  caption figure/table caption lines

Output: <work>/sources.jsonl  {"source","region","page","rid","text"}
        <work>/sources_stats.json

Exit codes: 0 ok; 2 input missing; 3 no text layer; 4 no extractor.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
LIG = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
       "\ufb03": "ffi", "\ufb04": "ffl"}
CAPTION_RE = re.compile(
    r"^\s*(figure|fig\.?|table|scheme|chart)\s*[sS]?\d+|^\s*(图|表)\s*\d+",
    re.IGNORECASE)
SI_NAME = re.compile(r"(supp|_si\b|\bsi\b|mmc|extdata|supporting)", re.IGNORECASE)
TABLE_LINE = re.compile(r"\||\S\s{3,}\S\s{3,}\S")


def pages_of(pdf, text_file):
    if text_file:
        t = open(text_file, encoding="utf-8").read()
        ps = t.split("\f")
        return ps if len(ps) > 1 else [t]
    try:
        p = subprocess.run(["pdftotext", "-layout", pdf, "-"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.split("\f")
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        from pypdf import PdfReader
        return [pg.extract_text() or "" for pg in PdfReader(pdf).pages]
    except ImportError:
        print("NEXT: no pdftotext/pypdf — OCR via environment tool, save "
              "text, rerun with --text-file-main/--text-file-si", file=sys.stderr)
        sys.exit(4)
    except Exception:  # noqa: BLE001
        return None
    return None


def segment(text, source, page, start_rid):
    """Region-tag one page of text. Returns (records, next_rid)."""
    records, rid = [], start_rid
    lines = [re.sub(r"[ \t]{2,}", " ", ln).strip()
             for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    def flush_body(buf):
        nonlocal rid
        if not buf:
            return
        para = " ".join(buf)
        for s in SENT_SPLIT.split(para):
            s = s.strip()
            if len(s) > 2:
                rid += 1
                records.append({"source": source, "region": "body",
                                "page": page, "rid": "r%05d" % rid, "text": s})

    buf = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if CAPTION_RE.match(ln):
            flush_body(buf)
            buf = []
            rid += 1
            records.append({"source": source, "region": "caption",
                            "page": page, "rid": "r%05d" % rid, "text": ln})
            if re.match(r"^\s*(table|表)", ln, re.IGNORECASE):
                # table caption: attach following table-like lines
                i += 1
                while i < len(lines) and TABLE_LINE.search(lines[i]) \
                        and not CAPTION_RE.match(lines[i]):
                    rid += 1
                    records.append({"source": source, "region": "table",
                                    "page": page, "rid": "r%05d" % rid,
                                    "text": lines[i], "caption": ln})
                    i += 1
                continue
            i += 1
            continue
        buf.append(ln)
        i += 1
    flush_body(buf)
    return records, rid


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--text-file-main")
    ap.add_argument("--text-file-si", action="append", default=[])
    a = ap.parse_args()
    if not os.path.isdir(a.input_dir):
        print("input dir missing: %s" % a.input_dir, file=sys.stderr)
        return 2
    os.makedirs(a.work_dir, exist_ok=True)
    pdfs = sorted(f for f in os.listdir(a.input_dir) if f.lower().endswith(".pdf"))
    mains = [f for f in pdfs if not SI_NAME.search(f)]
    sis = [f for f in pdfs if SI_NAME.search(f)]
    jobs = []
    if mains:
        jobs.append(("MAIN", os.path.join(a.input_dir, mains[0]),
                     a.text_file_main))
    elif a.text_file_main:
        jobs.append(("MAIN", None, a.text_file_main))
    for i, f in enumerate(sis, 1):
        tf = a.text_file_si[i - 1] if i <= len(a.text_file_si) else None
        jobs.append(("SI%d" % i, os.path.join(a.input_dir, f), tf))
    if not jobs:
        print("no PDFs found in %s" % a.input_dir, file=sys.stderr)
        return 2
    all_recs, stats, rid = [], {}, 0
    for src, pdf, tf in jobs:
        pages = pages_of(pdf, tf)
        if pages is None or not any(p.strip() for p in pages):
            print("NEXT: no text layer in %s — OCR then --text-file" % (pdf or src),
                  file=sys.stderr)
            return 3
        while pages and not pages[-1].strip():
            pages.pop()
        n_before = len(all_recs)
        for pi, ptxt in enumerate(pages, 1):
            for k, v in LIG.items():
                ptxt = ptxt.replace(k, v)
            ptxt = re.sub(r"(\w)[\u00ad-]\n(\w)", r"\1\2", ptxt)
            recs, rid = segment(ptxt, src, pi, rid)
            all_recs.extend(recs)
        stats[src] = {"pages": len(pages),
                      "records": len(all_recs) - n_before,
                      "regions": {}}
        for r in all_recs[n_before:]:
            stats[src]["regions"][r["region"]] = \
                stats[src]["regions"].get(r["region"], 0) + 1
    with open(os.path.join(a.work_dir, "sources.jsonl"), "w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(a.work_dir, "sources_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("scan -> %d records from %s" % (len(all_recs),
          ", ".join("%s(%dp)" % (s, st["pages"]) for s, st in stats.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
