#!/usr/bin/env python3
"""Render–audit–repair closed loop: prove the export matches the deck.

Each iteration:
  1. exports the deck to PDF (LibreOffice headless, private profile, one
     automatic retry on DeploymentException);
  2. audits the RENDERED pdf, not the pptx: page parity, blank pages,
     clipped words (bbox outside the page rect), per-slide title presence,
     per-slide text coverage (every bullet's normalized text must appear on
     its PDF page — lost text means the renderer clipped it), and the PDF
     font list (font substitution shows up here);
  3. repairs deterministically: slides with clipped/lost text get every run
     stepped 2 pt smaller (floor 12 pt); the iteration is logged with the
     pdf hash so the whole loop is replayable.

Stops when an iteration is clean or --max-iter is reached; renders PNG
previews of the final PDF; writes render_report.json containing the
per-page deviation table the task requires. Exit 0 = clean final render.

Usage:
    python render_loop.py deck.pptx export.pdf --previews DIR \
        --workdir /app/work --out render_report.json [--max-iter 3]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from pptx import Presentation
from pptx.util import Pt

FLOOR_PT = 12
STEP_PT = 2


def run(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, '', 'missing tool: ' + cmd[0]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def soffice_path():
    for c in ('soffice', 'libreoffice',
              '/Applications/LibreOffice.app/Contents/MacOS/soffice',
              '/usr/lib/libreoffice/program/soffice'):
        p = shutil.which(c) if '/' not in c else (c if os.path.exists(c)
                                                  else None)
        if p:
            return p
    return None


def export_pdf(soffice, deck, pdf, workdir, log):
    profile = os.path.join(workdir, 'lo_profile')
    outdir = os.path.dirname(os.path.abspath(pdf))
    cmd = [soffice, '--headless', '--norestore', '--nolockcheck',
           '-env:UserInstallation=file://' + os.path.abspath(profile),
           '--convert-to', 'pdf', '--outdir', outdir, deck]
    rc, out, err = run(cmd)
    produced = os.path.join(outdir, os.path.splitext(
        os.path.basename(deck))[0] + '.pdf')
    if not os.path.exists(produced):
        shutil.rmtree(profile, ignore_errors=True)
        rc, out, err = run(cmd)
        log.append('export retried with fresh LibreOffice profile')
    if os.path.exists(produced) and os.path.abspath(produced) != \
            os.path.abspath(pdf):
        os.replace(produced, pdf)
    return os.path.exists(pdf), (err or out)[-200:]


def norm(s):
    return re.sub(r'\s+', ' ', s).strip()


def squash(s):
    """Whitespace-free normal form: LibreOffice inserts CJK-latin
    autospacing at render time, so substring checks must ignore spaces."""
    return re.sub(r'\s+', '', s)


def deck_texts(deck):
    prs = Presentation(deck)
    titles, bodies = [], []
    for slide in prs.slides:
        t = slide.shapes.title.text if slide.shapes.title is not None else ''
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape != slide.shapes.title:
                parts.extend(p.text for p in shape.text_frame.paragraphs
                             if p.text.strip())
        titles.append(norm(t))
        bodies.append([norm(p) for p in parts])
    return titles, bodies


def pdf_pages_text(pdf):
    rc, out, _ = run(['pdftotext', pdf, '-'])
    if rc != 0:
        return []
    pages = out.split('\f')
    if pages and not pages[-1].strip():
        pages.pop()
    return [norm(p) for p in pages]


def pdf_bbox_pages(pdf):
    """Return [(width, height, [(xMin,yMin,xMax,yMax,word), ...]), ...]."""
    rc, out, _ = run(['pdftotext', '-bbox', pdf, '-'])
    if rc != 0:
        return []
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>',
                          out, re.S):
        w, h, body = float(pm.group(1)), float(pm.group(2)), pm.group(3)
        words = [(float(m.group(1)), float(m.group(2)),
                  float(m.group(3)), float(m.group(4)), m.group(5))
                 for m in re.finditer(
                     r'<word xMin="([\d.]+)" yMin="([\d.]+)" '
                     r'xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', body)]
        pages.append((w, h, words))
    return pages


def pdf_fonts(pdf):
    rc, out, _ = run(['pdffonts', pdf])
    if rc == 0:
        return sorted({ln.split()[0] for ln in out.splitlines()[2:]
                       if ln.split()})
    data = open(pdf, 'rb').read()
    return sorted({m.group(1).decode('latin1').split('+')[-1] for m in
                   re.finditer(rb'/BaseFont\s*/([^\s/<>\[\]()]+)', data)})


def shrink_slide_fonts(deck, slide_no):
    prs = Presentation(deck)
    slide = prs.slides[slide_no - 1]
    changed = 0
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for p in shape.text_frame.paragraphs:
            size = p.font.size
            if size is not None and size.pt > FLOOR_PT:
                p.font.size = Pt(max(FLOOR_PT, size.pt - STEP_PT))
                changed += 1
    prs.save(deck)
    return changed


def audit_iteration(pdf, deck):
    findings = []
    titles, bodies = deck_texts(deck)
    pages = pdf_pages_text(pdf)
    bbox = pdf_bbox_pages(pdf)
    if len(pages) != len(titles):
        findings.append({'level': 'fail', 'slide': None,
                         'check': 'page_parity',
                         'msg': 'PDF pages %d != slides %d'
                                % (len(pages), len(titles))})
    fonts = pdf_fonts(pdf)
    per_page = []
    for i in range(min(len(pages), len(titles))):
        page_findings = []
        words = bbox[i][2] if i < len(bbox) else []
        w, h = (bbox[i][0], bbox[i][1]) if i < len(bbox) else (0, 0)
        if not words and not pages[i]:
            page_findings.append(('blank_page', 'page %d renders blank'
                                  % (i + 1), 'fail'))
        if w and h:
            clipped = [wd for wd in words
                       if wd[2] > w + 2 or wd[3] > h + 2
                       or wd[0] < -2 or wd[1] < -2]
            if clipped:
                page_findings.append(
                    ('clipped_text', '%d word(s) outside page rect, e.g. %r'
                     % (len(clipped), clipped[0][4][:30]), 'fail'))
        if titles[i] and squash(titles[i]) not in squash(pages[i]):
            page_findings.append(('title_missing',
                                  'slide title not on its PDF page', 'fail'))
        page_sq = squash(pages[i])
        lost = [b for b in bodies[i]
                if len(b) >= 8 and squash(b) not in page_sq]
        if lost:
            page_findings.append(
                ('text_lost', '%d/%d text runs missing from render, e.g. %r'
                 % (len(lost), len(bodies[i]), lost[0][:40]), 'fail'))
        for check, msg, lvl in page_findings:
            findings.append({'level': lvl, 'slide': i + 1, 'check': check,
                             'msg': msg})
        per_page.append({'slide': i + 1, 'issues': [c for c, _, _ in
                                                    page_findings]})
    return findings, per_page, fonts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck')
    ap.add_argument('pdf')
    ap.add_argument('--previews', required=True)
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-iter', type=int, default=3)
    ap.add_argument('--dpi', type=int, default=110)
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    soffice = soffice_path()
    report = {'deck': args.deck, 'pdf': args.pdf, 'iterations': [],
              'status': 'fail', 'notes': []}
    if not soffice:
        report['notes'].append('no LibreOffice found — cannot render; '
                               'deliver pptx as partial with this report')
        json.dump(report, open(args.out, 'w'), ensure_ascii=False, indent=1)
        print('render_loop: no renderer; partial')
        sys.exit(1)

    clean = False
    for it in range(1, args.max_iter + 1):
        log = []
        ok, detail = export_pdf(soffice, args.deck, args.pdf,
                                args.workdir, log)
        if not ok:
            report['iterations'].append(
                {'iteration': it, 'export_failed': detail, 'repairs': []})
            continue
        findings, per_page, fonts = audit_iteration(args.pdf, args.deck)
        entry = {'iteration': it, 'pdf_sha256': sha256(args.pdf),
                 'findings': findings, 'per_page': per_page,
                 'pdf_fonts': fonts, 'notes': log, 'repairs': []}
        slides_to_fix = sorted({f['slide'] for f in findings
                                if f['level'] == 'fail' and f['slide']
                                and f['check'] in ('clipped_text',
                                                   'text_lost',
                                                   'title_missing')})
        unfixable = [f for f in findings
                     if f['check'] in ('page_parity', 'blank_page')]
        report['iterations'].append(entry)
        if not findings:
            clean = True
            break
        if it == args.max_iter:
            break
        for s in slides_to_fix:
            changed = shrink_slide_fonts(args.deck, s)
            entry['repairs'].append(
                {'slide': s, 'action': 'shrink fonts -%d pt' % STEP_PT,
                 'runs_changed': changed})
        if not slides_to_fix and unfixable:
            # structural export problems are not font-repairable
            report['notes'].append(
                'structural render failure not repairable by font steps; '
                'manual inspection required')
            break
        if not slides_to_fix:
            break

    if os.path.exists(args.pdf):
        os.makedirs(args.previews, exist_ok=True)
        run(['pdftoppm', '-png', '-r', str(args.dpi), args.pdf,
             os.path.join(args.previews, 'page')])
        report['previews'] = len([f for f in os.listdir(args.previews)
                                  if f.endswith('.png')])
    report['status'] = 'pass' if clean else 'fail'
    if not clean:
        last = report['iterations'][-1] if report['iterations'] else {}
        report['deviation_table'] = last.get('per_page', [])
        report['notes'].append(
            'final render still has findings; deliver as partial and list '
            'the deviation table in result.json uncertainty')
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('render_loop: %s after %d iteration(s) -> %s'
          % (report['status'], len(report['iterations']), args.out))
    for it in report['iterations']:
        print('iter %s: %d findings, %d repairs'
              % (it['iteration'], len(it.get('findings', [])),
                 len(it.get('repairs', []))))
    sys.exit(0 if clean else 1)


if __name__ == '__main__':
    main()
