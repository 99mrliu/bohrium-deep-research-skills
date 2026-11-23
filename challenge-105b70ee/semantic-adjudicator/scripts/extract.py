#!/usr/bin/env python3
"""Light text indexer for the semantic-adjudicator skill.

Extracts the paper into grep-friendly files under --work-dir:
  pages.txt      full text with [PAGE n] markers (pdftotext -layout)
  sentences.tsv  line-numbered sentences: <idx>\t<page>\t<sentence>

Exit codes: 0 ok; 2 input missing; 3 no text layer (use OCR, --text-file);
4 no extractor available.
"""
import argparse
import os
import re
import subprocess
import sys

SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
LIG = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
       "\ufb03": "ffi", "\ufb04": "ffl"}


def pdf_pages(pdf):
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
              "tool, save text, rerun with --text-file FILE", file=sys.stderr)
        sys.exit(4)
    except Exception:  # noqa: BLE001
        return None
    return None


def norm(t):
    for k, v in LIG.items():
        t = t.replace(k, v)
    t = re.sub(r"(\w)[\u00ad-]\n(\w)", r"\1\2", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t


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
    out_pages, out_sents, idx = [], [], 0
    for src, pdf, tf in jobs:
        if tf:
            txt = open(tf, encoding="utf-8").read()
            pages = txt.split("\f")
            pages = pages if len(pages) > 1 else [txt]
        elif pdf and os.path.isfile(pdf):
            pages = pdf_pages(pdf)
            if pages is None or not any(pg.strip() for pg in pages):
                print("NEXT: no text layer in %s — OCR then --text-file" % pdf,
                      file=sys.stderr)
                return 3
        else:
            print("input missing for %s" % src, file=sys.stderr)
            return 2
        while pages and not pages[-1].strip():
            pages.pop()
        for pi, ptxt in enumerate(pages, 1):
            ptxt = norm(ptxt)
            out_pages.append("===== %s [PAGE %d] =====" % (src, pi))
            out_pages.append(ptxt)
            for s in SENT_SPLIT.split(ptxt.replace("\n", " ")):
                s = s.strip()
                if len(s) > 2:
                    idx += 1
                    out_sents.append("%d\t%s:%d\t%s" % (idx, src, pi, s))
    with open(os.path.join(a.work_dir, "pages.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out_pages) + "\n")
    with open(os.path.join(a.work_dir, "sentences.tsv"), "w", encoding="utf-8") as f:
        f.write("\n".join(out_sents) + "\n")
    print("index -> %d sentences, %d page blocks" % (idx, len(out_pages) // 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
