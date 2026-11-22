#!/usr/bin/env python3
"""Evidence gate: verify every claim's anchor quote against the source index.

Input claims.json (written by the agent while reading the paper):

[
  {"id": "c1", "claim": "The big Transformer reaches 28.4 BLEU on WMT EN-DE",
   "kind": "table", "ref": "Table 2", "pdf_page": 8,
   "anchor": "big Transformer model ... 28.4"},
  ...
]

An anchor verifies when, after normalization (lowercase, whitespace collapse,
punctuation stripped), it is a substring of the cited page's text, OR — with
--fuzzy — its content-word overlap with the best-matching page window is at
least 0.8 and the page matches. Cross-page fallback: if the anchor matches a
*different* page, the claim is marked `page_mismatch` (fix the page, the
evidence itself exists). Unverified claims never enter the deck.

Usage:
    python verify_anchors.py --index source_index.json --claims claims.json \
        --out claims.verified.json [--fuzzy]
Exit 1 when any claim is unverified (the gate).
"""
import argparse
import json
import re
import sys

STOP = set('the a an of to in on for and or is are was were be been by with '
           'as at from that this it its we our et al'.split())


def norm(s):
    s = s.lower()
    s = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def tokens(s):
    return [t for t in norm(s).split() if t not in STOP]


def overlap(anchor_toks, page_text):
    ptok = tokens(page_text)
    if not anchor_toks or not ptok:
        return 0.0
    pset = set(ptok)
    return sum(1 for t in anchor_toks if t in pset) / len(anchor_toks)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index', required=True)
    ap.add_argument('--claims', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--fuzzy', action='store_true',
                    help='allow token-overlap >= 0.8 when exact substring fails')
    args = ap.parse_args()

    index = json.load(open(args.index, encoding='utf-8'))
    pages = {p['page']: p['text'] for p in index['pages']}
    claims = json.load(open(args.claims, encoding='utf-8'))
    n_ok = n_bad = 0

    for c in claims:
        anchor = c.get('anchor', '')
        page = c.get('pdf_page')
        status, detail = 'unverified', ''
        if not anchor.strip():
            detail = 'empty anchor'
        elif page not in pages:
            detail = 'pdf_page %r out of range' % page
        else:
            na, np_ = norm(anchor), norm(pages[page])
            if na and na in np_:
                status, detail = 'verified', 'exact substring on page %d' % page
            elif args.fuzzy and overlap(tokens(anchor), pages[page]) >= 0.8:
                status = 'verified'
                detail = 'fuzzy overlap %.2f on page %d' % (
                    overlap(tokens(anchor), pages[page]), page)
            else:
                # cross-page fallback: evidence may exist on another page
                for pn, text in pages.items():
                    if na and na in norm(text):
                        status = 'page_mismatch'
                        detail = 'anchor found on page %d, not %d' % (pn, page)
                        break
                else:
                    detail = 'anchor not found anywhere in source'
        c['status'] = status
        c['verification'] = detail
        if status == 'verified':
            n_ok += 1
        else:
            n_bad += 1

    json.dump({'index': args.index, 'claims': claims},
              open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('verified: %d/%d -> %s' % (n_ok, len(claims), args.out))
    for c in claims:
        if c['status'] != 'verified':
            print('%s: %s (%s)' % (c['status'].upper(), c.get('id'),
                                   c['verification']))
    sys.exit(1 if n_bad else 0)


if __name__ == '__main__':
    main()
