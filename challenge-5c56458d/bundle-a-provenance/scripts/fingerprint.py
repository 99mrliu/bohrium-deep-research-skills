#!/usr/bin/env python3
"""Fingerprint an authorized SQLite data snapshot for provenance auditing.

Read-only. For every database file found under --input (or the single --db
file) the script records: file identity (sha256, size), every table's row
count, every column's declared type, null count, distinct count, typeof
profile, numeric statistics (min/max/mean/sample-std) and top values for
low-cardinality columns. The resulting fingerprint.json is the upstream
"what did we actually receive" record that every later number must be
consistent with. Standard library only.

Usage:
  python fingerprint.py --input /input --out /app/work/fingerprint.json
  python fingerprint.py --db /input/lab.db --out fp.json
"""
import argparse
import hashlib
import json
import os
import sqlite3
import statistics
import sys

DB_EXT = ('.db', '.sqlite', '.sqlite3', '.sqlite2')
MAX_VALUES_FOR_EXACT_STD = 500000
TOP_VALUES = 8


def find_dbs(path):
    if os.path.isfile(path):
        return [path]
    found = []
    for root, _dirs, files in os.walk(path):
        for f in sorted(files):
            if f.lower().endswith(DB_EXT):
                found.append(os.path.join(root, f))
    return sorted(found)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def open_ro(path):
    uri = 'file:%s?mode=ro' % os.path.abspath(path)
    return sqlite3.connect(uri, uri=True)


def profile_column(con, table, col, row_count):
    qname = '"%s"' % col.replace('"', '""')
    qtable = '"%s"' % table.replace('"', '""')
    rec = {'name': col}
    rec['null_count'] = con.execute(
        'SELECT COUNT(*) FROM %s WHERE %s IS NULL' % (qtable, qname)).fetchone()[0]
    rec['distinct_count'] = con.execute(
        'SELECT COUNT(DISTINCT %s) FROM %s' % (qname, qtable)).fetchone()[0]
    types = con.execute(
        'SELECT typeof(%s), COUNT(*) FROM %s WHERE %s IS NOT NULL GROUP BY 1'
        % (qname, qtable, qname)).fetchall()
    rec['typeof'] = {t: n for t, n in types}
    non_null = row_count - rec['null_count']
    if non_null and set(rec['typeof']) <= {'integer', 'real'}:
        rows = con.execute('SELECT %s FROM %s WHERE %s IS NOT NULL'
                           % (qname, qtable, qname)).fetchall()
        vals = [float(r[0]) for r in rows]
        rec['numeric'] = {
            'min': round(min(vals), 6), 'max': round(max(vals), 6),
            'mean': round(statistics.fmean(vals), 6),
            'std': round(statistics.stdev(vals), 6) if len(vals) > 1 else 0.0,
            'n': len(vals),
            'std_kind': 'sample' if len(vals) <= MAX_VALUES_FOR_EXACT_STD else 'population'}
        if set(rec['typeof']) == {'integer'}:
            rec['numeric']['all_integer'] = True
    if non_null and rec['distinct_count'] <= 60:
        top = con.execute(
            'SELECT CAST(%s AS TEXT), COUNT(*) c FROM %s GROUP BY %s '
            'ORDER BY c DESC LIMIT %d' % (qname, qtable, qname, TOP_VALUES)).fetchall()
        rec['top_values'] = [{'value': v, 'count': c} for v, c in top]
    return rec


def profile_db(path):
    rec = {'path': path, 'file_name': os.path.basename(path),
           'size_bytes': os.path.getsize(path), 'sha256': sha256_file(path),
           'tables': {}}
    con = open_ro(path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tables:
            qt = '"%s"' % t.replace('"', '""')
            n = con.execute('SELECT COUNT(*) FROM %s' % qt).fetchone()[0]
            cols = [r[1] for r in con.execute('PRAGMA table_info(%s)' % qt)]
            decl = {r[1]: r[2] for r in con.execute('PRAGMA table_info(%s)' % qt)}
            trec = {'row_count': n, 'columns': []}
            for c in cols:
                crec = profile_column(con, t, c, n)
                crec['declared_type'] = decl.get(c, '')
                trec['columns'].append(crec)
            rec['tables'][t] = trec
    finally:
        con.close()
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--input', help='directory to scan for database files')
    ap.add_argument('--db', help='single database file')
    ap.add_argument('--out', required=True, help='fingerprint JSON output path')
    args = ap.parse_args()
    src = args.db or args.input
    if not src:
        ap.error('one of --db or --input is required')
    dbs = find_dbs(src)
    report = {'tool': 'fingerprint.py', 'source_argument': src,
              'databases_found': len(dbs), 'databases': []}
    for p in dbs:
        try:
            report['databases'].append(profile_db(p))
        except Exception as exc:  # honest failure, keep going for other files
            report['databases'].append({'path': p, 'error': '%s: %s'
                                        % (type(exc).__name__, exc)})
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    ntab = sum(len(d.get('tables', {})) for d in report['databases'])
    print(json.dumps({'out': args.out, 'databases': len(dbs), 'tables': ntab},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
