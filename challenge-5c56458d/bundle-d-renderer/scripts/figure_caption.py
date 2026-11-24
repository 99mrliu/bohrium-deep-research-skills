#!/usr/bin/env python3
"""Generate an audit-grade figure caption from the figure spec + evidence.

A chart in a scientific deliverable must say: what is shown, how many rows
stand behind it, the units, the data source (db hash / query tag) and any
caveat. This script composes that caption from the figure.json written by
render_chart.py and optional run metadata, so the text cannot drift from
what was actually rendered. Standard library only.

Usage:
  python figure_caption.py --figure /app/work/fig1.figure.json \
      [--run /app/work/q1.run.json] [--caveat "DRIFT: sepal_width rescaled"] \
      --out /app/work/fig1.caption.md
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--figure', required=True)
    ap.add_argument('--run')
    ap.add_argument('--caveat', action='append', default=[])
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    spec = json.load(open(args.figure, encoding='utf-8'))
    lines = ['**Figure.** ' + (spec.get('title') or spec['type'])]
    lines.append('Chart type: %s; source table: `%s`.' % (spec['type'],
                                                         spec['csv']))
    if spec.get('bars'):
        lines.append('Bars shown: %d (y-axis starts at zero).' % spec['bars'])
    if spec.get('n'):
        lines.append('Underlying observations: n = %d.' % spec['n'])
    if spec.get('groups'):
        lines.append('Groups: %s.' % ', '.join(map(str, spec['groups'])))
    if args.run and os.path.exists(args.run):
        run = json.load(open(args.run, encoding='utf-8'))
        if run.get('db_sha256'):
            lines.append('Source database sha256: `%s`.' % run['db_sha256'])
        if run.get('sql'):
            lines.append('Produced by query: `%s`.' % run['sql'][:300])
        if run.get('row_count') is not None:
            lines.append('Query returned %d rows.' % run['row_count'])
    for c in args.caveat:
        lines.append('Caveat: %s' % c)
    lines.append('Rendered deterministically by %s; regenerate with the '
                 'spec in `%s`.' % (spec.get('renderer', 'render_chart.py'),
                                    os.path.basename(args.figure)))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    open(args.out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({'caption': args.out}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
