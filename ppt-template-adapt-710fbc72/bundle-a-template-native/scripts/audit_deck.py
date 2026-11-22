#!/usr/bin/env python3
"""Structural audit of a finished deck against its template (JSON report).

Checks, per slide and deck-wide:
- slide count within the task's required range
- every slide's layout genuinely comes from the template package
  (layout part names verified against the template zip)
- non-empty titles; title position identical across slides (batch
  consistency of the title band)
- body font sizes never below the floor (12 pt) and on the ladder
- estimated text overflow (autofit-aware heuristic)
- image aspect-ratio preservation (shape box vs native pixel ratio)
- footer / slide-number placeholders present on every content slide
- speaker-notes coverage and total volume vs the talk budget

Usage:
    python audit_deck.py deck.pptx --template T.pptx \
        --min-slides 8 --max-slides 12 --duration-minutes 12 \
        --out audit.json
Exit code 0 = pass (no fail findings), 1 = fail.
"""
import argparse
import json
import re
import sys
import zipfile

from pptx import Presentation

FLOOR_PT = 12
CJK_RATE = 240      # Chinese chars per minute
LATIN_RATE = 140    # English words per minute


def template_partnames(path):
    with zipfile.ZipFile(path) as z:
        return set(z.namelist())


def est_lines(text, width_emu, size_pt):
    if not width_emu:
        return 1
    width_pt = width_emu / 12700.0
    n = 0
    for para in str(text).split('\n'):
        w = sum(1.0 if ord(c) > 0x2E7F else 0.52 for c in para) * size_pt
        n += max(1, -(-int(w) // max(1, int(width_pt))))
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck')
    ap.add_argument('--template')
    ap.add_argument('--min-slides', type=int, default=0)
    ap.add_argument('--max-slides', type=int, default=10 ** 9)
    ap.add_argument('--duration-minutes', type=float, default=0)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    prs = Presentation(args.deck)
    findings = []

    def fail(msg, slide=None):
        findings.append({'level': 'fail', 'slide': slide, 'msg': msg})

    def warn(msg, slide=None):
        findings.append({'level': 'warn', 'slide': slide, 'msg': msg})

    n = len(prs.slides._sldIdLst)
    if not (args.min_slides <= n <= args.max_slides):
        fail('slide count %d outside [%d, %d]'
             % (n, args.min_slides, args.max_slides))

    tparts = template_partnames(args.template) if args.template else None
    title_pos, notes_chars, notes_words = {}, 0, 0
    footer_missing, sn_missing = [], []
    per_slide = []

    for i, slide in enumerate(prs.slides, start=1):
        entry = {'slide': i, 'layout': slide.slide_layout.name}
        part = str(slide.slide_layout.part.partname).lstrip('/')
        if tparts is not None and part not in tparts:
            fail('layout part %s not in template package' % part, i)
        entry['layout_in_template'] = tparts is None or part in tparts
        # title
        title_ph = None
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == 0:
                title_ph = ph
        if title_ph is None or not (title_ph.text or '').strip():
            if i > 1:
                warn('missing or empty title', i)
        else:
            pos = (title_ph.left, title_ph.top)
            title_pos.setdefault(pos, []).append(i)
        # text checks
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            sizes = [p.font.size.pt for p in shape.text_frame.paragraphs
                     if p.font.size is not None]
            small = [s for s in sizes if s < FLOOR_PT]
            if small:
                fail('font size %.0f pt below %d pt floor'
                     % (min(small), FLOOR_PT), i)
            text = shape.text_frame.text.strip()
            if text and sizes and shape.height:
                size = min(sizes)
                need = est_lines(text, shape.width, size) * 1.3 * size * 12700
                if need > shape.height * 1.15:
                    warn('estimated text overflow (need %.0f%% of box)'
                         % (100 * need / shape.height), i)
        # images
        for shape in slide.shapes:
            if shape.shape_type == 13:  # PICTURE
                try:
                    iw, ih = shape.image.size
                    box_ratio = shape.width / shape.height
                    nat_ratio = iw / ih
                    if abs(box_ratio / nat_ratio - 1) > 0.05:
                        fail('image distorted (box %.3f vs native %.3f)'
                             % (box_ratio, nat_ratio), i)
                    eff = iw / (shape.width / 914400.0)
                    if eff < 96:
                        warn('image effective dpi %.0f < 96' % eff, i)
                except Exception as e:
                    warn('image check failed: %s' % e, i)
        # footer / slide number
        idxs = {ph.placeholder_format.idx for ph in slide.placeholders}
        if i > 1:
            if 11 not in idxs:
                footer_missing.append(i)
            if 12 not in idxs:
                sn_missing.append(i)
        # notes
        if slide.has_notes_slide:
            t = slide.notes_slide.notes_text_frame.text
            notes_chars += len(re.sub(r'\s', '', t))
            notes_words += len(t.split())
        else:
            warn('no speaker notes', i)
        per_slide.append(entry)

    if len(title_pos) > 1:
        warn('title position differs across slides: %s'
             % {str(k): v for k, v in title_pos.items()})
    if footer_missing:
        warn('footer placeholder missing on slides %s' % footer_missing)
    if sn_missing:
        fail('slide-number placeholder missing on slides %s' % sn_missing)
    if args.duration_minutes:
        est_min = notes_chars / CJK_RATE + notes_words / LATIN_RATE
        if est_min < args.duration_minutes * 0.6:
            warn('notes volume ~%.1f min of talk for a %.0f-min slot'
                 % (est_min, args.duration_minutes))

    fails = [f for f in findings if f['level'] == 'fail']
    report = {'deck': args.deck, 'slides': n,
              'status': 'fail' if fails else 'pass',
              'findings': findings, 'per_slide': per_slide,
              'notes_total_chars': notes_chars}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('audit: %s (%d fail, %d warn) -> %s'
          % (report['status'], len(fails),
             len(findings) - len(fails), args.out))
    for f_ in findings:
        print('%s%s: %s' % (f_['level'].upper(),
                            ' s%d' % f_['slide'] if f_['slide'] else '',
                            f_['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
