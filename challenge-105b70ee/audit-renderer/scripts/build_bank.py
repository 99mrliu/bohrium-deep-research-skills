#!/usr/bin/env python3
"""Build the page-tagged text layer and evidence bank (audit-renderer).

Outputs under --work-dir:
  layer.jsonl      {"page","source","sid","text"} per sentence (verbatim)
  bank.jsonl       {"bank_id","page","source","quote","kind"} for
                   quantified or cued sentences
  layer_stats.json sentence/page counts

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
QUANT = re.compile(
    r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?\s*(%|‰|ppm|mAh|Wh|kg|mg|g|cm|mm|nm|µm|um"
    r"|mV|kV|V|mA|A|W|kW|MPa|GPa|Pa|K|°C|deg C|s|min|h|Hz|mol|mM|M|J|kJ|mL|L"
    r"|cycles?)?\b|\d\s*[–—]\s*\d|[<>≥≤]\s*\d", re.IGNORECASE)
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
        print("NEXT: no pdftotext/pypdf — use the environment pdf-text/ocr "
              "tool, save text, rerun --text-file FILE", file=sys.stderr)
        sys.exit(4)
    except Exception:  # noqa: BLE001
        return None
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--si", action="append", default=[])
    ap.add_argument("--text-file")
    ap.add_argument("--work-dir", required=True)
    a = ap.parse_args()
    if not a.pdf and not a.text_file:
        print("need --pdf or --text-file", file=sys.stderr)
        return 2
    os.makedirs(a.work_dir, exist_ok=True)
    jobs = [("MAIN", a.pdf, a.text_file)] + \
           [("SI%d" % i, p, None) for i, p in enumerate(a.si, 1)]
    layer, bank, eid, sid = [], [], 0, 0
    for src, pdf, tf in jobs:
        pages = pages_of(pdf, tf)
        if pages is None or not any(p.strip() for p in pages):
            print("NEXT: no text layer in %s — OCR then --text-file" % (pdf or src),
                  file=sys.stderr)
            return 3
        while pages and not pages[-1].strip():
            pages.pop()
        for pi, ptxt in enumerate(pages, 1):
            for k, v in LIG.items():
                ptxt = ptxt.replace(k, v)
            ptxt = re.sub(r"(\w)[\u00ad-]\n(\w)", r"\1\2", ptxt)
            ptxt = re.sub(r"[ \t]{2,}", " ", ptxt)
            for s in SENT_SPLIT.split(ptxt.replace("\n", " ")):
                s = s.strip()
                if len(s) < 3:
                    continue
                sid += 1
                layer.append({"sid": sid, "page": pi, "source": src, "text": s})
                if QUANT.search(s) or CUE.search(s):
                    eid += 1
                    bank.append({"bank_id": "B%04d" % eid, "page": pi,
                                 "source": src, "quote": s,
                                 "kind": "quantified" if QUANT.search(s)
                                 else "cued"})
    with open(os.path.join(a.work_dir, "layer.jsonl"), "w", encoding="utf-8") as f:
        for e in layer:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(os.path.join(a.work_dir, "bank.jsonl"), "w", encoding="utf-8") as f:
        for b in bank:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    with open(os.path.join(a.work_dir, "layer_stats.json"), "w", encoding="utf-8") as f:
        json.dump({"sentences": sid, "bank_entries": eid,
                   "pages": max((e["page"] for e in layer), default=0)},
                  f, indent=2)
    print("layer -> %d sentences; bank -> %d entries" % (sid, eid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
