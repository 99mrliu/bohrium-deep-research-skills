#!/usr/bin/env python3
"""Deterministic stage workers (run-controller skill): extract, bank.

extract: PDF (--pdf, optional --si) or pre-extracted text (--text-file)
         -> <work>/pages.txt with [PAGE n] markers.
         Exit 3 = no text layer (OCR then --text-file); 4 = no extractor.
bank:    <work>/pages.txt -> <work>/bank.jsonl (quantified/cued sentences
         with bank_id, page, verbatim quote).
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
QUANT = re.compile(
    r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?\s*(%|‰|ppm|mAh|Wh|kg|mg|g|cm|mm|nm|µm|um"
    r"|mV|kV|V|mA|A|W|kW|MPa|GPa|Pa|K|°C|deg C|s|min|h|Hz|mol|mM|M|J|kJ|mL|L"
    r"|cycles?)\b|\d\s*[–—]\s*\d|[<>≥≤]\s*\d", re.IGNORECASE)
CUE = re.compile(
    r"\b(we (demonstrate|show|conclude|report)|in conclusion|limitation|"
    r"limited to|remains? (unclear|unreported)|may|might|suggests?|possibly)\b"
    r"|表明|证明|局限|可能|提示|有望", re.IGNORECASE)


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
        print("NEXT: no pdftotext/pypdf — OCR via environment tool, then "
              "rerun with --text-file", file=sys.stderr)
        sys.exit(4)
    except Exception:  # noqa: BLE001
        return None
    return None


def cmd_extract(a):
    jobs = [("MAIN", a.pdf, a.text_file)] + \
           [("SI%d" % i, p, None) for i, p in enumerate(a.si, 1)]
    out, npages = [], 0
    for src, pdf, tf in jobs:
        pages = pages_of(pdf, tf)
        if pages is None or not any(p.strip() for p in pages):
            print("NEXT: no text layer in %s — OCR then --text-file"
                  % (pdf or src), file=sys.stderr)
            return 3
        while pages and not pages[-1].strip():
            pages.pop()
        for pi, ptxt in enumerate(pages, 1):
            for k, v in LIG.items():
                ptxt = ptxt.replace(k, v)
            ptxt = re.sub(r"(\w)[\u00ad-]\n(\w)", r"\1\2", ptxt)
            out.append("===== %s [PAGE %d] =====" % (src, pi))
            out.append(ptxt)
            npages += 1
    with open(os.path.join(a.work_dir, "pages.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("extract: %d pages -> pages.txt" % npages)
    return 0


def cmd_bank(a):
    pt = os.path.join(a.work_dir, "pages.txt")
    if not os.path.isfile(pt):
        print("pages.txt missing — run extract first", file=sys.stderr)
        return 2
    page, entries, eid = 0, [], 0
    for line in open(pt, encoding="utf-8"):
        m = re.match(r"===== (\S+) \[PAGE (\d+)\] =====", line)
        if m:
            page = int(m.group(2))
            continue
        for s in SENT_SPLIT.split(line.replace("\n", " ")):
            s = re.sub(r"\s{2,}", " ", s).strip()
            if len(s) < 3:
                continue
            if QUANT.search(s) or CUE.search(s):
                eid += 1
                entries.append({"bank_id": "W%04d" % eid, "page": page,
                                "quote": s,
                                "kind": "quantified" if QUANT.search(s) else "cued"})
    with open(os.path.join(a.work_dir, "bank.jsonl"), "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print("bank: %d entries -> bank.jsonl" % eid)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--pdf")
    p.add_argument("--si", action="append", default=[])
    p.add_argument("--text-file")
    p.add_argument("--work-dir", required=True)
    p = sub.add_parser("bank")
    p.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    return {"extract": cmd_extract, "bank": cmd_bank}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
