#!/usr/bin/env python3
"""svg_lint.py — structural and editability checks for an SVG source file
(stdlib only).

Checks:
  layers    : at least one inkscape layer group (or data-layer group)
  ids       : every id unique; count of identifiable elements
  text      : <text> elements present and not converted to outlines
              (heuristic: path/text ratio); font-family declared somewhere
  rasters   : embedded <image> elements (must be justified by the caller)
  forbidden : <script>, <foreignObject>
  geometry  : width/height + viewBox present; min font-size; min stroke-width

Usage:
  python3 svg_lint.py --svg figure.svg --out lint_report.json
Exit 0 = pass (warnings allowed), 1 = fail.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
INK = '{http://www.inkscape.org/namespaces/inkscape}'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-font-pt', type=float, default=5.0)
    ap.add_argument('--min-stroke-pt', type=float, default=0.25)
    args = ap.parse_args()

    raw = open(args.svg, encoding='utf-8').read()
    root = ET.fromstring(raw)
    failures, warnings, checks = [], [], []

    layers = [el for el in root.iter()
              if el.attrib.get(INK + 'groupmode') == 'layer'
              or 'data-layer' in el.attrib]
    layer_names = [el.attrib.get(INK + 'label') or
                   el.attrib.get('data-layer') for el in layers]
    if not layers:
        failures.append('no layer groups (inkscape:groupmode="layer" or '
                        'data-layer) found')
    checks.append({'name': 'layers', 'layers': layer_names})

    ids = {}
    for el in root.iter():
        i = el.attrib.get('id')
        if i:
            ids[i] = ids.get(i, 0) + 1
    dup = sorted(i for i, n in ids.items() if n > 1)
    if dup:
        failures.append('duplicate ids: %s' % dup)
    checks.append({'name': 'ids_unique', 'id_count': len(ids)})

    texts = [el for el in root.iter() if el.tag in (NS + 'text', 'text')]
    paths = [el for el in root.iter() if el.tag in (NS + 'path', 'path')]
    images = [el for el in root.iter() if el.tag in (NS + 'image', 'image')]
    if not texts:
        warnings.append('no <text> elements: figure has no editable text')
    if paths and not texts and len(paths) > 20:
        failures.append('text appears converted to outlines '
                        '(%d paths, 0 <text>)' % len(paths))
    if 'font-family' not in raw:
        warnings.append('no font-family declared anywhere')
    fonts = sorted(set(re.findall(r'font-family="([^"]+)"', raw)))
    checks.append({'name': 'editable_text',
                   'text_elements': len(texts),
                   'path_elements': len(paths),
                   'fonts_declared': fonts})

    if images:
        warnings.append('%d embedded <image> raster element(s) — must be '
                        'justified (not vector content faked as bitmap)'
                        % len(images))
    checks.append({'name': 'raster_images', 'count': len(images)})

    for tag in ('script', 'foreignObject'):
        if re.search(r'<%s[\s>]' % tag, raw):
            failures.append('forbidden element <%s> present' % tag)
    checks.append({'name': 'forbidden_elements'})

    if 'viewBox' not in root.attrib:
        warnings.append('no viewBox on root <svg>')
    if not re.match(r'^[0-9.]+$', root.attrib.get('width', '')):
        warnings.append('root width is not plain user units: %r'
                        % root.attrib.get('width'))
    sizes = [float(s) for s in
             re.findall(r'font-size="([0-9.]+)"', raw)]
    small = [s for s in sizes if s < args.min_font_pt]
    if small:
        warnings.append('font sizes below %.1f: %s' % (args.min_font_pt,
                                                       sorted(small)[:5]))
    strokes = [float(s) for s in
               re.findall(r'stroke-width="([0-9.]+)"', raw)]
    thin = [s for s in strokes if s < args.min_stroke_pt]
    if thin:
        warnings.append('stroke widths below %.2f: %s'
                        % (args.min_stroke_pt, sorted(thin)[:5]))
    checks.append({'name': 'geometry',
                   'min_font_size': min(sizes) if sizes else None,
                   'min_stroke_width': min(strokes) if strokes else None})

    report = {'status': 'pass' if not failures else 'fail',
              'svg': args.svg, 'checks': checks,
              'failures': failures, 'warnings': warnings,
              'available_ids': sorted(ids)[:500]}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'],
                      'layers': layer_names,
                      'ids': len(ids), 'texts': len(texts),
                      'failures': len(failures),
                      'warnings': len(warnings)}, ensure_ascii=False))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
