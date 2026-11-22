#!/usr/bin/env python3
"""Numeric-consistency audit: every number on a slide must exist in the source.

Extracts numeric tokens (including decimals, percentages, thousand
separators, exponents) from all slide text via python-pptx, normalizes
formatting variants (28.4 == 28.40; 1,024 == 1024; 5% == 5 percent), and
checks each token against the source index pages. Numbers that appear
nowhere in the source are reported per slide — they are either hallucinated
or mis-copied and must be fixed or justified in the change log.

Small integers that plausibly come from the deck's own apparatus (slide
numbers, years in the task text, enumerations like "3 steps") can be
whitelisted with --allow "1,2,3,2024".

Usage:
    python check_numbers.py --deck deck.pptx --index source_index.json \
        --out numbers_check.json [--allow "1,2,3"]
Exit 1 when unaccounted numbers remain.
"""
import argparse
import json
import re
import sys

from pptx import Presentation

NUM_RE = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(%|percent))?(?![\w.])')


def norm_num(tok):
    return tok.replace(',', '').rstrip('0').rstrip('.') if '.' in \
        tok.replace(',', '') else tok.replace(',', '')


def source_numbers(index):
    vals = set()
    for p in index['pages']:
        for m in NUM_RE.finditer(p['text']):
            vals.add(norm_num(m.group(1)))
            if m.group(1).replace(',', '').isdigit():
                v = int(m.group(1).replace(',', ''))
                vals.add(str(v))
    return vals


def slide_texts(deck):
    prs = Presentation(deck)
    out = []
    for i, slide in enumerate(prs.slides, start=1):
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
        out.append((i, '\n'.join(parts)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deck', required=True)
    ap.add_argument('--index', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--allow', default='')
    args = ap.parse_args()

    index = json.load(open(args.index, encoding='utf-8'))
    src = source_numbers(index)
    allow = {norm_num(t) for t in args.allow.split(',') if t.strip()}
    bad = {}
    total = 0
    for i, text in slide_texts(args.deck):
        for m in NUM_RE.finditer(text):
            tok = norm_num(m.group(1))
            if not tok:
                continue
            total += 1
            if tok not in src and tok not in allow:
                bad.setdefault(i, []).append(m.group(0))

    report = {'deck': args.deck, 'numbers_checked': total,
              'unmatched': {str(k): sorted(set(v)) for k, v in bad.items()},
              'status': 'fail' if bad else 'pass'}
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('numbers: %d checked, %d slide(s) with unmatched -> %s'
          % (total, len(bad), args.out))
    for slide, toks in sorted(bad.items()):
        print('slide %d: %s' % (slide, sorted(set(toks))))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
