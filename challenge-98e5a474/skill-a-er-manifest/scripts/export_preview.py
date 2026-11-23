#!/usr/bin/env python3
"""export_preview.py — export an SVG to PNG (requested dpi) and PDF through
the first available backend, then verify the exported files (stdlib only;
missing backends are reported honestly, never faked).

Backend probe order:
  PNG: cairosvg (python) -> rsvg-convert -> inkscape -> chromium/chrome
       headless screenshot -> ImageMagick (magick/convert)
  PDF: cairosvg -> rsvg-convert -> inkscape -> chromium headless print-to-pdf
  PDF preview: pdftoppm / pdftocairo (when direct PNG export failed)

Verification: PNG signature + IHDR pixel size; PDF %PDF header. Results,
including every failure, go into the export report JSON.

Usage:
  python3 export_preview.py --svg figure.svg --outdir /app/output \
      --basename figure --dpi 300 --report export_report.json
Exit code 0 when at least one export succeeded, 1 when all failed.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile


def probe(cmd):
    return shutil.which(cmd)


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(33)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h = struct.unpack('>II', head[16:24])
    return w, h


def is_pdf(path):
    with open(path, 'rb') as f:
        return f.read(5) == b'%PDF-'


def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stderr or '')[-400:]
    except Exception as exc:  # missing binary, timeout, ...
        return -1, str(exc)


def svg_size(svg_path):
    import re
    with open(svg_path, encoding='utf-8') as f:
        head = f.read(2000)
    mw = re.search(r'\bwidth="([0-9.]+)', head)
    mh = re.search(r'\bheight="([0-9.]+)', head)
    return (float(mw.group(1)) if mw else 1000.0,
            float(mh.group(1)) if mh else 640.0)


def export_png(svg, out, dpi, failures):
    w_px, _ = svg_size(svg)
    scale = dpi / 96.0
    target_w = max(1, int(round(w_px * scale)))
    try:
        import cairosvg
        cairosvg.svg2png(url=svg, write_to=out, scale=scale)
        return 'cairosvg'
    except Exception as exc:
        failures.append({'format': 'png', 'backend': 'cairosvg',
                         'error': str(exc)[:300]})
    if probe('rsvg-convert'):
        rc, err = run(['rsvg-convert', '-w', str(target_w), '-f', 'png',
                       '-o', out, svg])
        if rc == 0 and os.path.exists(out):
            return 'rsvg-convert'
        failures.append({'format': 'png', 'backend': 'rsvg-convert',
                         'error': err})
    if probe('inkscape'):
        rc, err = run(['inkscape', svg, '--export-type=png',
                       '--export-filename=%s' % out,
                       '--export-dpi=%d' % dpi])
        if rc == 0 and os.path.exists(out):
            return 'inkscape'
        failures.append({'format': 'png', 'backend': 'inkscape',
                         'error': err})
    for chrome in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
        if probe(chrome):
            rc, err = run([chrome, '--headless=new', '--disable-gpu',
                           '--screenshot=%s' % out,
                           '--window-size=%d,%d' % (target_w, target_w),
                           'file://' + os.path.abspath(svg)])
            if rc == 0 and os.path.exists(out):
                return chrome + ' (headless screenshot)'
            failures.append({'format': 'png', 'backend': chrome,
                             'error': err})
            break
    if probe('qlmanage'):  # macOS QuickLook thumbnail, last resort
        with tempfile.TemporaryDirectory() as td:
            rc, err = run(['qlmanage', '-t', '-s', str(target_w), '-o', td,
                           svg])
            produced = os.path.join(td, os.path.basename(svg) + '.png')
            if rc == 0 and os.path.exists(produced):
                shutil.copyfile(produced, out)
                return 'qlmanage'
            failures.append({'format': 'png', 'backend': 'qlmanage',
                             'error': err})
    for im in ('magick', 'convert'):
        if probe(im):
            cmd = ([im] if im == 'magick' else [im]) + \
                  ['-density', str(dpi), svg, out]
            rc, err = run(cmd)
            if rc == 0 and os.path.exists(out):
                return im
            failures.append({'format': 'png', 'backend': im, 'error': err})
            break
    return None


def export_pdf(svg, out, failures):
    try:
        import cairosvg
        cairosvg.svg2pdf(url=svg, write_to=out)
        return 'cairosvg'
    except Exception as exc:
        failures.append({'format': 'pdf', 'backend': 'cairosvg',
                         'error': str(exc)[:300]})
    if probe('rsvg-convert'):
        rc, err = run(['rsvg-convert', '-f', 'pdf', '-o', out, svg])
        if rc == 0 and os.path.exists(out):
            return 'rsvg-convert'
        failures.append({'format': 'pdf', 'backend': 'rsvg-convert',
                         'error': err})
    if probe('inkscape'):
        rc, err = run(['inkscape', svg, '--export-type=pdf',
                       '--export-filename=%s' % out])
        if rc == 0 and os.path.exists(out):
            return 'inkscape'
        failures.append({'format': 'pdf', 'backend': 'inkscape',
                         'error': err})
    for chrome in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
        if probe(chrome):
            rc, err = run([chrome, '--headless=new', '--disable-gpu',
                           '--print-to-pdf=%s' % out, '--no-pdf-header-footer',
                           'file://' + os.path.abspath(svg)])
            if rc == 0 and os.path.exists(out):
                return chrome + ' (headless print-to-pdf)'
            failures.append({'format': 'pdf', 'backend': chrome,
                             'error': err})
            break
    return None


def pdf_to_png(pdf, out, dpi, failures):
    for tool, cmd in (
            ('pdftoppm', ['pdftoppm', '-png', '-r', str(dpi), '-singlefile',
                          pdf, out[:-4]]),
            ('pdftocairo', ['pdftocairo', '-png', '-r', str(dpi),
                            '-singlefile', pdf, out[:-4]])):
        if probe(tool):
            rc, err = run(cmd)
            if rc == 0 and os.path.exists(out):
                return tool
            failures.append({'format': 'png-from-pdf', 'backend': tool,
                             'error': err})
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--basename', required=True)
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    png = os.path.join(args.outdir, args.basename + '.png')
    pdf = os.path.join(args.outdir, args.basename + '.pdf')
    failures, exports = [], []

    backend = export_png(args.svg, png, args.dpi, failures)
    if backend:
        size = png_size(png)
        exports.append({'format': 'png', 'path': png, 'backend': backend,
                        'bytes': os.path.getsize(png),
                        'requested_dpi': args.dpi,
                        'pixel_size': list(size) if size else None,
                        'verified': size is not None})
    backend_pdf = export_pdf(args.svg, pdf, failures)
    if backend_pdf:
        ok = is_pdf(pdf)
        exports.append({'format': 'pdf', 'path': pdf, 'backend': backend_pdf,
                        'bytes': os.path.getsize(pdf), 'verified': ok})
    if not backend and backend_pdf:
        b2 = pdf_to_png(pdf, png, args.dpi, failures)
        if b2:
            size = png_size(png)
            exports.append({'format': 'png', 'path': png, 'backend': b2,
                            'bytes': os.path.getsize(png),
                            'requested_dpi': args.dpi,
                            'pixel_size': list(size) if size else None,
                            'verified': size is not None})

    report = {'status': 'ok' if exports else 'failed',
              'svg': args.svg,
              'exports': exports,
              'failures': failures,
              'note': ('all export backends unavailable; SVG source remains '
                       'the editable deliverable' if not exports else '')}
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'],
                      'exports': [e['format'] + ':' + e['backend']
                                  for e in exports],
                      'failures': len(failures)}, ensure_ascii=False))
    sys.exit(0 if exports else 1)


if __name__ == '__main__':
    main()
