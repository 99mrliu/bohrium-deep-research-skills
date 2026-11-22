#!/usr/bin/env python3
"""Build a deck *inside* a real template from a page plan (JSON).

Opens the template (or starting deck) itself with python-pptx so that
master/layout/placeholder inheritance genuinely happens; fills placeholders
by idx/type, never by guessed coordinates; fits images with aspect ratio
preserved; enforces an explainable font-size ladder (shrink only down to the
floor, then flags for a page split); instantiates footer / slide-number
placeholders on every content slide for batch consistency; writes speaker
notes; and records every decision in a build report.

Usage:
    python build_deck.py --template T.pptx --plan plan.json \
        --out deck.pptx --report build_report.json [--keep-existing]

Plan schema (UTF-8 JSON):
{
  "slides": [
    {"layout": "Title and Content",          # layout name or global index
     "title": "…",                            # optional per slide type
     "bullets": ["…", ["nested", "…"]],       # strings or nested lists
     "body": "paragraph text",                # alternative to bullets
     "images": [{"path": "fig1.png", "caption": "Fig. 1: …",
                  "source": "paper p.7 Fig. 3"}],
     "notes": "speaker notes …",
     "footer": "…",                           # optional footer text
     "table": {"rows": [["h1","h2"], …]}}     # optional native table
  ]
}
"""
import argparse
import copy
import json
import sys

from pptx import Presentation
from pptx.util import Emu, Pt

FONT_FLOOR_PT = 12
BODY_LADDER = [18, 16, 14, 12]
TITLE_MAX_CHARS_PER_LINE = 40


def load_layouts(prs):
    by_name, by_idx = {}, {}
    for i, layout in enumerate(prs.slide_layouts):
        by_idx[i] = layout
        by_name.setdefault(layout.name.lower(), layout)
    return by_name, by_idx


def resolve_layout(prs, spec, report, slide_no):
    by_name, by_idx = load_layouts(prs)
    if isinstance(spec, int) or (isinstance(spec, str) and spec.isdigit()):
        i = int(spec)
        if i in by_idx:
            return by_idx[i], 'index %d' % i
    if isinstance(spec, str) and spec.lower() in by_name:
        return by_name[spec.lower()], 'name "%s"' % spec
    # fallback: first layout that has a body/object placeholder
    for i, layout in by_idx.items():
        for ph in layout.placeholders:
            if ph.placeholder_format.idx not in (0,) and \
               ph.placeholder_format.type in (2, 7):  # BODY / OBJECT
                report.setdefault('warnings', []).append(
                    'slide %d: layout "%s" not found; fell back to "%s"'
                    % (slide_no, spec, layout.name))
                return layout, 'fallback "%s"' % layout.name
    return prs.slide_layouts[0], 'fallback first layout'


def get_ph(slide, idx=None, types=None):
    best = None
    for ph in slide.placeholders:
        f = ph.placeholder_format
        if idx is not None and f.idx == idx:
            return ph
        if types is not None and f.type in types:
            area = (ph.width or 0) * (ph.height or 0)
            if best is None or area > (best.width or 0) * (best.height or 0):
                best = ph
    return best


def eff_geo(shape):
    """Effective (left, top, width, height) EMU, inheriting from the layout
    placeholder of the same idx when the slide placeholder carries no xfrm.
    Never write a partial xfrm: setting only left/width zeroes the rest."""
    vals = [shape.left, shape.top, shape.width, shape.height]
    if all(v is not None for v in vals):
        return vals
    try:
        for lph in shape.slide_layout.placeholders:
            if lph.placeholder_format.idx == shape.placeholder_format.idx:
                inh = [lph.left, lph.top, lph.width, lph.height]
                vals = [v if v is not None else inh[i]
                        for i, v in enumerate(vals)]
                break
    except Exception:
        pass
    return [v if v is not None else 0 for v in vals]


def set_geo(shape, left=None, top=None, width=None, height=None):
    l, t, w, h = eff_geo(shape)
    shape.left, shape.top = left if left is not None else l, \
        top if top is not None else t
    shape.width, shape.height = width if width is not None else w, \
        height if height is not None else h


