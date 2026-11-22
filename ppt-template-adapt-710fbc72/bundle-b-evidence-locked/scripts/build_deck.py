#!/usr/bin/env python3
"""Evidence-gated deck builder.

Like any builder it renders plan.json into the template with python-pptx —
but every content slide MUST carry an `evidence` list whose entries were
verified by verify_anchors.py (status "verified"), or the build refuses
(--strict default). The builder writes evidence_map.json alongside the deck,
prints a source line on each slide (12 pt, bottom-left), and appends the
same source line to the speaker notes, so page-level traceability survives
both presentation and review.

Plan schema:
{
  "slides": [
    {"layout": "Title and Content", "title": "…",
     "bullets": ["…"], "notes": "…",
     "images": [{"path": "…", "caption": "Fig. 2: …"}],
     "evidence": [{"kind": "table", "ref": "Table 2", "pdf_page": 8,
                   "anchor": "…", "status": "verified"}]}
  ]
}

Usage:
    python build_deck.py --template T.pptx --plan plan.json \
        --out deck.pptx --evidence-map evidence_map.json \
        --report build_report.json [--no-strict]
"""
import argparse
import json
import sys

from pptx import Presentation
from pptx.util import Emu, Pt

MIN_PT = 12


def pick_layout(prs, name_or_idx, report, n):
    layouts = list(prs.slide_layouts)
    if isinstance(name_or_idx, int) or str(name_or_idx).isdigit():
        i = int(name_or_idx)
        if 0 <= i < len(layouts):
            return layouts[i]
    for layout in layouts:
        if layout.name.lower() == str(name_or_idx).lower():
            return layout
    report['warnings'].append(
        'slide %d: layout "%s" not found, using first layout' % (n, name_or_idx))
    return layouts[0]


def body_placeholder(slide):
    best = None
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:
            continue
        if not ph.has_text_frame:
            continue
        area = (ph.width or 0) * (ph.height or 0)
        if best is None or area > (best.width or 0) * (best.height or 0):
            best = ph
    return best


def fill_body(ph, bullets, report, n):
    tf = ph.text_frame
    tf.word_wrap = True
    flat = []

    def walk(items, level):
        for it in items:
            if isinstance(it, (list, tuple)):
                walk(it, level + 1)
            else:
                flat.append((str(it), level))
    walk(bullets, 0)
    for i, (text, level) in enumerate(flat):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.level = min(level, 4)
        p.font.size = Pt(max(MIN_PT, 18 - 2 * level))


