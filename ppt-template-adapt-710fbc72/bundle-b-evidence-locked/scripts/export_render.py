#!/usr/bin/env python3
"""Render the deck to PDF + per-page PNGs and verify the export honestly.

- LibreOffice headless, private profile, one automatic retry on
  DeploymentException (bare first runs crash on fresh machines).
- Verifies PDF page count equals slide count and that each slide's title
  string appears on the matching PDF page (order-sensitive spot check of
  pptx<->PDF correspondence).
- Renders PNG previews with pdftoppm (or the runtime pdf-render tool).
- Records everything, including tool versions, in export_report.json;
  a failed export is a recorded `partial`, never a silent gap.

Usage:
    python export_render.py deck.pptx export.pdf --previews DIR \
        --expect-per-page --out export_report.json
"""
import argparse
import json
import os
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
        return 127, '', 'missing: ' + cmd[0]


def soffice_path():
    for c in ('soffice', 'libreoffice',
              '/Applications/LibreOffice.app/Contents/MacOS/soffice',
              '/usr/lib/libreoffice/program/soffice'):
        p = shutil.which(c) if '/' not in c else (c if os.path.exists(c)
                                                  else None)
        if p:
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck')
    ap.add_argument('pdf')
    ap.add_argument('--previews', required=True)
    ap.add_argument('--dpi', type=int, default=110)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    report = {'deck': args.deck, 'pdf': args.pdf, 'findings': [],
              'tools': {}}

    def rec(level, msg):
        report['findings'].append({'level': level, 'msg': msg})

    soffice = soffice_path()
    report['tools']['soffice'] = soffice
    if not soffice:
        rec('fail', 'no LibreOffice found; deliver pptx + diagnostics as '
                    'partial and record the missing renderer')
    else:
        work = tempfile.mkdtemp(prefix='lo_export_')
        profile = os.path.join(work, 'profile')
        outdir = os.path.dirname(os.path.abspath(args.pdf))
        cmd = [soffice, '--headless', '--norestore', '--nolockcheck',
               '-env:UserInstallation=file://' + profile,
               '--convert-to', 'pdf', '--outdir', outdir, args.deck]
        rc, out, err = run(cmd, timeout=600)
        produced = os.path.join(outdir, os.path.splitext(
            os.path.basename(args.deck))[0] + '.pdf')
        if not os.path.exists(produced) and \
                ('DeploymentException' in (err + out) or rc != 0):
            shutil.rmtree(profile, ignore_errors=True)
            rc, out, err = run(cmd, timeout=600)
            rec('warn', 'export retried with a fresh LibreOffice profile')
        if os.path.exists(produced) and os.path.abspath(produced) != \
                os.path.abspath(args.pdf):
            os.replace(produced, args.pdf)
        rcv, ver, _ = run([soffice, '--version'])
        report['tools']['soffice_version'] = (ver or '').strip()
        if not os.path.exists(args.pdf):
            rec('fail', 'PDF export failed rc=%s: %s' % (rc, (err or out)[-300:]))

    if os.path.exists(args.pdf):
        rc, text, _ = run(['pdftotext', args.pdf, '-'])
        pages = text.split('\f') if rc == 0 else []
        if pages and not pages[-1].strip():
            pages.pop()
        from pptx import Presentation
        prs = Presentation(args.deck)
        titles = []
        for slide in prs.slides:
            t = ''
            try:
                t = slide.shapes.title.text.strip()
            except AttributeError:
                pass
            titles.append(t)
        report['slides'] = len(titles)
        report['pdf_pages'] = len(pages)
        if len(pages) != len(titles):
            rec('fail', 'PDF pages %d != slides %d'
                % (len(pages), len(titles)))
        import re as _re
        squash = lambda x: _re.sub(r'\s+', '', x)
        for i, (t, ptext) in enumerate(zip(titles, pages), start=1):
            if t and squash(t) not in squash(ptext):
                rec('warn', 'slide %d title not found on its PDF page' % i)
        os.makedirs(args.previews, exist_ok=True)
        rc, _, perr = run(['pdftoppm', '-png', '-r', str(args.dpi),
                           args.pdf, os.path.join(args.previews, 'page')])
        if rc == 0:
            report['preview_count'] = len([f for f in
                                           os.listdir(args.previews)
                                           if f.endswith('.png')])
        else:
            rec('warn', 'preview rendering failed: %s' % perr[-200:])

    fails = [f for f in report['findings'] if f['level'] == 'fail']
    report['status'] = 'fail' if fails else 'pass'
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('export: %s -> %s' % (report['status'], args.out))
    for f in report['findings']:
        print('%s: %s' % (f['level'].upper(), f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
