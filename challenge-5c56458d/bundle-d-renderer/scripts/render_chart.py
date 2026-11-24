#!/usr/bin/env python3
"""Deterministically render a result CSV to a publication-style PNG.

Same inputs -> byte-stable figure spec and visually identical PNG: headless
Agg backend, fixed rcParams from references/style_guide.md, no randomness,
no timestamps inside the figure. A machine-readable figure spec
(<out>.figure.json) is always written next to the PNG so the figure can be
regenerated and audited. Requires matplotlib; if it is missing the script
says so honestly instead of drawing with unverified fallbacks.

Usage:
  python render_chart.py --csv q1.csv --type bar --x group_id --y mean_metric \
      --y-unit MPa --title "Mean metric by group" --out /app/work/fig1
Writes: <out>.png, <out>.figure.json
"""
import argparse
import csv
import json
import os
import sys


def load_columns(path):
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, data = rows[0], rows[1:]
    idx = {name: i for i, name in enumerate(header)}
    return idx, data


def col(idx, data, name, numeric=True):
    vals = [(data_row[idx[name]] if idx[name] < len(data_row) else '')
            for data_row in data]
    vals = [v for v in vals if v != '']
    if numeric:
        return [float(v) for v in vals]
    return vals


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--csv', required=True)
    ap.add_argument('--type', required=True,
                    choices=['bar', 'grouped_bar', 'histogram', 'scatter',
                             'line', 'box'])
    ap.add_argument('--x')
    ap.add_argument('--y')
    ap.add_argument('--group')
    ap.add_argument('--x-label')
    ap.add_argument('--y-label')
    ap.add_argument('--x-unit')
    ap.add_argument('--y-unit')
    ap.add_argument('--title', default='')
    ap.add_argument('--out', required=True, help='output path without extension')
    args = ap.parse_args()
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        raise SystemExit('matplotlib not available in this runtime; figure '
                         'cannot be rendered — report this honestly instead '
                         'of substituting an unverified renderer')
    plt.rcParams.update({
        'figure.dpi': 200, 'savefig.dpi': 200, 'figure.figsize': (6.4, 4.0),
        'font.size': 10, 'axes.titlesize': 11, 'axes.labelsize': 10,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.grid': True, 'grid.alpha': 0.3, 'grid.linewidth': 0.5,
        'axes.axisbelow': True, 'legend.frameon': False,
    })
    idx, data = load_columns(args.csv)

    def lab(name, unit, override):
        if override:
            return override
        return name + ((' (%s)' % unit) if unit else '')

    fig, ax = plt.subplots()
    spec = {'csv': args.csv, 'type': args.type, 'title': args.title,
            'renderer': 'matplotlib ' + matplotlib.__version__ + ' (Agg)',
            'style': 'references/style_guide.md v1'}
    if args.type in ('bar', 'line', 'scatter'):
        if args.type == 'bar':
            cats = col(idx, data, args.x, numeric=False)
            ys = col(idx, data, args.y)
            ax.bar(range(len(cats)), ys, color='#4C72B0', width=0.7)
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels(cats, rotation=30, ha='right')
            ax.set_ylim(bottom=0)
            spec['bars'] = len(cats)
        elif args.type == 'line':
            xs = col(idx, data, args.x)
            ys = col(idx, data, args.y)
            ax.plot(xs, ys, marker='o', ms=3.5, lw=1.2, color='#4C72B0')
        else:
            xs = col(idx, data, args.x)
            ys = col(idx, data, args.y)
            ax.scatter(xs, ys, s=18, color='#4C72B0', alpha=0.8,
                       edgecolors='none')
        ax.set_xlabel(lab(args.x, args.x_unit, args.x_label))
        ax.set_ylabel(lab(args.y, args.y_unit, args.y_label))
        spec.update(x=args.x, y=args.y)
    elif args.type == 'grouped_bar':
        cats = col(idx, data, args.x, numeric=False)
        groups = col(idx, data, args.group, numeric=False)
        ys = col(idx, data, args.y)
        order = sorted(set(groups))
        corder = sorted(set(cats))
        import itertools
        width = 0.8 / len(order)
        for gi, g in enumerate(order):
            vals = [y for c, gg, y in zip(cats, groups, ys) if gg == g]
            cc = [c for c, gg, y in zip(cats, groups, ys) if gg == g]
            pos = [corder.index(c) + gi * width for c in cc]
            ax.bar(pos, vals, width=width, label=str(g))
        ax.set_xticks([i + 0.4 - width / 2 for i in range(len(corder))])
        ax.set_xticklabels(corder, rotation=30, ha='right')
        ax.set_ylim(bottom=0)
        ax.legend(title=args.group)
        ax.set_xlabel(lab(args.x, args.x_unit, args.x_label))
        ax.set_ylabel(lab(args.y, args.y_unit, args.y_label))
        spec.update(x=args.x, y=args.y, group=args.group, groups=order)
    elif args.type == 'histogram':
        vals = col(idx, data, args.x)
        bins = min(30, max(8, int(len(vals) ** 0.5)))
        ax.hist(vals, bins=bins, color='#4C72B0', edgecolor='white', lw=0.5)
        ax.set_xlabel(lab(args.x, args.x_unit, args.x_label))
        ax.set_ylabel('count')
        spec.update(x=args.x, bins=bins, n=len(vals))
    elif args.type == 'box':
        cats = col(idx, data, args.x, numeric=False)
        ys = col(idx, data, args.y)
        order = sorted(set(cats))
        series = [[y for c, y in zip(cats, ys) if c == g] for g in order]
        ax.boxplot(series, tick_labels=order, showfliers=True,
                   medianprops={'color': '#C44E52'})
        ax.set_xlabel(lab(args.x, args.x_unit, args.x_label))
        ax.set_ylabel(lab(args.y, args.y_unit, args.y_label))
        spec.update(x=args.x, y=args.y, groups=order)
    if args.title:
        ax.set_title(args.title)
    fig.tight_layout()
    png = args.out + '.png'
    fig.savefig(png)
    spec['png'] = png
    spec['png_bytes'] = os.path.getsize(png)
    json.dump(spec, open(args.out + '.figure.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'png': png, 'bytes': spec['png_bytes'],
                      'spec': args.out + '.figure.json'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