def add_picture_fit(slide, path, slide_w, slide_h, has_text):
    from pptx.parts.image import Image
    img = Image.from_file(path)
    iw, ih = img.size
    dpi = img.dpi or (96, 96)
    nw0 = iw / dpi[0] * 914400
    nh0 = ih / dpi[1] * 914400
    if has_text:
        box = (int(slide_w * 0.58), int(slide_h * 0.24),
               int(slide_w * 0.36), int(slide_h * 0.58))
    else:
        box = (int(slide_w * 0.12), int(slide_h * 0.22),
               int(slide_w * 0.76), int(slide_h * 0.60))
    scale = min(box[2] / nw0, box[3] / nh0, 1.5)
    w, h = int(nw0 * scale), int(nh0 * scale)
    left = int(box[0] + (box[2] - w) / 2)
    top = int(box[1] + (box[3] - h) / 2)
    return slide.shapes.add_picture(path, left, top, w, h), iw / (w / 914400.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--template', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--evidence-map', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--no-strict', dest='strict', action='store_false')
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding='utf-8'))
    prs = Presentation(args.template)
    report = {'warnings': [], 'slides': []}
    evidence_map = []
    slide_w, slide_h = prs.slide_width, prs.slide_height

    # remove starter slides from a starting deck
    for sld in list(prs.slides._sldIdLst):
        prs.slides._sldIdLst.remove(sld)

    for n, spec in enumerate(plan['slides'], start=1):
        ev = spec.get('evidence') or []
        is_cover = n == 1 or 'title' in str(spec.get('layout', '')).lower()
        unverified = [e for e in ev if e.get('status') != 'verified']
        if not is_cover and not ev:
            msg = 'slide %d has NO evidence entries' % n
            if args.strict:
                sys.exit('GATE: ' + msg + ' — every content slide needs '
                         'verified evidence (see verify_anchors.py)')
            report['warnings'].append(msg)
        if unverified and args.strict:
            sys.exit('GATE: slide %d has unverified evidence: %s'
                     % (n, [e.get('ref') for e in unverified]))

        layout = pick_layout(prs, spec.get('layout', 1), report, n)
        slide = prs.slides.add_slide(layout)
        if spec.get('title'):
            try:
                slide.shapes.title.text = spec['title']
            except AttributeError:
                report['warnings'].append(
                    'slide %d: no title placeholder' % n)
        if spec.get('bullets'):
            ph = body_placeholder(slide)
            if ph is not None:
                fill_body(ph, spec['bullets'], report, n)
                if spec.get('images'):
                    ph.width = int((ph.width or slide_w) * 0.55)
            else:
                tb = slide.shapes.add_textbox(
                    Emu(int(slide_w * 0.08)), Emu(int(slide_h * 0.22)),
                    Emu(int(slide_w * 0.84)), Emu(int(slide_h * 0.6)))
                fill_body(tb, spec['bullets'], report, n)
                report['warnings'].append(
                    'slide %d: text-box substitution (no body placeholder)' % n)
        for im in spec.get('images', []):
            try:
                _, eff = add_picture_fit(slide, im['path'], slide_w, slide_h,
                                         bool(spec.get('bullets')))
                if eff < 96:
                    report['warnings'].append(
                        'slide %d: image %s eff dpi %.0f < 96'
                        % (n, im['path'], eff))
            except Exception as e:
                report['warnings'].append(
                    'slide %d: image %s failed: %s' % (n, im.get('path'), e))
            if im.get('caption'):
                cap = slide.shapes.add_textbox(
                    Emu(int(slide_w * 0.08)), Emu(int(slide_h * 0.84)),
                    Emu(int(slide_w * 0.84)), Emu(int(slide_h * 0.08)))
                p = cap.text_frame.paragraphs[0]
                p.text = im['caption']
                p.font.size = Pt(MIN_PT)
        # visible source line (traceability on the slide itself)
        src_bits = ['%s %s (p.%s)' % (e.get('kind', 'src'),
                                      e.get('ref', ''), e.get('pdf_page', '?'))
                    for e in ev]
        if src_bits:
            line = '来源: ' + '; '.join(src_bits)
            box = slide.shapes.add_textbox(
                Emu(int(slide_w * 0.03)), Emu(int(slide_h * 0.93)),
                Emu(int(slide_w * 0.7)), Emu(int(slide_h * 0.05)))
            p = box.text_frame.paragraphs[0]
            p.text = line
            p.font.size = Pt(MIN_PT)
        # notes = what to say + the same source line
        notes = spec.get('notes', '')
        if src_bits:
            notes = (notes + '\n[evidence] ' + '; '.join(src_bits)).strip()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

        evidence_map.append({
            'slide': n, 'title': spec.get('title', ''),
            'claim_summary': spec.get('claim', ''),
            'sources': [{k: e.get(k) for k in
                         ('kind', 'ref', 'pdf_page', 'anchor', 'status')}
                        for e in ev]})
        report['slides'].append({'slide': n, 'layout': layout.name,
                                 'evidence_entries': len(ev)})

    prs.save(args.out)
    json.dump(evidence_map, open(args.evidence_map, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(report, open(args.report, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('deck -> %s (%d slides, %d warnings); evidence map -> %s'
          % (args.out, len(report['slides']), len(report['warnings']),
             args.evidence_map))
    for w in report['warnings']:
        print('WARN:', w)


if __name__ == '__main__':
    main()
