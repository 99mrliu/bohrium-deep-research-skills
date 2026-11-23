#!/usr/bin/env python3
"""SYNTHETIC EXAMPLE — toy case + full redraw-proof pipeline.

Illustrative miniature, NOT an official case and NOT a pre-computed
answer. It fabricates a grouped-bar figure (two series, error bars), then
exercises the real scripts:

  to_spec.py -> replot.py -> overlay_diff.py -> make_result.py

plus a negative control (a spec with a wrong bar value that the diff must
reject).

Usage:
  python examples/make_synthetic_case.py [workdir]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, 'scripts')

TRUE = {  # the synthetic "ground truth" the figure is plotted from
    'categories': ['ctrl', 'low', 'mid', 'high'],
    'WT': [100.0, 82.0, 55.0, 21.0],
    'KO': [100.0, 91.0, 74.0, 48.0],
    'WT_err': [4.0, 5.0, 6.0, 3.5],
    'KO_err': [4.0, 4.5, 5.5, 4.0],
}


def img_box(fig, bbox, dpi):
    fig.canvas.draw()
    h = fig.get_figheight() * dpi
    return [int(round(bbox.x0)), int(round(h - bbox.y1)),
            int(round(bbox.x1)), int(round(h - bbox.y0))]


def plot_area(fig, ax, dpi):
    return img_box(fig, ax.get_window_extent(), dpi)


def gen_case(root):
    inp = os.path.join(root, 'input')
    work = os.path.join(root, 'work')
    out = os.path.join(root, 'output')
    for d in (inp, work, out):
        os.makedirs(d, exist_ok=True)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    dpi = 150
    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=dpi)
    idx = np.arange(4)
    ax.bar(idx - 0.2, TRUE['WT'], width=0.4, yerr=TRUE['WT_err'],
           color='#0072B2', label='WT', capsize=3, edgecolor='black',
           linewidth=0.4)
    ax.bar(idx + 0.2, TRUE['KO'], width=0.4, yerr=TRUE['KO_err'],
           color='#D55E00', label='KO', capsize=3, edgecolor='black',
           linewidth=0.4)
    ax.set_xticks(idx)
    ax.set_xticklabels(TRUE['categories'])
    ax.set_xlabel('treatment')
    ax.set_ylabel('viability (%)')
    ax.set_ylim(0, 120)
    legend = ax.legend()
    fig.tight_layout()
    legend_box = img_box(fig, legend.get_window_extent(), dpi)
    fig_path = os.path.join(inp, 'fig_viability.png')
    fig.savefig(fig_path, dpi=dpi)
    box = plot_area(fig, ax, dpi)
    plt.close(fig)

    case = {
        'case_id': 'SYN-REDRAW-EXAMPLE',
        'kind': 'synthetic-illustrative-example',
        'output_contract': {
            'answer': 'free text answering the task question with units',
            'extracted_values': 'list of {series,category,value,unit,err}',
            'verification': 'reconstruction diff summary'
        }
    }
    with open(os.path.join(inp, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(case, f, indent=2)
    with open(os.path.join(inp, 'task.md'), 'w', encoding='utf-8') as f:
        f.write('Extract each bar height with its error bar (unit %, error '
                'semantics from the caption: SD), and state at which '
                'treatment the WT/KO difference is largest.\n')
    with open(os.path.join(inp, 'caption.txt'), 'w', encoding='utf-8') as f:
        f.write('Figure 1. Cell viability after treatment. Bars show '
                'mean +/- SD, n = 5.\n')
    return inp, work, out, fig_path, box, legend_box


def run(cmd, expect_rc=0):
    print('$', ' '.join(os.path.basename(c) if c.endswith('.py') else c
                        for c in cmd))
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != expect_rc:
        print(r.stderr.strip())
        raise SystemExit('step failed (rc=%d): %s' % (r.returncode, cmd[0]))
    if r.stderr.strip():
        print(r.stderr.strip())
    return r


def make_spec(read_err):
    """Agent-authored spec: bar heights read from the zoomed figure with
    small reading errors; error_semantics from the caption (SD)."""
    def noisy(vals):
        return [round(v + read_err, 1) for v in vals]
    return {
        'figure': {'title': None, 'width_in': 5.0, 'height_in': 3.5},
        'axes': {
            'x': {'label': 'treatment', 'unit': None, 'type': 'linear',
                  'range': [-0.6, 3.6]},
            'y': {'label': 'viability (%)', 'unit': '%', 'type': 'linear',
                  'range': [0, 120]},
        },
        'series': [
            {'name': 'WT', 'kind': 'bar', 'color': '#0072B2',
             'categories': TRUE['categories'], 'values': noisy(TRUE['WT']),
             'errors': TRUE['WT_err'], 'error_semantics': 'SD'},
            {'name': 'KO', 'kind': 'bar', 'color': '#D55E00',
             'categories': TRUE['categories'], 'values': noisy(TRUE['KO']),
             'errors': TRUE['KO_err'], 'error_semantics': 'SD'},
        ],
        'annotations': [{'text': 'n=5', 'x': 0, 'y': 110}],
    }


def pipeline(inp, work, out, fig_path, box, spec, tag,
             exclude=()):
    spec_path = os.path.join(work, 'figure_spec.json')
    with open(spec_path, 'w') as f:
        json.dump(spec, f, indent=2)
    run([os.path.join(SCRIPTS, 'to_spec.py'), '--spec', spec_path,
         '--out', os.path.join(work, 'spec_canonical.json')])
    run([os.path.join(SCRIPTS, 'replot.py'), '--spec',
         os.path.join(work, 'spec_canonical.json'),
         '--out', os.path.join(out, 'reconstruction')])
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS, 'overlay_diff.py'),
                        '--original', fig_path,
                        '--orig-plot-area', ','.join(map(str, box)),
                        '--recon', os.path.join(out, 'reconstruction.png'),
                        '--meta', os.path.join(out, 'reconstruction.meta.json'),
                        '--spec', os.path.join(work, 'spec_canonical.json'),
                        ] + sum((['--exclude-box', b] for b in exclude), [])
                        + ['--out', os.path.join(out, 'verify')],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())
    mpath = os.path.join(out, 'verify.metrics.json')
    return json.load(open(mpath)) if os.path.exists(mpath) else None


def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
        os.path.abspath('synthetic_run_b')
    inp, work, out, fig_path, box, legend_box = gen_case(root)
    print('[example] synthetic figure written:', fig_path,
          'plot_area', box)

    # --- positive run: honest readings (±0.8% FS) -------------------------
    # legend box is measured by the agent and excluded: legends are text,
    # not data
    excl = [','.join(map(str, legend_box))]
    metrics = pipeline(inp, work, out, fig_path, box, make_spec(0.8),
                       'good', exclude=excl)
    assert metrics, 'metrics missing'
    print('[example] positive verdict:', metrics['verdict'],
          'recall', metrics['ink_recall'])
    assert metrics['verdict'] in ('verified', 'plausible')

    cats = TRUE['categories']
    fragment = {
        'answer': 'Largest WT/KO gap at "high": WT 21.8% vs KO 48.8% '
                  '(read from figure, SD error bars per caption).',
        'extracted_values': [
            {'series': 'WT', 'category': c, 'value': round(v + 0.8, 1),
             'unit': '%', 'err': e}
            for c, v, e in zip(cats, TRUE['WT'], TRUE['WT_err'])] + [
            {'series': 'KO', 'category': c, 'value': round(v + 0.8, 1),
             'unit': '%', 'err': e}
            for c, v, e in zip(cats, TRUE['KO'], TRUE['KO_err'])],
    }
    with open(os.path.join(work, 'result_fragment.json'), 'w') as f:
        json.dump(fragment, f, indent=2)
    run([os.path.join(SCRIPTS, 'make_result.py'),
         '--case', os.path.join(inp, 'case.json'),
         '--fragment', os.path.join(work, 'result_fragment.json'),
         '--metrics', os.path.join(out, 'verify.metrics.json'),
         '--out', os.path.join(out, 'result.json'), '--status', 'success'])

    # --- negative control 1: a whole series dropped (the classic miss) ----
    bad = make_spec(0.8)
    bad['series'] = bad['series'][:1]  # KO series never read
    neg_work = os.path.join(work, 'neg')
    neg_out = os.path.join(out, 'neg')
    os.makedirs(neg_work, exist_ok=True)
    os.makedirs(neg_out, exist_ok=True)
    print('--- negative control 1: KO series dropped (expect rejected)')
    metrics = pipeline(neg_work, neg_work, neg_out, fig_path, box, bad, 'bad')
    assert metrics and metrics['verdict'] == 'rejected', \
        'dropped series must be rejected, got %s' % metrics
    print('[example] negative control 1 verdict:', metrics['verdict'],
          'recall', metrics['ink_recall'])
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS, 'make_result.py'),
                        '--case', os.path.join(inp, 'case.json'),
                        '--fragment', os.path.join(work, 'result_fragment.json'),
                        '--metrics', os.path.join(neg_out, 'verify.metrics.json'),
                        '--out', os.path.join(neg_out, 'result.json'),
                        '--status', 'success'],
                       capture_output=True, text=True)
    neg_result = json.load(open(os.path.join(neg_out, 'result.json')))
    print('[example] make_result on rejected metrics ->',
          neg_result['status'])
    assert neg_result['status'] != 'success'

    # --- negative control 2: one bar misread by 30% (edge sensitivity) ----
    bad2 = make_spec(0.8)
    bad2['series'][0]['values'][3] = TRUE['WT'][3] * 1.3 + 8
    neg2_work = os.path.join(work, 'neg2')
    neg2_out = os.path.join(out, 'neg2')
    os.makedirs(neg2_work, exist_ok=True)
    os.makedirs(neg2_out, exist_ok=True)
    print('--- negative control 2: WT high bar +30% (edge_recall must drop)')
    m2 = pipeline(neg2_work, neg2_work, neg2_out, fig_path, box, bad2, 'bad2')
    print('[example] negative control 2: fill recall %.4f, edge recall %.4f'
          % (m2['ink_recall'], m2['edge_recall']))
    assert m2['edge_recall'] < 0.98, \
        'edge metric should be sensitive to the misread bar'
    print('[example] DONE. Inspect %s' % os.path.join(out, 'verify.diff.png'))


if __name__ == '__main__':
    main()
