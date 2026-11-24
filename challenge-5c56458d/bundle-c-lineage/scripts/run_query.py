#!/usr/bin/env python3
"""Execute a read-only SELECT and export the result set with run metadata.

The query text is the unit of reproducibility: it is stored verbatim next to
its output, together with the database sha256, wall time, row count and
column type profile. Only SELECT/WITH statements are accepted; the database
is opened read-only. Standard library only.

Usage:
  python run_query.py --db /input/lab.db --sql /app/work/q1.sql \
      --tag q1 --outdir /app/work
Writes: <outdir>/<tag>.csv, <outdir>/<tag>.run.json
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True)
    ap.add_argument('--sql', required=True, help='file containing ONE select')
    ap.add_argument('--tag', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()
    sql = open(args.sql, encoding='utf-8').read().strip().rstrip(';')
    head = sql.lstrip().split(None, 1)[0].lower() if sql.split() else ''
    if head not in ('select', 'with'):
        raise SystemExit('refused: only SELECT/WITH statements are executed')
    con = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(args.db), uri=True)
    t0 = time.time()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        rec = {'tag': args.tag, 'db': args.db, 'sql': sql, 'status': 'error',
               'error': '%s: %s' % (type(exc).__name__, exc)}
        os.makedirs(args.outdir, exist_ok=True)
        json.dump(rec, open(os.path.join(args.outdir, args.tag + '.run.json'),
                            'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        raise SystemExit('query failed (see %s.run.json): %s' % (args.tag, exc))
    finally:
        con.close()
    dt = time.time() - t0
    os.makedirs(args.outdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, args.tag + '.csv')
    import csv as csvmod
    with open(csv_path, 'w', encoding='utf-8', newline='') as fh:
        w = csvmod.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow(['' if v is None else v for v in r])
    typeof = {}
    for r in rows[:200]:
        for c, v in zip(cols, r):
            typeof.setdefault(c, set()).add(type(v).__name__)
    rec = {'tag': args.tag, 'db': args.db, 'db_sha256': sha256_file(args.db),
           'sql_file': args.sql, 'sql': sql, 'status': 'ok',
           'row_count': len(rows), 'columns': cols,
           'column_py_types': {c: sorted(t) for c, t in typeof.items()},
           'seconds': round(dt, 4), 'csv': csv_path,
           'csv_sha256': sha256_file(csv_path)}
    json.dump(rec, open(os.path.join(args.outdir, args.tag + '.run.json'),
                        'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'tag': args.tag, 'rows': len(rows), 'csv': csv_path,
                      'seconds': rec['seconds']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
