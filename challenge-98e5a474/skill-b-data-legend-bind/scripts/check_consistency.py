#!/usr/bin/env python3
"""check_consistency.py — consistency gate between a chart's binding spec,
its frozen data snapshot, the legend map actually rendered, and the final
SVG (stdlib + re-render comparison).

Checks (fail unless noted):
  1. every column the spec references exists in the snapshot data;
  2. legend entries in legend_map == the actual category values in the data
     (same set, same order, none missing, none invented);
  3. palette size >= number of categories (color count matches classes);
  4. declared axis units appear in the SVG axis labels;
  5. anti-hallucination: every visible SVG text is the title, an axis label,
     a legend entry, or a tick label (numeric or a data category);
  6. data drift: snapshot sha256 == spec.source.sha256 (when declared);
  7. determinism (warning only): two renders produce identical SVG after
     stripping comment/metadata lines.

Usage:
  python3 check_consistency.py --spec s.json --snapshot DIR \
      --legend-map lm.json --svg figure.svg --out report.json
Exit 0 = pass, 1 = fail.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
        except csv.Error:
            dialect = csv.excel
        return list(csv.DictReader(f, dialect=dialect))


def unique_in_order(values):
    seen, out = set(), []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def svg_texts(path):
    root = ET.parse(path).getroot()
    out = []
    for el in root.iter():
        if el.tag in (NS + 'text', 'text'):
            s = ''.join(el.itertext()).strip()
            if s:
                out.append(re.sub(r'\s+', ' ', s))
    return out


def is_number(s):
    try:
        float(s.replace(',', '').replace('−', '-').rstrip('%'))
        return True
    except ValueError:
        return False


def strip_svg(path):
    text = open(path, encoding='utf-8').read()
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'<metadata>.*?</metadata>', '', text, flags=re.S)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--snapshot', required=True)
    ap.add_argument('--legend-map', required=True)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--renderer', default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'render_chart.py'))
    args = ap.parse_args()

    with open(args.spec, encoding='utf-8') as f:
        spec = json.load(f)
    with open(args.legend_map, encoding='utf-8') as f:
        lmap = json.load(f)
    data_path = os.path.join(args.snapshot, spec['data_file'])
    rows = load_rows(data_path)
    cols = set(rows[0].keys())
    failures, warnings, checks = [], [], []

    # 1. referenced columns exist
    needed = [spec['x']['column'], spec['y']['column']]
    if spec.get('category_column'):
        needed.append(spec['category_column'])
    if spec.get('yerr_column'):
        needed.append(spec['yerr_column'])
    missing = [c for c in needed if c not in cols]
    if missing:
        failures.append('spec references missing columns: %s' % missing)
    checks.append({'name': 'columns_exist', 'needed': needed})

    # 2. legend entries == data categories
    cat_col = spec.get('category_column')
    data_cats = []
    if cat_col:
        vals = [(r.get(cat_col) or '').strip() for r in rows]
        vals = [v if v else (spec.get('na_label') or v) for v in vals]
        data_cats = unique_in_order([v for v in vals if v])
    map_cats = [m['category'] for m in lmap.get('mapping', [])]
    if cat_col:
        if map_cats != data_cats:
            failures.append('legend entries != data categories: legend=%r '
                            'data=%r' % (map_cats, data_cats))
    checks.append({'name': 'legend_equals_data_categories',
                   'legend': map_cats, 'data': data_cats})

    # 3. color count == category count
    palette = spec.get('palette') or []
    colors_in_map = unique_in_order([m['color'] for m in
                                     lmap.get('mapping', [])])
    if cat_col and len(colors_in_map) < len(data_cats):
        failures.append('only %d colors for %d categories'
                        % (len(colors_in_map), len(data_cats)))
    if palette and cat_col and len(palette) < len(data_cats):
        failures.append('spec palette has %d colors for %d categories'
                        % (len(palette), len(data_cats)))
    checks.append({'name': 'color_count_matches_categories'})

    # 4. axis units present in SVG labels
    texts = svg_texts(args.svg)
    for role in ('x', 'y'):
        unit = spec[role].get('unit')
        if unit and not any(unit in t for t in texts):
            failures.append('declared %s unit %r absent from SVG texts'
                            % (role, unit))
    checks.append({'name': 'axis_units_present'})

    # 5. anti-hallucination text gate
    allowed = set()
    if spec.get('title'):
        allowed.add(spec['title'])
    for role in ('x', 'y'):
        label = spec[role].get('label') or spec[role]['column']
        unit = spec[role].get('unit')
        allowed.add('%s (%s)' % (label, unit) if unit else label)
    if spec.get('legend_title'):
        allowed.add(spec['legend_title'])
    xvals = unique_in_order([(r.get(spec['x']['column']) or '').strip()
                             for r in rows])
    allowed.update(xvals)
    allowed.update(map_cats)
    bad = [t for t in texts
           if t not in allowed and not is_number(t) and t not in
           {a.get('text') for a in spec.get('annotations', [])}]
    if bad:
        failures.append('untraceable text in SVG: %r' % sorted(set(bad)))
    checks.append({'name': 'anti_hallucination_text_gate',
                   'svg_texts': len(texts)})

    # 6. data drift
    sha = sha256_of(data_path)
    declared = (spec.get('source') or {}).get('sha256')
    if declared and declared != sha:
        failures.append('data drift: snapshot sha256=%s spec declares=%s'
                        % (sha[:12], declared[:12]))
    if lmap.get('data_sha256') and lmap['data_sha256'] != sha:
        failures.append('legend_map was rendered from a different data '
                        'version (sha256 mismatch)')
    checks.append({'name': 'data_version_match', 'sha256': sha})

    # 7. determinism (warning only)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cmd = [sys.executable, args.renderer, '--spec', args.spec,
               '--snapshot', args.snapshot, '--outdir', td,
               '--basename', 'r2', '--render-only']
        p = subprocess.run(cmd, capture_output=True, text=True)
        r2 = os.path.join(td, 'r2.svg')
        if p.returncode == 0 and os.path.isfile(r2):
            if strip_svg(r2) != strip_svg(args.svg):
                warnings.append('re-render differs from delivered SVG '
                                '(figure was edited outside the pipeline?)')
        else:
            warnings.append('determinism re-render failed: '
                            + (p.stderr or '')[-200:])
    checks.append({'name': 'deterministic_redraw', 'level': 'warning'})

    report = {'status': 'pass' if not failures else 'fail',
              'spec': args.spec, 'svg': args.svg,
              'data_sha256': sha,
              'checks': checks, 'failures': failures, 'warnings': warnings}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'],
                      'failures': len(failures),
                      'warnings': len(warnings)}, ensure_ascii=False))
    for f_ in failures:
        print('FAIL: ' + f_, file=sys.stderr)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
