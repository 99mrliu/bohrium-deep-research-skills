#!/usr/bin/env python3
"""Run a grouped aggregate query and export every number WITH its row lineage.

Input is a small JSON query spec (see references/lineage_contract.md):
{
  "table": "measurements",
  "key": "sample_id",                 // source-row identifier column
  "group_by": ["group_id"],
  "aggregates": [{"func": "AVG", "column": "metric", "as": "mean_metric"},
                 {"func": "COUNT", "column": "*", "as": "n"}],
  "where": "metric IS NOT NULL"       // optional
}
Identifiers are validated against the real schema; functions are whitelisted.
For each output group the lineage sidecar records the contributing source
keys (or a digest when a group exceeds --max-keys), so every reported number
can be independently recomputed from raw rows by scripts/recompute.py.
Read-only, standard library only.

Usage:
  python lineage_export.py --db /input/lab.db --spec /app/work/spec.json \
      --tag q1 --outdir /app/work
Writes: <tag>.csv, <tag>.lineage.jsonl, <tag>.run.json
"""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time

FUNCS = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'}


def ident_ok(name, cols):
    if name not in cols:
        raise SystemExit('identifier %r not in table columns %s' % (name, cols))
    return '"%s"' % name.replace('"', '""')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--max-keys', type=int, default=5000)
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding='utf-8'))
    con = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(args.db), uri=True)
    try:
        table = spec['table']
        qt = '"%s"' % table.replace('"', '""')
        cols = [r[1] for r in con.execute('PRAGMA table_info(%s)' % qt)]
        if not cols:
            raise SystemExit('table %r not found' % table)
        key = ident_ok(spec['key'], cols)
        groups = [ident_ok(g, cols) for g in spec['group_by']]
        aggs = []
        for a in spec['aggregates']:
            f = a['func'].upper()
            if f not in FUNCS:
                raise SystemExit('func %r not whitelisted %s' % (f, FUNCS))
            if a['column'] == '*':
                if f != 'COUNT':
                    raise SystemExit('only COUNT(*) may use *')
                aggs.append((f, '*', a['as'], 'COUNT(*)'))
            else:
                qc = ident_ok(a['column'], cols)
                aggs.append((f, a['column'], a['as'], '%s(%s)' % (f, qc)))
        where = (' WHERE ' + spec['where']) if spec.get('where') else ''
        select_aggs = ', '.join(s for *_x, s in aggs)
        gcols = ', '.join(groups)
        t0 = time.time()
        sql = ('SELECT %s, %s FROM %s%s GROUP BY %s ORDER BY %s'
               % (gcols, select_aggs, qt, where, gcols, gcols))
        rows = con.execute(sql).fetchall()
        keysql = ('SELECT %s, %s FROM %s%s' % (key, gcols, qt, where))
        krows = con.execute(keysql).fetchall()
    finally:
        con.close()
    dt = time.time() - t0
    gnames = spec['group_by']
    lineage_keys = {}
    for kr in krows:
        gv = tuple(kr[1:])
        lineage_keys.setdefault(gv, []).append(kr[0])
    os.makedirs(args.outdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, args.tag + '.csv')
    header = gnames + [a[2] for a in aggs]
    with open(csv_path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(['' if v is None else v for v in r])
    lin_path = os.path.join(args.outdir, args.tag + '.lineage.jsonl')
    with open(lin_path, 'w', encoding='utf-8') as fh:
        for r in rows:
            gv = tuple(r[:len(gnames)])
            keys = lineage_keys.get(gv, [])
            rec = {'group': dict(zip(gnames, gv)),
                   'aggregates': dict(zip([a[2] for a in aggs],
                                          r[len(gnames):])),
                   'source_rows': len(keys)}
            if len(keys) <= args.max_keys:
                rec['source_keys'] = sorted(keys, key=str)
            else:
                digest = hashlib.sha256(
                    json.dumps(sorted(keys, key=str)).encode()).hexdigest()
                rec['source_keys_digest'] = digest
                rec['note'] = ('group too large for inline keys; digest of '
                               'sorted key list recorded')
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    run = {'tag': args.tag, 'db': args.db, 'spec': spec, 'sql': sql,
           'key_sql': keysql, 'seconds': round(dt, 4),
           'groups': len(rows), 'csv': csv_path, 'lineage': lin_path,
           'contract': 'references/lineage_contract.md v1'}
    json.dump(run, open(os.path.join(args.outdir, args.tag + '.run.json'),
                        'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'tag': args.tag, 'groups': len(rows), 'csv': csv_path,
                      'lineage': lin_path}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
