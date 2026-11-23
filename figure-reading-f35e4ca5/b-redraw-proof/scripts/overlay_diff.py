#!/usr/bin/env python3
"""Overlay-diff the original figure against the reconstruction.

This is the acceptance test of the whole skill: the reconstruction is
affine-registered onto the original via the two plot-area boxes, ink masks
are extracted inside the plot area, and coverage is measured both ways:

  recall    = fraction of ORIGINAL ink within --tol-px of reconstruction ink
              (missed curves, wrong values, dropped markers drive this down)
  precision = fraction of RECONSTRUCTION ink supported by original ink
              (invented data drives this down)

Outputs:
  <out>.diff.png   original in gray; covered ink green, missed original ink
                   red, unsupported reconstruction ink blue
  <out>.metrics.json  recall/precision, per-series recall (when spec colors
                   are given), worst grid cells, verdict thresholds

Usage:
  python overlay_diff.py --original fig.png --orig-plot-area 60,15,620,470 \
      --recon reconstruction.png --meta reconstruction.meta.json \
      [--spec spec_canonical.json] [--tol-px 4] --out /app/output/verify
"""
import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(json.dumps({'diff': False,
                      'reason': 'numpy/PIL unavailable: %s' % e}))
    raise SystemExit(3)


def ink_mask(arr):
    """Non-background ink: distance from near-white background."""
    rgb = arr[..., :3].astype(np.int16)
    return (255 - rgb.max(axis=2) > 40) | (rgb.max(axis=2) - rgb.min(axis=2) > 40)


def dilate(mask, px):
    out = mask.copy()
    m = mask
    for _ in range(px):
        grown = m.copy()
        grown[1:, :] |= m[:-1, :]
        grown[:-1, :] |= m[1:, :]
        grown[:, 1:] |= m[:, :-1]
        grown[:, :-1] |= m[:, 1:]
        m = grown
    return m


def crop(arr, box):
    l, t, r, b = box
    return arr[t:b, l:r]


def warp_recon(recon_arr, meta, orig_box):
    """Affine-map the reconstruction's plot area onto the original's box."""
    rl, rt, rr, rb = meta['plot_area_px']
    ol, ot, orr, ob = orig_box
    rw, rh = rr - rl, rb - rt
    ow, oh = orr - ol, ob - ot
    plot = Image.fromarray(recon_arr[rt:rb, rl:rr, :3])
    return np.asarray(plot.resize((ow, oh), Image.BILINEAR))


