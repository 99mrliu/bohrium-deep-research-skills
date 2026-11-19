#!/usr/bin/env python3
"""Study matrix: validated row intake for the comparison matrix. Stdlib only."""
import argparse
import json
import os

DESIGNS = {'rct', 'meta', 'cohort', 'review', 'opinion', 'n/a', ''}
DIRECTIONS = {'positive', 'negative', 'mixed', 'none'}


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def validate_row(row):
    errs = []
    if not row.get('study'):
        errs.append('study 必填')
    if row.get('design') not in DESIGNS:
        errs.append('design 必须是 rct/meta/cohort/review/opinion/n/a')
    if row.get('direction') not in DIRECTIONS:
        errs.append('direction 必须是 positive/negative/mixed/none')
    if not row.get('source'):
        errs.append('source 必填（DOI/URL/材料路径）——不允许无源行')
    return errs


def main():
    import sys
    # tolerate values starting with '-', e.g. "--magnitude -0.6%"
    argv = sys.argv[1:]
    fixed = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if (tok.startswith('--') and '=' not in tok and i + 1 < len(argv)
                and argv[i + 1].startswith('-')):
            fixed.append(tok + '=' + argv[i + 1])
            i += 2
        else:
            fixed.append(tok)
            i += 1
    sys.argv[1:] = fixed
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add')
    a.add_argument('--matrix', required=True)
    a.add_argument('--study', required=True)
    a.add_argument('--design', required=True)
    a.add_argument('--n', default=None)
    a.add_argument('--population', default='')
    a.add_argument('--topic', required=True)
    a.add_argument('--outcome', required=True)
    a.add_argument('--direction', required=True)
    a.add_argument('--magnitude', default=None)
    a.add_argument('--limits', default='')
    a.add_argument('--source', required=True)
    l = sub.add_parser('list')
    l.add_argument('--matrix', required=True)
    args = ap.parse_args()

    if args.cmd == 'list':
        m = load(args.matrix)
        for i, r in enumerate(m['rows'], 1):
            print(json.dumps({'row': i, **r}, ensure_ascii=False))
        return

    m = load(args.matrix)
    row = {'study': args.study, 'design': args.design, 'n': args.n,
           'population': args.population, 'topic': args.topic,
           'outcome': args.outcome, 'direction': args.direction,
           'magnitude': args.magnitude, 'limits': args.limits,
           'source': args.source}
    errs = validate_row(row)
    dup = [i for i, r in enumerate(m['rows'], 1)
           if r['study'] == row['study'] and r['topic'] == row['topic']
           and r['outcome'] == row['outcome']]
    if dup:
        errs.append('重复录入：同 (study,topic,outcome) 已存在 row=%s' % dup[0])
    if errs:
        print(json.dumps({'ok': False, 'errors': errs}, ensure_ascii=False))
        raise SystemExit(1)
    m['rows'].append(row)
    save(args.matrix, m)
    print(json.dumps({'ok': True, 'row': len(m['rows'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
