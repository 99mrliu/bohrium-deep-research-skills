#!/usr/bin/env python3
"""export_gate.py — journal-profile export of an SVG with per-format
compliance verification (stdlib only; missing backends are reported as
degraded, never faked).

Exports the formats listed in the export profile, then verifies each file:
  PNG : signature + IHDR pixel size vs expected (width_mm * dpi / 25.4),
        pHYs chunk DPI when present
  PDF : %PDF header; font embedding via pdffonts when available
        (recorded as unknown when the tool is missing, not as pass)
  TIFF: signature + byte size (full tag parsing out of scope)
  EPS : %!PS header + %%BoundingBox line

Usage:
  python3 export_gate.py --svg figure.svg --profile generic_1col \
      --outdir OUT --basename figure --report export_compliance.json
Exit 0 when every requested format is exported and verified, 1 otherwise.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))


def probe(cmd):
    return shutil.which(cmd)


def run(cmd, timeout=240):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or '')[-600:], (p.stderr or '')[-600:]
    except Exception as exc:
        return -1, '', str(exc)


def svg_user_width(svg_path):
    import re
    head = open(svg_path, encoding='utf-8').read(2000)
    m = re.search(r'\bwidth="([0-9.]+)', head)
    return float(m.group(1)) if m else None


def png_info(path):
    with open(path, 'rb') as f:
        data = f.read(64)
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h = struct.unpack('>II', data[16:24])
    dpi = None
    if data[25:33] == b'pHYs':
        xppu, yppu, unit = struct.unpack('>IIB', data[33:42])
        if unit == 1:
            dpi = round(xppu * 0.0254)
    return {'width_px': w, 'height_px': h, 'dpi': dpi}


def export_one(fmt, svg, out, dpi, failures):
    """Try backends in order; return backend name or None."""
    if fmt == 'png':
        try:
            import cairosvg
            cairosvg.svg2png(url=svg, write_to=out, dpi=dpi)
            return 'cairosvg'
        except Exception as exc:
            failures.append({'format': fmt, 'backend': 'cairosvg',
                             'error': str(exc)[:300]})
        if probe('rsvg-convert'):
            rc, so, se = run(['rsvg-convert', '-d', str(dpi), '-f', 'png',
                              '-o', out, svg])
            if rc == 0 and os.path.exists(out):
                return 'rsvg-convert'
            failures.append({'format': fmt, 'backend': 'rsvg-convert',
                             'error': se})
        if probe('inkscape'):
            rc, so, se = run(['inkscape', svg, '--export-type=png',
                              '--export-filename=%s' % out,
                              '--export-dpi=%d' % dpi])
            if rc == 0 and os.path.exists(out):
                return 'inkscape'
            failures.append({'format': fmt, 'backend': 'inkscape',
                             'error': se})
        for im in ('magick', 'convert'):
            if probe(im):
                rc, so, se = run([im, '-density', str(dpi), svg, out])
                if rc == 0 and os.path.exists(out):
                    return im
                failures.append({'format': fmt, 'backend': im, 'error': se})
                break
    elif fmt == 'pdf':
        try:
            import cairosvg
            cairosvg.svg2pdf(url=svg, write_to=out)
            return 'cairosvg'
        except Exception as exc:
            failures.append({'format': fmt, 'backend': 'cairosvg',
                             'error': str(exc)[:300]})
        if probe('rsvg-convert'):
            rc, so, se = run(['rsvg-convert', '-f', 'pdf', '-o', out, svg])
            if rc == 0 and os.path.exists(out):
                return 'rsvg-convert'
            failures.append({'format': fmt, 'backend': 'rsvg-convert',
                             'error': se})
        if probe('inkscape'):
            rc, so, se = run(['inkscape', svg, '--export-type=pdf',
                              '--export-filename=%s' % out])
            if rc == 0 and os.path.exists(out):
                return 'inkscape'
            failures.append({'format': fmt, 'backend': 'inkscape',
                             'error': se})
    elif fmt == 'eps':
        if probe('inkscape'):
            rc, so, se = run(['inkscape', svg, '--export-type=eps',
                              '--export-filename=%s' % out])
            if rc == 0 and os.path.exists(out):
                return 'inkscape'
            failures.append({'format': fmt, 'backend': 'inkscape',
                             'error': se})
        if probe('rsvg-convert'):
            rc, so, se = run(['rsvg-convert', '-f', 'ps', '-o', out, svg])
            if rc == 0 and os.path.exists(out):
                return 'rsvg-convert (ps)'
            failures.append({'format': fmt, 'backend': 'rsvg-convert',
                             'error': se})
    elif fmt == 'tiff':
        png_tmp = tempfile.mktemp(suffix='.png')
        b = export_one('png', svg, png_tmp, dpi, failures)
        if b:
            try:
                from PIL import Image
                Image.open(png_tmp).save(out, compression='tiff_lzw')
                return b + ' + Pillow'
            except Exception as exc:
                failures.append({'format': fmt, 'backend': 'Pillow',
                                 'error': str(exc)[:300]})
            for im in ('magick', 'convert'):
                if probe(im):
                    rc, so, se = run([im, '-density', str(dpi), svg,
                                      '-compress', 'LZW', out])
                    if rc == 0 and os.path.exists(out):
                        return im
                    failures.append({'format': fmt, 'backend': im,
                                     'error': se})
                    break
        if os.path.exists(png_tmp):
            os.unlink(png_tmp)
    return None


def verify(fmt, path, profile, dpi, svg_w):
    v = {'checks': [], 'ok': True}

    def chk(name, ok, detail):
        v['checks'].append({'name': name, 'ok': ok, 'detail': detail})
        if ok is False:
            v['ok'] = False

    size = os.path.getsize(path)
    chk('nonempty', size > 0, '%d bytes' % size)
    if fmt == 'png':
        info = png_info(path)
        chk('signature', info is not None, 'PNG IHDR parsed')
        if info:
            if svg_w and profile.get('width_mm'):
                expected = round(profile['width_mm'] / 25.4 * dpi)
                tol = max(4, expected // 20)
                chk('pixel_width', abs(info['width_px'] - expected) <= tol,
                    'got %d px, expected ~%d px (±%d)'
                    % (info['width_px'], expected, tol))
            chk('dpi_tag', (info['dpi'] == dpi) if info['dpi'] else None,
                'pHYs=%s dpi' % info['dpi'] if info['dpi']
                else 'no pHYs chunk (viewer decides)')
    elif fmt == 'pdf':
        head = open(path, 'rb').read(5)
        chk('signature', head == b'%PDF-', repr(head))
        if probe('pdffonts'):
            rc, so, se = run(['pdffonts', path])
            if rc == 0:
                lines = [l for l in so.splitlines() if l.strip()
                         and not l.startswith('-')
                         and not l.lower().startswith('name ')]
                unemb = []
                for l in lines:
                    flags = [t for t in l.split() if t in ('yes', 'no')]
                    if flags and flags[0] == 'no':  # emb column is first flag
                        unemb.append(l)
                chk('fonts_embedded', len(unemb) == 0 if lines else None,
                    '%d fonts, %d not embedded' % (len(lines), len(unemb))
                    if lines else 'no fonts (vector-only or outlined)')
        else:
            chk('fonts_embedded', None, 'pdffonts unavailable: unknown')
    elif fmt == 'tiff':
        head = open(path, 'rb').read(4)
        chk('signature', head[:2] in (b'II', b'MM') and
            head[2:4] in (b'\x2a\x00', b'\x00\x2a'), repr(head))
    elif fmt == 'eps':
        head = open(path, 'rb').read(4096).decode('latin-1', 'replace')
        chk('signature', head.startswith('%!PS'), head[:16])
        chk('bounding_box', '%%BoundingBox:' in head, '')
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--profile', default='generic_1col')
    ap.add_argument('--profiles', default=os.path.join(
        _HERE, '..', 'resources', 'export_profiles.json'))
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--basename', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.svg):
        print('SVG not found: ' + args.svg, file=sys.stderr)
        sys.exit(1)
    with open(args.profiles, encoding='utf-8') as f:
        profile = json.load(f)[args.profile]
    dpi = int(profile.get('dpi', 300))
    svg_w = svg_user_width(args.svg)
    os.makedirs(args.outdir, exist_ok=True)

    results, failures = [], []
    for fmt in profile.get('formats', ['pdf', 'png']):
        out = os.path.join(args.outdir, args.basename + '.' + fmt)
        backend = export_one(fmt, args.svg, out, dpi, failures)
        if not backend:
            results.append({'format': fmt, 'status': 'degraded',
                            'reason': 'no working backend'})
            continue
        v = verify(fmt, out, profile, dpi, svg_w)
        results.append({'format': fmt, 'status': 'pass' if v['ok'] else 'fail',
                        'path': out, 'backend': backend,
                        'bytes': os.path.getsize(out),
                        'verification': v['checks']})

    ok = all(r['status'] == 'pass' for r in results) and results
    report = {'status': 'pass' if ok else 'fail',
              'svg': args.svg, 'profile': args.profile,
              'profile_params': profile, 'results': results,
              'backend_failures': failures}
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'],
                      'formats': {r['format']: r['status'] for r in results}},
                     ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
