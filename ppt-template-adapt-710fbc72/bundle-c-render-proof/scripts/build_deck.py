#!/usr/bin/env python3
"""Straightforward, deterministic deck builder for the render-proof pipeline.

Deliberately simple: it turns plan.json into a deck inside the real template
(title/body placeholders by idx, images aspect-fitted, notes attached,
body font size taken from the plan so the render-repair loop can step it
down deterministically). All visual quality is then enforced by
render_loop.py against the actual rendering, not by heuristics.

Plan schema:
{"slides": [{"layout": <name|index>, "title": "…",
             "bullets": ["…"], "body_pt": 18,
             "images": [{"path": "…", "caption": "…"}],
             "notes": "…"}]}

Usage:
    python build_deck.py --template T.pptx --plan plan.json --out deck.pptx \
        --report build_report.json
"""
import argparse
import json

from pptx import Presentation
from pptx.util import Emu, Pt


def layout_for(prs, key):
    layouts = list(prs.slide_layouts)
    if isinstance(key, int) or str(key).isdigit():
        i = int(key)
        if 0 <= i < len(layouts):
            return layouts[i]
    for lay in layouts:
        if lay.name.lower() == str(key).lower():
            return lay
    return layouts[min(1, len(layouts) - 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--template', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding='utf-8'))
    prs = Presentation(args.template)
    for sld in list(prs.slides._sldIdLst):
        prs.slides._sldIdLst.remove(sld)
    W, H = prs.slide_width, prs.slide_height
    report = {'slides': [], 'warnings': []}

    for n, spec in enumerate(plan['slides'], start=1):
        slide = prs.slides.add_slide(layout_for(prs, spec.get('layout', 1)))
        entry = {'slide': n, 'layout': slide.slide_layout.name}
        if spec.get('title') and slide.shapes.title is not None:
            slide.shapes.title.text = spec['title']
        body_pt = int(spec.get('body_pt', 18))
        if spec.get('bullets'):
            ph = None
            for cand in slide.placeholders:
                if cand.placeholder_format.idx != 0 and cand.has_text_frame:
                    ph = cand
                    break
            if ph is None:
                ph = slide.shapes.add_textbox(
                    Emu(int(W * 0.08)), Emu(int(H * 0.22)),
                    Emu(int(W * 0.84)), Emu(int(H * 0.62)))
                report['warnings'].append(
                    'slide %d: text-box substitution' % n)
            tf = ph.text_frame
            tf.word_wrap = True
            for i, item in enumerate(spec['bullets']):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                if isinstance(item, (list, tuple)):
                    p.text, p.level = str(item[0]), 1
                    p.font.size = Pt(max(12, body_pt - 2))
                else:
                    p.text = str(item)
                    p.font.size = Pt(body_pt)
            entry['body_pt'] = body_pt
        for im in spec.get('images', []):
            from pptx.parts.image import Image
            img = Image.from_file(im['path'])
            iw, ih = img.size
            dpi = img.dpi or (96, 96)
            nw, nh = iw / dpi[0] * 914400, ih / dpi[1] * 914400
            has_text = bool(spec.get('bullets'))
            box = (int(W * (0.58 if has_text else 0.12)), int(H * 0.24),
                   int(W * (0.36 if has_text else 0.76)), int(H * 0.56))
            s = min(box[2] / nw, box[3] / nh, 1.5)
            w, h = int(nw * s), int(nh * s)
            slide.shapes.add_picture(im['path'],
                                     int(box[0] + (box[2] - w) / 2),
                                     int(box[1] + (box[3] - h) / 2), w, h)
            if im.get('caption'):
                cap = slide.shapes.add_textbox(
                    Emu(int(W * 0.08)), Emu(int(H * 0.85)),
                    Emu(int(W * 0.84)), Emu(int(H * 0.08)))
                p = cap.text_frame.paragraphs[0]
                p.text = im['caption']
                p.font.size = Pt(12)
        if spec.get('notes'):
            slide.notes_slide.notes_text_frame.text = spec['notes']
        report['slides'].append(entry)

    prs.save(args.out)
    json.dump(report, open(args.report, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('deck -> %s (%d slides)' % (args.out, len(report['slides'])))


if __name__ == '__main__':
    main()
