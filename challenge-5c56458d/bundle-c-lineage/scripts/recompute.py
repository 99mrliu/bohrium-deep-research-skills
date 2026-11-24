#!/usr/bin/env python3
"""Independently recompute a lineage export from raw rows.

This is the audit twin of lineage_export.py: instead of trusting GROUP BY,
it fetches the source rows named by each group's source_keys and recomputes
every aggregate in plain Python (per-function implementations below, not via
SQL). Any mismatch between the exported CSV numbers and the recomputation is
reported — that is exactly the class of error (wrong join key, fan-out,
silent filter drift) that reviewers need to catch. Read-only, stdlib only.

Usage:
  python recompute.py --db /input/lab.db --tag q1 --outdir /app/work
Reads: <tag>.run.json, <tag>.lineage.jsonl  Writes: <tag>.recompute.json
"""
import argparse
import json
import os
import sqlite3
import sys

TOL = 1e-9


def recompute_func(func, vals):
    vals = [v for v in vals if v is not None]
    if func == 'COUNT':
        return len(vals)
    if not vals:
        return None
    if func == 'SUM':
        return sum(vals)
    if func == 'AVG':
        return sum(vals) / len(vals)
    if func == 'MIN':
        return min(vals)
    if func == 'MAX':
        return max(vals)
    raise SystemExit('unknown func ' + func)


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)), abs(float(b)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()
    run = json.load(open(os.path.join(args.outdir, args.tag + '.run.json'),
                         encoding='utf-8'))
    spec = run['spec']
    con = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(args.db), uri=True)
    qt = '"%s"' % spec['table'].replace('"', '""')
    keyq = '"%s"' % spec['key'].replace('"', '""')
    mismatches, checked, skipped = [], 0, 0
    try:
        for line in open(os.path.join(args.outdir, args.tag + '.lineage.jsonl'),
                         encoding='utf-8'):
            rec = json.loads(line)
            if 'source_keys' not in rec:
                skipped += 1
                continue
            ph = ','.join('?' * len(rec['source_keys'])) or "''"
            for asname, exported in rec['aggregates'].items():
                agg = next(a for a in spec['aggregates'] if a['as'] == asname)
                func = agg['func'].upper()
                if agg['column'] == '*':
                    got = len(rec['source_keys'])
                else:
                    colq = '"%s"' % agg['column'].replace('"', '""')
                    vals = [r[0] for r in con.execute(
                        'SELECT %s FROM %s WHERE %s IN (%s)' % (colq, qt, keyq, ph),
                        rec['source_keys'])]
                    got = recompute_func(func, vals)
                checked += 1
                if not close(exported, got):
                    mismatches.append({'group': rec['group'], 'aggregate': asname,
                                       'exported': exported, 'recomputed': got})
    finally:
        con.close()
    report = {'tag': args.tag, 'db': args.db, 'aggregates_checked': checked,
              'groups_skipped_digest_only': skipped,
              'mismatches': mismatches,
              'status': 'PASS' if not mismatches else 'MISMATCH'}
    out = os.path.join(args.outdir, args.tag + '.recompute.json')
    json.dump(report, open(out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'tag': args.tag, 'status': report['status'],
                      'checked': checked, 'mismatches': len(mismatches)},
                     ensure_ascii=False))
    return 0 if not mismatches else 2


if __name__ == '__main__':
    sys.exit(main())