def cell_map(miss_and_ink, shape, nx=8, ny=6):
    """Recall per grid cell of the original plot area.

    miss_and_ink = (missed_mask, orig_ink_mask); only cells with >20 ink
    pixels are ranked, and the 5 worst are returned."""
    missed, om = miss_and_ink
    h, w = shape
    cells = []
    for iy in range(ny):
        for ix in range(nx):
            sl = np.s_[iy * h // ny:(iy + 1) * h // ny,
                       ix * w // nx:(ix + 1) * w // nx]
            ink = om[sl].sum()
            if ink > 20:
                rec = 1.0 - missed[sl].sum() / ink
                cells.append({'cell': [ix, iy], 'recall': round(float(rec), 3)})
    cells.sort(key=lambda c: c['recall'])
    return cells[:5]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--original', required=True)
    ap.add_argument('--orig-plot-area', required=True,
                    help='left,top,right,bottom in original image pixels')
    ap.add_argument('--recon', required=True)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--spec', default=None)
    ap.add_argument('--tol-px', type=int, default=4)
    ap.add_argument('--exclude-box', action='append', default=[],
                    help='original-image pixel box L,T,R,B to exclude from '
                         'data-ink verification (legend, in-plot text); '
                         'repeatable')
    ap.add_argument('--out', required=True, help='output prefix')
    args = ap.parse_args()

    orig_box = [int(v) for v in args.orig_plot_area.split(',')]
    meta = json.load(open(args.meta, encoding='utf-8'))
    orig = np.asarray(Image.open(args.original).convert('RGB'))
    recon = np.asarray(Image.open(args.recon).convert('RGB'))
    warped = warp_recon(recon, meta, orig_box)
    orig_plot = crop(orig, orig_box)

    om = ink_mask(orig_plot)
    rm = ink_mask(warped)
    excluded = []
    for spec_box in args.exclude_box:
        l, t, r, b = [int(v) for v in spec_box.split(',')]
        # pad to absorb anti-aliased fringes of the excluded element
        pad = 6
        l, t, r, b = l - pad, t - pad, r + pad, b + pad
        # convert original-image coords to plot-area-relative coords
        pl, pt = max(l - orig_box[0], 0), max(t - orig_box[1], 0)
        pr, pb = min(r - orig_box[0], om.shape[1]), min(b - orig_box[1],
                                                         om.shape[0])
        if pr > pl and pb > pt:
            om[pt:pb, pl:pr] = False
            rm[pt:pb, pl:pr] = False
            excluded.append([l, t, r, b])
    rm_d = dilate(rm, args.tol_px)
    om_d = dilate(om, args.tol_px)
    recall = float((om & rm_d).sum() / max(om.sum(), 1))
    precision = float((rm & om_d).sum() / max(rm.sum(), 1))

    # edge masks: ink pixels with at least one non-ink 4-neighbour. Filled
    # regions (bars) hide value errors inside their fill; edges expose them.
    def edge_mask(m):
        # interior = ink pixel whose 4-neighbours are ALL ink; edge = rest
        interior = np.ones_like(m)
        interior[1:, :] &= m[:-1, :]
        interior[:-1, :] &= m[1:, :]
        interior[:, 1:] &= m[:, :-1]
        interior[:, :-1] &= m[:, 1:]
        return m & ~interior
    om_e = edge_mask(om)
    rm_e = edge_mask(rm)
    rm_e_d = dilate(rm_e, args.tol_px)
    edge_recall = float((om_e & rm_e_d).sum() / max(om_e.sum(), 1))

    # per-series recall by spec color (when colors are declared)
    per_series = []
    if args.spec and os.path.exists(args.spec):
        spec = json.load(open(args.spec, encoding='utf-8'))
        for s in spec.get('series', []):
            color = s.get('color')
            if not color or not str(color).startswith('#'):
                continue
            c = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)])
            dist = np.abs(orig_plot[..., :3].astype(np.int16) - c).sum(axis=2)
            sm = (dist < 120) & om
            if sm.sum() < 30:
                continue
            per_series.append({'series': s.get('name'), 'color': color,
                               'ink_px': int(sm.sum()),
                               'recall': round(float((sm & rm_d).sum() /
                                                     sm.sum()), 4)})

    h, w = om.shape
    canvas = (orig_plot * 0.35 + 160).astype(np.uint8)
    covered = om & rm_d
    missed = om & ~rm_d
    extra = rm & ~om_d
    canvas[covered] = [0, 158, 115]
    canvas[missed] = [213, 94, 0]
    canvas[extra] = [0, 114, 178]

    worst = cell_map((missed, om), om.shape)
    worst_recall = worst[0]['recall'] if worst else 1.0
    verdict = ('verified' if recall >= 0.85 and precision >= 0.70
               and edge_recall >= 0.70 and worst_recall >= 0.50 else
               'plausible' if recall >= 0.60 and edge_recall >= 0.45
               and worst_recall >= 0.25 else
               'rejected')

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    diff_png = args.out + '.diff.png'
    Image.fromarray(canvas).save(diff_png)
    metrics = {
        'ink_recall': round(recall, 4),
        'ink_precision': round(precision, 4),
        'edge_recall': round(edge_recall, 4),
        'tol_px': args.tol_px,
        'per_series_recall': per_series,
        'worst_cells': worst,
        'worst_cell_recall': worst_recall,
        'excluded_boxes': excluded,
        'verdict': verdict,
        'verdict_rules': 'verified: recall>=0.85 & precision>=0.70 & '
                         'edge_recall>=0.70 & worst_cell_recall>=0.50; '
                         'plausible: recall>=0.60 & edge_recall>=0.45 & '
                         'worst_cell_recall>=0.25; else rejected. Edge '
                         'recall tracks region boundaries (bar tops, curve '
                         'shapes) that filled-area metrics hide; the '
                         'worst-cell gate catches locally dropped content '
                         '(a missing series hides inside global recall).',
        'diff_png': diff_png,
    }
    mpath = args.out + '.metrics.json'
    with open(mpath, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(json.dumps({'metrics': mpath, 'diff_png': diff_png,
                      'ink_recall': metrics['ink_recall'],
                      'ink_precision': metrics['ink_precision'],
                      'edge_recall': metrics['edge_recall'],
                      'verdict': verdict}, ensure_ascii=False))
    if verdict == 'rejected':
        print('REJECTED — the reconstruction does not cover the original '
              'ink; the readings in the spec are wrong somewhere. Inspect '
              'worst_cells and per_series_recall, fix the spec, re-render.',
              file=sys.stderr)


if __name__ == '__main__':
    main()
