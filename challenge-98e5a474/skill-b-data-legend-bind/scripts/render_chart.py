#!/usr/bin/env python3
"""render_chart.py — deterministic chart renderer driven by a binding spec
(figure.spec.json). Every visual channel (legend entries, colors, markers,
axis labels with units) is bound to actual data columns; the script contains
no scientific judgement and never invents values.

Requires matplotlib (TIFF export additionally needs Pillow; absence is
degraded honestly in the render log).

Usage:
  python3 render_chart.py --spec figure.spec.json --snapshot DIR \
      --outdir OUT --basename figure --profile generic_1col \
      [--presets journal_presets.json]
Exit 0 on success, 1 on a spec/data error (unknown column, non-numeric y...).
"""
import argparse
import csv
import hashlib
import json
import os
import sys

DEFAULT_PALETTE = ['#4C78A8', '#F58518', '#54A24B', '#E45756', '#72B7B2',
                   '#B279A2', '#FF9DA6', '#9D755D', '#BAB0AC', '#EECA3B']
MARKERS = ['o', 's', '^', 'D', 'v', 'P', 'X', '<', '>', 'h']
CHART_TYPES = ('bar', 'grouped_bar', 'stacked_bar', 'line', 'scatter')
_HERE = os.path.dirname(os.path.abspath(__file__))


class SpecError(Exception):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_table(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(f, dialect=dialect))
    if not rows:
        raise SpecError('data file has no rows: ' + path)
    return rows


def to_float(v):
    try:
        return float(str(v).strip().replace('%', ''))
    except (TypeError, ValueError):
        return None


def unique_in_order(values):
    seen, out = set(), []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def validate(spec, rows):
    cols = set(rows[0].keys())
    for role in ('x', 'y'):
        if role not in spec or 'column' not in spec[role]:
            raise SpecError('spec missing %s.column' % role)
        if spec[role]['column'] not in cols:
            raise SpecError('%s.column %r not in data columns %s'
                            % (role, spec[role]['column'], sorted(cols)))
    if spec.get('category_column') and spec['category_column'] not in cols:
        raise SpecError('category_column %r not in data columns'
                        % spec['category_column'])
    if spec.get('yerr_column') and spec['yerr_column'] not in cols:
        raise SpecError('yerr_column %r not in data columns'
                        % spec['yerr_column'])
    if spec.get('chart_type') not in CHART_TYPES:
        raise SpecError('chart_type must be one of %s' % (CHART_TYPES,))


