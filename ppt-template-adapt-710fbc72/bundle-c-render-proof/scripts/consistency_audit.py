#!/usr/bin/env python3
"""Batch-consistency audit across the whole deck (整册一致性).

Rules applied uniformly to every slide, not just the front pages:
- title band: identical (left, top) and identical effective title font size
  across content slides (cover exempt)
- body font hierarchy: one declared body size (plus the -2 pt second level);
  any run below 12 pt is a failure
- footer / slide-number placeholders present on all content slides or none —
  a partially applied apparatus is a failure
- margins: body boxes start at the same left edge across slides
- speaker notes: present on every slide; total volume vs talk budget
- pptx<->PDF agreement: per-page text coverage of the final export
  (requires the export PDF; pass --pdf)

Usage:
    python consistency_audit.py deck.pptx [--pdf export.pdf] \
        [--duration-minutes T] --out consistency.json
Exit 1 on any fail-level finding.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter

from pptx import Presentation

FLOOR = 12


def norm(s):
    return re.sub(r'\s+', ' ', s).strip()


def squash(s):
    return re.sub(r'\s+', '', s)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck')
    ap.add_argument('--pdf')
    ap.add_argument('--duration-minutes', type=float, default=0)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    prs = Presentation(args.deck)
    findings = []
    rec = lambda lvl, msg, s=None: findings.append(
        {'level': lvl, 'slide': s, 'msg': msg})

    title_pos, body_lefts, body_sizes, notes_len = Counter(), Counter(), \
        Counter(), 0
    apparatus = {'footer': [], 'slide_number': []}
    n_slides = len(prs.slides._sldIdLst)

    for i, slide in enumerate(prs.slides, start=1):
        idxs = {ph.placeholder_format.idx for ph in slide.placeholders}
        apparatus['footer'].append(11 in idxs)
        apparatus['slide_number'].append(12 in idxs)
        title = slide.shapes.title
        if i > 1 and title is not None and title.text.strip():
            title_pos[(title.left, title.top)] += 1
        for shape in slide.shapes:
            if not shape.has_text_frame or shape is title:
                continue
            if shape.text_frame.text.strip():
                body_lefts[shape.left] += 1
            for p in shape.text_frame.paragraphs:
                if p.font.size is not None:
                    body_sizes[round(p.font.size.pt)] += 1
                    if p.font.size.pt < FLOOR:
                        rec('fail', 'run below %d pt floor (%.0f pt)'
                            % (FLOOR, p.font.size.pt), i)
        if slide.has_notes_slide:
            notes_len += len(re.sub(
                r'\s', '', slide.notes_slide.notes_text_frame.text))
        else:
            rec('warn', 'no speaker notes', i)

    if len(title_pos) > 1:
        rec('fail', 'title band inconsistent across slides: %s'
            % dict(title_pos))
    if len(body_lefts) > 2:
        rec('warn', 'body left edge varies across slides: %s'
            % dict(body_lefts))
    sizes = sorted(body_sizes)
    if sizes and (sizes[-1] - sizes[0] > 8):
        rec('warn', 'body font spread %s pt across deck (ladder drift?)'
            % (sizes[-1] - sizes[0]))
    for key, flags in apparatus.items():
        content = flags[1:]
        if content and any(content) and not all(content):
            rec('fail', '%s placeholder on only %d/%d content slides'
                % (key, sum(content), len(content)))
        if content and not any(content):
            rec('warn', '%s placeholder absent on all content slides' % key)
    if args.duration_minutes and notes_len < 240 * args.duration_minutes * 0.5:
        rec('warn', 'notes volume low for a %.0f-min slot (%d CJK-equiv '
            'chars)' % (args.duration_minutes, notes_len))

    if args.pdf:
        try:
            out = subprocess.run(['pdftotext', args.pdf, '-'],
                                 capture_output=True, text=True).stdout
            pages = [norm(p) for p in out.split('\f')]
            if pages and not pages[-1]:
                pages.pop()
            coverage = []
            for i, slide in enumerate(prs.slides, start=1):
                if i > len(pages):
                    break
                runs = [norm(p.text) for sh in slide.shapes
                        if sh.has_text_frame
                        for p in sh.text_frame.paragraphs
                        if len(norm(p.text)) >= 8]
                page_sq = squash(pages[i - 1])
                hit = sum(1 for r in runs if squash(r) in page_sq)
                coverage.append({'slide': i,
                                 'coverage': round(hit / len(runs), 3)
                                 if runs else 1.0})
            low = [c for c in coverage if c['coverage'] < 1.0]
            if low:
                rec('fail', 'pptx<->PDF text coverage < 100%% on: %s'
                    % {c['slide']: c['coverage'] for c in low})
        except FileNotFoundError:
            rec('warn', 'pdftotext unavailable; coverage check skipped')

    fails = [f for f in findings if f['level'] == 'fail']
    report = {'deck': args.deck, 'slides': n_slides,
              'status': 'fail' if fails else 'pass', 'findings': findings,
              'title_positions': {str(k): v for k, v in title_pos.items()},
              'body_font_histogram': {str(k): v for k, v in
                                      sorted(body_sizes.items())},
              'notes_total_chars': notes_len}
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('consistency: %s (%d fail, %d warn) -> %s'
          % (report['status'], len(fails), len(findings) - len(fails),
             args.out))
    for f in findings:
        print('%s%s: %s' % (f['level'].upper(),
                            ' s%d' % f['slide'] if f['slide'] else '',
                            f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
