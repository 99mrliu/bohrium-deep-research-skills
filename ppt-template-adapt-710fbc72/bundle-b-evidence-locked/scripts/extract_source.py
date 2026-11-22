#!/usr/bin/env python3
"""Extract a source index from the case's paper PDF (and optional figure
files) so that every later claim can be checked against actual text.

Produces source_index.json:
- per-page text (pdftotext -layout; falls back to PyMuPDF, then to OCR via
  the runtime ocr tool if the text layer is empty — flagged, not silent)
- detected section headings per page (font-size heuristic is unreliable from
  pdftotext, so headings are matched from common academic patterns and
  numbered-heading shapes)
- an image inventory per page (pdfimages -list when available, else PyMuPDF)
- sha256 of every input file, so the evidence map pins exact file versions

Usage:
    python extract_source.py --pdf paper.pdf [--figures-dir DIR] \
        --out source_index.json
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HEADING_RE = re.compile(
    r'^\s*((?:[0-9]+(?:\.[0-9]+)*[.\s]+)?'
    r'(abstract|introduction|background|related work|method(?:s|ology)?|'
    r'experimental setup|experiments|results|discussion|conclusion(?:s)?|'
    r'limitations|references|appendix)\b.*|\d+(?:\.\d+)*\.?\s+\S.{0,80})$',
    re.IGNORECASE)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, '', 'missing tool: ' + cmd[0]


def pages_pdftotext(pdf):
    rc, out, err = run(['pdftotext', '-layout', pdf, '-'])
    if rc != 0:
        return None
    pages = out.split('\f')
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def pages_pymupdf(pdf):
    try:
        import fitz
    except ImportError:
        return None
    doc = fitz.open(pdf)
    return [page.get_text() for page in doc]


def image_inventory(pdf):
    inv = {}
    rc, out, _ = run(['pdfimages', '-list', pdf])
    if rc == 0 and out:
        for line in out.splitlines()[2:]:
            cols = line.split()
            if len(cols) > 1 and cols[0].isdigit():
                inv.setdefault(int(cols[0]), 0)
                inv[int(cols[0])] += 1
        return inv
    try:
        import fitz
        doc = fitz.open(pdf)
        for i, page in enumerate(doc, start=1):
            n = len(page.get_images(full=True))
            if n:
                inv[i] = n
    except ImportError:
        pass
    return inv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--figures-dir')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    pages = pages_pdftotext(args.pdf)
    extractor = 'pdftotext -layout'
    if pages is None:
        pages = pages_pymupdf(args.pdf)
        extractor = 'pymupdf'
    if pages is None:
        sys.exit('no PDF text extractor available (need pdftotext or PyMuPDF)')
    empty_pages = [i + 1 for i, t in enumerate(pages) if len(t.strip()) < 20]
    ocr_note = None
    if len(empty_pages) > len(pages) // 2 and len(pages) > 0:
        ocr_note = ('text layer mostly empty on %d/%d pages — re-render and '
                    'OCR with the runtime ocr tool, then mark affected '
                    'anchors unverified' % (len(empty_pages), len(pages)))

    headings = {}
    for i, text in enumerate(pages, start=1):
        hits = []
        for line in text.splitlines():
            line = line.strip()
            if 3 < len(line) < 90 and HEADING_RE.match(line):
                hits.append(line)
        if hits:
            headings[i] = hits[:6]

    index = {
        'pdf': os.path.abspath(args.pdf),
        'pdf_sha256': sha256(args.pdf),
        'extractor': extractor,
        'page_count': len(pages),
        'pages': [{'page': i + 1, 'text': t} for i, t in enumerate(pages)],
        'empty_text_pages': empty_pages,
        'ocr_note': ocr_note,
        'headings_by_page': headings,
        'images_per_page': image_inventory(args.pdf),
        'figure_files': [],
    }
    if args.figures_dir and os.path.isdir(args.figures_dir):
        for name in sorted(os.listdir(args.figures_dir)):
            p = os.path.join(args.figures_dir, name)
            if os.path.isfile(p):
                index['figure_files'].append(
                    {'path': os.path.abspath(p), 'sha256': sha256(p)})

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print('pages: %d (extractor: %s); headings on %d pages; images on %s'
          % (len(pages), extractor, len(headings),
             sorted(index['images_per_page']) or 'none detected'))
    if ocr_note:
        print('NOTE:', ocr_note)
    print('index ->', args.out)


if __name__ == '__main__':
    main()