def est_lines(text, width_emu, size_pt):
    """Rough line estimate: average glyph width ~0.52 em for latin, 1.0 for CJK."""
    if width_emu is None or width_emu <= 0:
        return 1
    width_pt = width_emu / 12700.0
    lines = 0
    for para in str(text).split('\n'):
        w = sum(1.0 if ord(c) > 0x2E7F else 0.52 for c in para) * size_pt
        lines += max(1, -(-int(w) // max(1, int(width_pt))))
    return lines


def fit_body(tf, items, width_emu, height_emu, report, slide_no):
    """Fill a text frame with bullets; choose the largest ladder size that fits."""
    flat = []

    def walk(seq, level):
        for it in seq:
            if isinstance(it, (list, tuple)):
                walk(it, level + 1)
            else:
                flat.append((str(it), level))
    walk(items, 0)
    chosen = BODY_LADDER[-1]
    for size in BODY_LADDER:
        total = sum(est_lines(t, width_emu, size) * 1.3 for _, t in flat)
        if height_emu is None or total * size * 12700 <= height_emu:
            chosen = size
            break
    else:
        report.setdefault('warnings', []).append(
            'slide %d: body text still overflows at %d pt floor — split the '
            'page instead of shrinking further' % (slide_no, FONT_FLOOR_PT))
        report.setdefault('overflow_pages', []).append(slide_no)
    tf.word_wrap = True
    for i, (text, level) in enumerate(flat):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.level = min(level, 4)
        p.font.size = Pt(max(FONT_FLOOR_PT, chosen - 2 * level))
    return chosen


def add_image_fit(slide, path, box, report, slide_no):
    """Insert image inside box (left,top,width,height EMU) keeping aspect."""
    from pptx.util import Emu as _E  # noqa
    from pptx.parts.image import Image
    try:
        img = Image.from_file(path)
    except Exception as e:
        report.setdefault('warnings', []).append(
            'slide %d: image %s unreadable (%s)' % (slide_no, path, e))
        return None
    iw, ih = img.size  # px
    dpi = img.dpi or (96, 96)
    native_w = int(iw / dpi[0] * 914400)
    native_h = int(ih / dpi[1] * 914400)
    l, t, w, h = box
    scale = min(w / native_w, h / native_h, 1.5)
    nw, nh = int(native_w * scale), int(native_h * scale)
    nl = int(l + (w - nw) / 2)
    nt = int(t + (h - nh) / 2)
    pic = slide.shapes.add_picture(path, nl, nt, nw, nh)
    eff_dpi = round(iw / (nw / 914400.0))
    report['images'].append({'slide': slide_no, 'path': path,
                             'eff_dpi': eff_dpi, 'aspect_preserved': True})
    if eff_dpi < 96:
        report.setdefault('warnings', []).append(
            'slide %d: image %s effective dpi %d < 96 — re-render at higher '
            'resolution' % (slide_no, path, eff_dpi))
    return pic


def clone_layout_ph(slide, layout, idx):
    """Instantiate a placeholder (e.g. footer/slide number) that the layout
    defines but the slide lacks, by cloning the layout's sp XML (real
    placeholder inheritance, not a floating text box)."""
    for lph in layout.placeholders:
        if lph.placeholder_format.idx == idx:
            sp = copy.deepcopy(lph._element)
            # strip any text content carried over from the layout
            ns = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
            for t in sp.iter(ns + 't'):
                t.text = ''
            slide.shapes._spTree.append(sp)
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--template', required=True,
                    help='template .pptx or starting deck')
    ap.add_argument('--plan', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--keep-existing', action='store_true',
                    help='keep slides already in the starting deck')
    args = ap.parse_args()

    prs = Presentation(args.template)
    report = {'template': args.template, 'slides': [], 'images': [],
              'warnings': [], 'placeholders_cloned': [],
              'existing_slides_removed': 0}

    if not args.keep_existing:
        xml_slides = prs.slides._sldIdLst
        for sld in list(xml_slides):
            xml_slides.remove(sld)
            report['existing_slides_removed'] += 1

    with open(args.plan, encoding='utf-8') as f:
        plan = json.load(f)
    slide_w, slide_h = prs.slide_width, prs.slide_height

    for n, spec in enumerate(plan['slides'], start=1):
        layout, how = resolve_layout(prs, spec.get('layout', ''), report, n)
        slide = prs.slides.add_slide(layout)
        entry = {'slide': n, 'layout': layout.name, 'layout_resolved_by': how}
        # title
        title = spec.get('title')
        tph = get_ph(slide, idx=0)
        if title is not None and tph is not None:
            tph.text = title
            if len(title) > TITLE_MAX_CHARS_PER_LINE and \
               est_lines(title, eff_geo(tph)[2], 24) > 2:
                report['warnings'].append(
                    'slide %d: title wraps past two lines — shorten it' % n)
        elif title is not None:
            report['warnings'].append(
                'slide %d: layout "%s" has no title placeholder; title '
                'dropped or must be a text box' % (n, layout.name))
        # body
        body_ph = get_ph(slide, types=(2, 7))  # BODY / OBJECT
        items = spec.get('bullets') or ([spec['body']] if spec.get('body')
                                        else None)
        if items and body_ph is not None and not spec.get('images'):
            l, t, w, h = eff_geo(body_ph)
            size = fit_body(body_ph.text_frame, items, w, h, report, n)
            entry['body_font_pt'] = size
        elif items and body_ph is not None:
            # image + text: shrink text box to left 55% of body area
            l, t, w, h = eff_geo(body_ph)
            set_geo(body_ph, width=int(w * 0.55))
            size = fit_body(body_ph.text_frame, items,
                            int(w * 0.55), h, report, n)
            entry['body_font_pt'] = size
        elif items:
            tb = slide.shapes.add_textbox(Emu(int(slide_w * 0.08)),
                                          Emu(int(slide_h * 0.22)),
                                          Emu(int(slide_w * 0.84)),
                                          Emu(int(slide_h * 0.66)))
            size = fit_body(tb.text_frame, items, tb.width, tb.height,
                            report, n)
            entry['body_font_pt'] = size
            report['warnings'].append(
                'slide %d: no body placeholder in layout; added aligned '
                'text box (substitution recorded)' % n)
        # images
        for im in spec.get('images', []):
            pic_ph = get_ph(slide, types=(18,))  # PICTURE
            if pic_ph is not None:
                pl, pt, pw, ph_ = eff_geo(pic_ph)
                box = (pl, pt, pw or int(slide_w * 0.5),
                       ph_ or int(slide_h * 0.5))
                pic = add_image_fit(slide, im['path'], box, report, n)
                if pic is not None:
                    pic_ph._element.getparent().remove(pic_ph._element)
            else:
                l = int(slide_w * 0.60) if items else int(slide_w * 0.15)
                w = int(slide_w * 0.34) if items else int(slide_w * 0.70)
                box = (l, int(slide_h * 0.25), w, int(slide_h * 0.55))
                add_image_fit(slide, im['path'], box, report, n)
            if im.get('caption'):
                cap = slide.shapes.add_textbox(
                    Emu(int(slide_w * 0.08)), Emu(int(slide_h * 0.86)),
                    Emu(int(slide_w * 0.84)), Emu(int(slide_h * 0.08)))
                p = cap.text_frame.paragraphs[0]
                p.text = im['caption'] + (
                    '（%s）' % im['source'] if im.get('source') else '')
                p.font.size = Pt(12)
        # native table
        if spec.get('table'):
            rows = spec['table']['rows']
            nr, nc = len(rows), max(len(r) for r in rows)
            gt = slide.shapes.add_table(
                nr, nc, Emu(int(slide_w * 0.08)), Emu(int(slide_h * 0.25)),
                Emu(int(slide_w * 0.84)),
                Emu(int(min(slide_h * 0.6, 400000 * nr)))).table
            for r in range(nr):
                for c in range(nc):
                    cell = gt.cell(r, c)
                    cell.text = str(rows[r][c]) if c < len(rows[r]) else ''
                    for p in cell.text_frame.paragraphs:
                        p.font.size = Pt(12)
            entry['table'] = '%dx%d' % (nr, nc)
        # notes
        if spec.get('notes'):
            slide.notes_slide.notes_text_frame.text = spec['notes']
            entry['notes_chars'] = len(spec['notes'])
        # batch consistency: footer + slide number on every content slide
        for idx, key in ((11, 'footer'), (12, 'slide_number')):
            if get_ph(slide, idx=idx) is None:
                if clone_layout_ph(slide, layout, idx):
                    report['placeholders_cloned'].append(
                        {'slide': n, 'idx': idx, 'kind': key})
        fph = get_ph(slide, idx=11)
        if fph is not None and spec.get('footer'):
            fph.text = spec['footer']
        report['slides'].append(entry)

    prs.save(args.out)
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('deck ->', args.out, '(%d slides, %d warnings)' % (
        len(report['slides']), len(report['warnings'])))
    for w in report['warnings']:
        print('WARN:', w)


if __name__ == '__main__':
    main()
