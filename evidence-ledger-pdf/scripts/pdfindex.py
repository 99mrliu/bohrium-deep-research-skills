#!/usr/bin/env python3
"""PDF corpus indexing with page anchors.

Priority: pdftotext (poppler, page-broken by \f) > pure-python raw-bytes
fallback (best effort, flagged). Writes per-page text snapshots so later
steps never re-parse. Stdlib only.
"""
import hashlib
import os
import re
import shutil
import subprocess
import unicodedata

FORM_FEED = '\f'


def sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def norm(s: str) -> str:
    """Normalization used for quote matching: NFKC, fold whitespace,
    unify dashes/quotes, drop soft hyphens and hyphenation line breaks."""
    s = unicodedata.normalize('NFKC', s)
    s = s.replace('\u00ad', '').replace('-\n', '').replace('‐\n', '')
    s = s.replace('‐', '-').replace('‑', '-').replace('–', '-')
    s = s.replace('—', '-').replace('‘', "'").replace('’', "'")
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()


def find_quote(pages_text, quote):
    """Locate a verbatim quote across page texts.

    Returns (page_number_1based, char_start, char_end, snippet) or None.
    Matching is done on normalized text with position mapping back to raw.
    """
    nq = norm(quote)
    if len(nq) < 4:
        return None
    for pno, raw in enumerate(pages_text, 1):
        nraw = norm(raw)
        pos = nraw.find(nq)
        if pos >= 0:
            return (pno, pos, pos + len(nq),
                    raw[max(0, pos - 30):pos + len(quote) + 30])
    # sliding-window fallback: allow up to 2 char-level mismatches by
    # trying sub-phrases of the quote (first half / second half)
    half = len(nq) // 2
    for frag in (nq[:half], nq[-half:]):
        if len(frag) < 8:
            continue
        for pno, raw in enumerate(pages_text, 1):
            nraw = norm(raw)
            pos = nraw.find(frag)
            if pos >= 0:
                return (pno, pos, pos + len(frag),
                        '[partial] ' + raw[max(0, pos - 30):
                                           pos + len(frag) + 30])
    return None


def _parse_with_pdftotext(path):
    out = subprocess.run(['pdftotext', '-layout', path, '-'],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout.split(FORM_FEED)


def _parse_fallback(path):
    """Raw-bytes fallback: extract text-ish runs. Flagged as degraded."""
    with open(path, 'rb') as f:
        data = f.read()
    runs = re.findall(rb'\((?:[^()\\]|\\.)*\)', data)
    chunks = []
    for r in runs[:40000]:
        inner = r[1:-1].replace(b'\\(', b'(').replace(b'\\)', b')')
        try:
            t = inner.decode('utf-8')
        except UnicodeDecodeError:
            try:
                t = inner.decode('latin-1')
            except Exception:
                continue
        t = t.strip()
        if t:
            chunks.append(t)
    if not chunks:
        return None
    return [' '.join(chunks)]  # single pseudo-page, degraded


def build_index(input_dir, corpus_dir):
    tool = 'pdftotext' if shutil.which('pdftotext') else 'raw-fallback(degraded)'
    documents, parse_errors = [], []
    for root, _dirs, files in os.walk(input_dir):
        for name in sorted(files):
            if not name.lower().endswith('.pdf'):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, input_dir)
            with open(path, 'rb') as f:
                digest = sha16(f.read())
            try:
                pages_text = (_parse_with_pdftotext(path)
                              if tool == 'pdftotext' else None)
                if pages_text is None:
                    pages_text = _parse_fallback(path)
                if not pages_text:
                    raise ValueError('empty extraction')
            except Exception as e:  # noqa: BLE001 - report, don't crash
                parse_errors.append({'path': rel, 'sha256': digest,
                                     'error': str(e)})
                continue
            doc_id = 'DOC-%d' % (len(documents) + 1)
            pages = []
            offset = 0
            safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', rel)
            for pno, text in enumerate(pages_text, 1):
                start = offset
                offset += len(text)
                snap = os.path.join(corpus_dir,
                                    '%s.p%04d.txt' % (safe, pno))
                with open(snap, 'w', encoding='utf-8') as f:
                    f.write(text)
                pages.append({'page': pno, 'char_start': start,
                              'char_end': offset, 'snapshot': snap,
                              'chars': len(text)})
            documents.append({'doc_id': doc_id, 'path': rel,
                              'sha256': digest, 'pages': pages})
    return ({'documents': documents,
             'normalization': 'NFKC+fold-whitespace+unify-dash/quote+'
                              'dehyphenation (see pdfindex.norm)'},
            parse_errors, tool)


def load_pages(doc, pages=None):
    """Return list of raw page texts for a document from snapshots."""
    out = []
    for p in doc['pages']:
        if pages and p['page'] not in pages:
            continue
        with open(p['snapshot'], encoding='utf-8') as f:
            out.append(f.read())
    return out
