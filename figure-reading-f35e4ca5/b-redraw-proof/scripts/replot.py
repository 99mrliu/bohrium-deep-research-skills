#!/usr/bin/env python3
"""Deterministically re-render a validated figure spec (matplotlib).

The reconstruction is the skill's proof artifact: if the readings in the
spec are right, the redrawn figure must match the original under
overlay_diff.py. Rendered outputs:

  <out>.png  300 dpi raster for the overlay diff and visual inspection
  <out>.pdf  vector export (editable deliverable)
  <out>.svg  vector export with real text kept as text
  <out>.meta.json  pixel geometry of the plot area (needed by overlay_diff)

Axis titles, units, scales, series order, colors, markers, error bars and
annotations all come from the spec — nothing is auto-invented. matplotlib
absence is reported honestly (exit 3), never faked.

Usage:
  python replot.py --spec work/spec_canonical.json --out /app/output/reconstruction
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--out', required=True, help='output prefix')
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding='utf-8'))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError as e:
        print(json.dumps({'rendered': False,
                          'reason': 'matplotlib unavailable: %s' % e}))
        raise SystemExit(3)

    matplotlib.rcParams.update({
        'svg.fonttype': 'none',          # keep SVG text editable
        'pdf.fonttype': 42,
        'axes.unicode_minus': False,
        'font.size': 10,
    })
    fig_geom = spec.get('figure') or {}
    w = float(fig_geom.get('width_in', 5.0))
    h = float(fig_geom.get('height_in', 3.5))
    dpi = 300
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)

    axes = spec['axes']
    xlab = axes['x'].get('label', '')
    ylab = axes['y'].get('label', '')
    if axes['x'].get('unit') and '(%s)' % axes['x']['unit'] not in xlab:
        xlab = '%s (%s)' % (xlab, axes['x']['unit'])
    if axes['y'].get('unit') and '(%s)' % axes['y']['unit'] not in ylab:
        ylab = '%s (%s)' % (ylab, axes['y']['unit'])
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    if axes['x'].get('type') == 'log':
        ax.set_xscale('log')
    if axes['y'].get('type') == 'log':
        ax.set_yscale('log')
    if axes['x'].get('range'):
        ax.set_xlim(*axes['x']['range'])
    if axes['y'].get('range'):
        ax.set_ylim(*axes['y']['range'])
    if fig_geom.get('title'):
        ax.set_title(fig_geom['title'])

    bar_offset = {}
    n_bar = sum(1 for s in spec['series'] if (s.get('kind') or 'line') == 'bar')
    for si, s in enumerate(spec['series']):
        kind = s.get('kind') or 'line'
        color = s.get('color') or None
        name = s.get('name')
        if kind in ('line', 'scatter'):
            xs = [p[0] for p in s['points']]
            ys = [p[1] for p in s['points']]
            marker = None if s.get('marker') in (None, 'none') else \
                s.get('marker', 'o')
            if kind == 'line':
                ax.plot(xs, ys, marker=marker or 'o', color=color,
                        label=name, linewidth=1.5, markersize=4)
            else:
                ax.scatter(xs, ys, marker=marker or 'o', color=color,
                           label=name, s=18)
        elif kind == 'bar':
            import numpy as _np
            cats = s['categories']
            vals = s['values']
            errs = s.get('errors')
            idx = _np.arange(len(cats))
            width = 0.8 / max(n_bar, 1)
            off = (bar_offset.setdefault('i', 0) - (n_bar - 1) / 2.0) * width
            bar_offset['i'] += 1
            ax.bar(idx + off, vals, width=width, yerr=errs, color=color,
                   label=name, capsize=3, edgecolor='black', linewidth=0.4)
            ax.set_xticks(idx)
            ax.set_xticklabels(cats)

    for ann in spec.get('annotations') or []:
        ax.annotate(ann['text'], xy=(ann.get('x'), ann.get('y')),
                    fontsize=8)

    if len(spec['series']) > 1 or spec['series'][0].get('name'):
        ax.legend(framealpha=0.9, fontsize=8)
    fig.tight_layout()

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    png = args.out + '.png'
    pdf = args.out + '.pdf'
    svg = args.out + '.svg'
    fig.savefig(png, dpi=dpi)
    fig.savefig(pdf)
    fig.savefig(svg)

    # plot-area pixel geometry for overlay registration (top-left origin)
    fig.canvas.draw()
    bbox = ax.get_window_extent()  # display px, bottom-left origin
    meta = {
        'image_width_px': int(round(fig.get_figwidth() * dpi)),
        'image_height_px': int(round(fig.get_figheight() * dpi)),
        'plot_area_px': [int(round(bbox.x0)),
                         int(round(fig.get_figheight() * dpi - bbox.y1)),
                         int(round(bbox.x1)),
                         int(round(fig.get_figheight() * dpi - bbox.y0))],
        'dpi': dpi,
    }
    plt.close(fig)
    meta_path = args.out + '.meta.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    print(json.dumps({'rendered': True, 'png': png, 'pdf': pdf, 'svg': svg,
                      'meta': meta_path, 'plot_area_px': meta['plot_area_px']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