def axis_text(role):
    label = role.get('label') or role.get('column')
    unit = role.get('unit')
    return '%s (%s)' % (label, unit) if unit else label


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--snapshot', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--basename', required=True)
    ap.add_argument('--profile', default='generic_1col')
    ap.add_argument('--presets',
                    default=os.path.join(_HERE, '..', 'resources',
                                         'journal_presets.json'))
    ap.add_argument('--render-only', action='store_true',
                    help='internal: used by check_consistency.py')
    args = ap.parse_args()

    with open(args.spec, encoding='utf-8') as f:
        spec = json.load(f)
    with open(args.presets, encoding='utf-8') as f:
        presets = json.load(f)
    profile = presets.get(args.profile) or presets['generic_1col']

    data_path = os.path.join(args.snapshot, spec['data_file'])
    if not os.path.isfile(data_path):
        raise SpecError('data_file %r not found in snapshot dir'
                        % spec['data_file'])
    data_sha = sha256_of(data_path)
    declared = (spec.get('source') or {}).get('sha256')
    if declared and declared != data_sha:
        raise SpecError('data drift: snapshot sha256 %s != spec.source.sha256 %s'
                        % (data_sha[:12], declared[:12]))

    rows = load_table(data_path)
    validate(spec, rows)

    xcol, ycol = spec['x']['column'], spec['y']['column']
    cat_col = spec.get('category_column')
    err_col = spec.get('yerr_column')
    dropped = []
    clean = []
    for i, r in enumerate(rows, start=2):
        yv = to_float(r.get(ycol))
        if yv is None:
            dropped.append({'row': i, 'reason': 'non-numeric y',
                            'raw': r.get(ycol)})
            continue
        rec = {'x': (r.get(xcol) or '').strip(), 'y': yv}
        rec['xv'] = to_float(r.get(xcol))
        rec['cat'] = (r.get(cat_col) or '').strip() if cat_col else ''
        if cat_col and not rec['cat']:
            na = spec.get('na_label')
            if na:
                rec['cat'] = na
            else:
                dropped.append({'row': i, 'reason': 'missing category'})
                continue
        rec['yerr'] = to_float(r.get(err_col)) if err_col else None
        clean.append(rec)
    if not clean:
        raise SpecError('no usable rows after cleaning')

    categories = unique_in_order([r['cat'] for r in clean]) if cat_col else ['']
    palette = spec.get('palette') or DEFAULT_PALETTE
    if len(palette) < len(categories):
        raise SpecError('palette has %d colors but data has %d categories'
                        % (len(palette), len(categories)))
    legend_map = [{'category': c, 'color': palette[i],
                   'marker': MARKERS[i % len(MARKERS)]}
                  for i, c in enumerate(categories)]
    color_of = {m['category']: m['color'] for m in legend_map}
    marker_of = {m['category']: m['marker'] for m in legend_map}

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42,
        'font.family': 'sans-serif',
        'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
        'font.size': profile['font_pt'],
        'axes.linewidth': profile['axis_lw_pt'],
        'lines.linewidth': profile['linewidth_pt'],
        'xtick.labelsize': profile['font_pt'],
        'ytick.labelsize': profile['font_pt'],
        'axes.labelsize': profile['font_pt'],
        'axes.titlesize': profile['title_pt'],
        'legend.fontsize': profile['font_pt'],
        'figure.dpi': 96,
        'svg.hashsalt': 'data-legend-bind-v1',
    })
    w_in = profile['width_mm'] / 25.4
    h_in = profile['height_mm'] / 25.4
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ctype = spec['chart_type']

    if ctype in ('bar', 'grouped_bar', 'stacked_bar'):
        xs = unique_in_order([r['x'] for r in clean])
        xpos = list(range(len(xs)))
        if ctype == 'bar' and not cat_col:
            ax.bar(xpos, [next(r['y'] for r in clean if r['x'] == x)
                          for x in xs], color=palette[0])
        else:
            ncat = len(categories)
            width = 0.8 / ncat if ctype == 'grouped_bar' else 0.8
            for ci, cat in enumerate(categories):
                vals, errs, pos = [], [], []
                bottoms = [0.0] * len(xs)
                for xi, x in enumerate(xs):
                    hit = [r for r in clean if r['x'] == x and r['cat'] == cat]
                    vals.append(hit[0]['y'] if hit else 0.0)
                    errs.append(hit[0]['yerr'] if hit and
                                hit[0]['yerr'] is not None else None)
                    pos.append(xi + (ci - (ncat - 1) / 2.0) * width
                               if ctype == 'grouped_bar' else xi)
                kw = {}
                if ctype == 'stacked_bar':
                    for ci2 in range(ci):
                        prev = categories[ci2]
                        for xi, x in enumerate(xs):
                            hit = [r for r in clean
                                   if r['x'] == x and r['cat'] == prev]
                            bottoms[xi] += hit[0]['y'] if hit else 0.0
                    kw['bottom'] = bottoms
                has_err = any(e is not None for e in errs)
                if has_err:
                    kw['yerr'] = [e or 0.0 for e in errs]
                    kw['capsize'] = 2
                    kw['error_kw'] = {'lw': profile['linewidth_pt']}
                ax.bar(pos, vals, width=width, color=color_of[cat],
                       label=cat, **kw)
        ax.set_xticks(xpos)
        ax.set_xticklabels(xs)
    elif ctype == 'line':
        for cat in categories:
            sub = [r for r in clean if r['cat'] == cat]
            if all(r['xv'] is not None for r in sub):
                sub.sort(key=lambda r: r['xv'])
                ax.plot([r['xv'] for r in sub], [r['y'] for r in sub],
                        marker=marker_of[cat], color=color_of[cat],
                        label=cat or None)
            else:
                xs = unique_in_order([r['x'] for r in sub])
                ax.plot(xs, [next(r['y'] for r in sub if r['x'] == x)
                             for x in xs],
                        marker=marker_of[cat], color=color_of[cat],
                        label=cat or None)
    elif ctype == 'scatter':
        for cat in categories:
            sub = [r for r in clean if r['cat'] == cat]
            if not all(r['xv'] is not None for r in sub):
                raise SpecError('scatter requires numeric x column')
            ax.scatter([r['xv'] for r in sub], [r['y'] for r in sub],
                       marker=marker_of[cat], color=color_of[cat],
                       label=cat or None, s=18)

    ax.set_xlabel(axis_text(spec['x']))
    ax.set_ylabel(axis_text(spec['y']))
    if spec.get('title'):
        ax.set_title(spec['title'])
    if cat_col:
        ax.legend(title=spec.get('legend_title'), frameon=False)
    ax.spines[['top', 'right']].set_visible(False)
    fig.tight_layout()

    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.join(args.outdir, args.basename)
    exports, failures = [], []
    for ext, kw in (('svg', {}), ('pdf', {}),
                    ('png', {'dpi': profile['dpi']}),
                    ('tiff', {'dpi': profile['dpi'], 'pil_kwargs':
                              {'compression': 'tiff_lzw'}})):
        path = base + '.' + ext
        try:
            fig.savefig(path, **kw)
            exports.append({'format': ext, 'path': path,
                            'bytes': os.path.getsize(path)})
        except Exception as exc:
            failures.append({'format': ext, 'error': str(exc)[:300]})
    plt.close(fig)

    with open(base + '.legend_map.json', 'w', encoding='utf-8') as f:
        json.dump({'data_file': spec['data_file'], 'data_sha256': data_sha,
                   'category_column': cat_col, 'mapping': legend_map},
                  f, ensure_ascii=False, indent=2)
    log = {'status': 'ok' if exports else 'failed',
           'spec': os.path.abspath(args.spec), 'data_file': spec['data_file'],
           'data_sha256': data_sha, 'rows_total': len(rows),
           'rows_used': len(clean), 'rows_dropped': dropped,
           'categories': categories, 'exports': exports,
           'export_failures': failures,
           'profile': dict(profile, name=args.profile)}
    with open(base + '.render_log.json', 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': log['status'],
                      'exports': [e['format'] for e in exports],
                      'categories': categories,
                      'rows_used': len(clean),
                      'rows_dropped': len(dropped)}, ensure_ascii=False))
    sys.exit(0 if exports else 1)


if __name__ == '__main__':
    try:
        main()
    except SpecError as exc:
        print('SPEC ERROR: %s' % exc, file=sys.stderr)
        sys.exit(1)
