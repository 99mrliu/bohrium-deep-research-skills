#!/usr/bin/env python3
"""Export a deck to PDF + PNG previews and verify the rendering.

Uses LibreOffice headless with a *private* user profile and --norestore
(a bare first invocation commonly crashes with DeploymentException — this
script retries automatically). Verifies: PDF page count == slide count;
expected strings present in the PDF text layer (title, a caption, …); fonts
listed by pdffonts against the template theme fonts (substitutions are
recorded as warnings); renders PNG previews with pdftoppm for visual
inspection. Everything goes into an export-check JSON.

Usage:
    python export_check.py deck.pptx export.pdf \
        --expect "Deck title" --expect "Fig. 1" \
        --previews previews_dir --out export_check.json
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, '', 'tool not found: ' + cmd[0]
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout: ' + cmd[0]


def find_soffice():
    for name in ('soffice', 'libreoffice'):
        p = shutil.which(name)
        if p:
            return p
    for cand in ('/Applications/LibreOffice.app/Contents/MacOS/soffice',
                 '/usr/lib/libreoffice/program/soffice'):
        if os.path.exists(cand):
            return cand
    return None


def export_pdf(deck, pdf, workdir):
    soffice = find_soffice()
    if not soffice:
        return None, 'no LibreOffice/soffice found'
    profile = os.path.join(workdir, 'lo_profile')
    outdir = os.path.dirname(os.path.abspath(pdf))
    cmd = [soffice, '--headless', '--norestore', '--nolockcheck',
           '-env:UserInstallation=file://' + os.path.abspath(profile),
           '--convert-to', 'pdf', '--outdir', outdir, deck]
    rc, out, err = run(cmd)
    produced = os.path.join(outdir, os.path.splitext(
        os.path.basename(deck))[0] + '.pdf')
    if (rc != 0 or not os.path.exists(produced)) and \
            ('DeploymentException' in err or 'DeploymentException' in out):
        shutil.rmtree(profile, ignore_errors=True)
        rc, out, err = run(cmd)  # retry once with a fresh profile
    if os.path.exists(produced) and produced != pdf:
        os.replace(produced, pdf)
    if not os.path.exists(pdf):
        return None, 'export failed rc=%s: %s %s' % (rc, out[-300:],
                                                     err[-300:])
    return pdf, None


def pdf_text(pdf):
    rc, out, err = run(['pdftotext', pdf, '-'])
    return out if rc == 0 else ''


def pdf_pages(pdf):
    rc, out, _ = run(['pdfinfo', pdf])
    m = re.search(r'Pages:\s+(\d+)', out or '')
    if m:
        return int(m.group(1))
    text = pdf_text(pdf)
    if text:
        n = text.count('\f')
        if not text.endswith('\f') and text.strip():
            n += 1
        return n or None
    data = open(pdf, 'rb').read()
    n = len(re.findall(rb'/Type\s*/Page[^s]', data))
    return n or None


def pdf_fonts(pdf):
    rc, out, _ = run(['pdffonts', pdf])
    fonts = []
    if rc == 0:
        for line in out.splitlines()[2:]:
            cols = line.split()
            if cols:
                fonts.append({'name': cols[0],
                              'emb': 'yes' in line.split()[-4:-3]})
        return fonts
    # fallback: scrape /BaseFont names from raw PDF
    data = open(pdf, 'rb').read()
    names = sorted({m.group(1).decode('latin1') for m in
                    re.finditer(rb'/BaseFont\s*/([^\s/<>\[\]()]+)', data)})
    return [{'name': n.split('+')[-1], 'emb': None} for n in names]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck')
    ap.add_argument('pdf')
    ap.add_argument('--expect', action='append', default=[])
    ap.add_argument('--previews')
    ap.add_argument('--preview-dpi', type=int, default=110)
    ap.add_argument('--theme-fonts', default='',
                    help='comma-separated theme font names to look for')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    from pptx import Presentation
    report = {'deck': args.deck, 'pdf': args.pdf, 'findings': []}

    def rec(level, msg):
        report['findings'].append({'level': level, 'msg': msg})

    workdir = tempfile.mkdtemp(prefix='export_check_')
    pdf, err = export_pdf(args.deck, args.pdf, workdir)
    if err:
        rec('fail', err)
        report['status'] = 'fail'
        json.dump(report, open(args.out, 'w'), ensure_ascii=False, indent=2)
        print('export_check: FAIL -', err)
        sys.exit(1)

    n_slides = len(Presentation(args.deck).slides._sldIdLst)
    n_pages = pdf_pages(pdf)
    report['slides'] = n_slides
    report['pdf_pages'] = n_pages
    if n_pages != n_slides:
        rec('fail', 'PDF page count %s != slide count %s'
            % (n_pages, n_slides))

    text = pdf_text(pdf)
    squash = lambda x: re.sub(r'\s+', '', x)
    for s in args.expect:
        if s and squash(s) not in squash(text):
            rec('fail', 'expected string missing from PDF: %r' % s)

    fonts = pdf_fonts(pdf)
    report['pdf_fonts'] = [f['name'] for f in fonts]
    not_emb = [f['name'] for f in fonts if f['emb'] is False]
    if not_emb:
        rec('warn', 'non-embedded fonts in PDF: %s' % not_emb)
    for tf_ in [t for t in args.theme_fonts.split(',') if t]:
        if not any(tf_.lower() in f['name'].lower() for f in fonts):
            rec('warn', 'theme font %r absent from PDF (substituted?)' % tf_)

    if args.previews:
        os.makedirs(args.previews, exist_ok=True)
        rc, _, perr = run(['pdftoppm', '-png', '-r', str(args.preview_dpi),
                           pdf, os.path.join(args.previews, 'page')])
        if rc == 0:
            report['previews'] = sorted(
                os.path.join(args.previews, f)
                for f in os.listdir(args.previews) if f.endswith('.png'))
        else:
            rec('warn', 'preview render failed: %s' % perr[-200:])

    fails = [f for f in report['findings'] if f['level'] == 'fail']
    report['status'] = 'fail' if fails else 'pass'
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('export_check: %s (%d fail, %d warn) -> %s'
          % (report['status'], len(fails),
             len(report['findings']) - len(fails), args.out))
    for f in report['findings']:
        print('%s: %s' % (f['level'].upper(), f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
