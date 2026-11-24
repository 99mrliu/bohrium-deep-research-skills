#!/usr/bin/env python3
"""Recommend a chart type for a result table, with veto-able rationale.

Profiles the CSV (column types, cardinalities, row count) and applies the
rules in references/chart_rules.md. The output is a recommendation with the
fired rule recorded — the analyst may override, but the default is never a
silent guess. Standard library only.

Usage:
  python chart_select.py --csv /app/work/q1.csv --question "compare groups" \
      --out /app/work/chart_recommendation.json
"""
import argparse
import csv
import json
import os
import sys


def profile_csv(path):
    with open(path, encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, data = rows[0], rows[1:]
    cols = []
    for i, name in enumerate(header):
        vals = [r[i] for r in data if i < len(r) and r[i] != '']
        numeric = False
        if vals:
            try:
                [float(v) for v in vals]
                numeric = True
            except ValueError:
                numeric = False
        cols.append({'name': name, 'numeric': numeric,
                     'distinct': len(set(vals)), 'non_null': len(vals)})
    return header, data, cols


def recommend(cols, n_rows, question):
    q = (question or '').lower()
    nums = [c for c in cols if c['numeric']]
    cats = [c for c in cols if not c['numeric']]
    recs = []
    if any(w in q for w in ('distribution', '分布', 'histogram')) and nums:
        recs.append({'chart': 'histogram', 'rule': 'R2 distribution',
                     'x': nums[0]['name'],
                     'why': 'question asks about the distribution of a numeric column'})
    if any(w in q for w in ('correlation', 'relationship', '相关', '关系',
                            'scatter')) and len(nums) >= 2:
        recs.append({'chart': 'scatter', 'rule': 'R3 relationship',
                     'x': nums[0]['name'], 'y': nums[1]['name'],
                     'why': 'two numeric measures; question asks relationship'})
    if any(w in q for w in ('trend', 'time', 'over time', '趋势', '随时间')) \
            and len(nums) >= 2:
        recs.append({'chart': 'line', 'rule': 'R4 trend',
                     'x': cols[0]['name'], 'y': nums[-1]['name'],
                     'why': 'ordered x (time/age) against a measure'})
    if cats and nums:
        cat, num = cats[0], nums[0]
        if cat['distinct'] <= 25 and n_rows <= 200:
            recs.append({'chart': 'bar', 'rule': 'R1 categorical compare',
                         'x': cat['name'], 'y': num['name'],
                         'why': '%d-level category vs numeric aggregate; bars '
                                'start at zero' % cat['distinct']})
        else:
            recs.append({'chart': 'table', 'rule': 'R6 too many levels',
                         'why': 'category has %d levels; a table beats a chart'
                                % cat['distinct']})
    if len(cats) >= 2 and nums:
        recs.append({'chart': 'grouped_bar', 'rule': 'R5 two categories',
                     'x': cats[0]['name'], 'group': cats[1]['name'],
                     'y': nums[0]['name'],
                     'why': 'two categorical dimensions with a numeric aggregate'})
    if not recs and len(nums) == 1:
        recs.append({'chart': 'histogram', 'rule': 'R2 fallback',
                     'x': nums[0]['name'],
                     'why': 'single numeric column; show its distribution'})
    if not recs:
        recs.append({'chart': 'table', 'rule': 'R6 fallback',
                     'why': 'no chart rule fired; deliver a formatted table'})
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--csv', required=True)
    ap.add_argument('--question', default='')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    header, data, cols = profile_csv(args.csv)
    recs = recommend(cols, len(data), args.question)
    out = {'csv': args.csv, 'rows': len(data), 'columns': cols,
           'recommendations': recs, 'primary': recs[0],
           'note': ('recommendation only; the fired rule is recorded so the '
                    'choice can be reviewed or vetoed')}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(out, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'primary': recs[0], 'alternatives': len(recs) - 1},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
