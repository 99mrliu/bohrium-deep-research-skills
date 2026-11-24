#!/usr/bin/env python3
"""Profile every column of a SQLite snapshot and infer its field role.

The centre of this skill is field *meaning*, so profiling goes beyond
min/max: each column is classified into a role that drives later semantics
work — identifier / coded_categorical / numeric_coded_category (a trap:
numbers that must not be aggregated) / numeric_measure / boolean_flag /
free_text / constant / empty. Every classification carries the evidence
(distinct ratio, typeof profile) so a reviewer can override it.
Read-only, standard library only.

Usage:
  python profile_fields.py --db /input/lab.db --out /app/work/field_profile.json
"""
import argparse
import json
import os
import sqlite3
import sys

DB_EXT = ('.db', '.sqlite', '.sqlite3')


def open_ro(path):
    return sqlite3.connect('file:%s?mode=ro' % os.path.abspath(path), uri=True)


def classify(name, row_count, nulls, distinct, typeofs, is_numeric, avg_len):
    non_null = row_count - nulls
    ev = {'distinct': distinct, 'non_null': non_null,
          'distinct_ratio': round(distinct / non_null, 4) if non_null else None}
    if non_null == 0:
        return 'empty', ev, 'column is entirely NULL'
    if distinct == 1:
        return 'constant', ev, 'single value; carries no information'
    if non_null and distinct == non_null and row_count > 0:
        return 'identifier', ev, 'unique per row; use as key, never aggregate'
    if is_numeric and distinct <= 10:
        return 'numeric_coded_category', ev, (
            'TRAP: numeric-typed code with <=10 levels; treat as labels, '
            'do NOT average/sum without explicit justification')
    if is_numeric:
        return 'numeric_measure', ev, 'quantitative measure; aggregations meaningful'
    if distinct <= 2:
        return 'boolean_flag', ev, 'two-level flag'
    if distinct <= max(20, int(0.01 * row_count) + 1):
        return 'coded_categorical', ev, 'low-cardinality label column'
    if avg_len and avg_len > 30:
        return 'free_text', ev, 'long text; not a join key or category'
    return 'text_label', ev, 'moderate-cardinality text; inspect before grouping'


def profile_db(path):
    con = open_ro(path)
    out = {'database': path, 'tables': {}}
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tables:
            qt = '"%s"' % t.replace('"', '""')
            n = con.execute('SELECT COUNT(*) FROM %s' % qt).fetchone()[0]
            cols = [r[1] for r in con.execute('PRAGMA table_info(%s)' % qt)]
            trec = {'row_count': n, 'columns': []}
            for c in cols:
                qc = '"%s"' % c.replace('"', '""')
                nulls = con.execute('SELECT COUNT(*) FROM %s WHERE %s IS NULL'
                                    % (qt, qc)).fetchone()[0]
                distinct = con.execute('SELECT COUNT(DISTINCT %s) FROM %s'
                                       % (qc, qt)).fetchone()[0]
                typeofs = dict(con.execute(
                    'SELECT typeof(%s), COUNT(*) FROM %s WHERE %s IS NOT NULL '
                    'GROUP BY 1' % (qc, qt, qc)).fetchall())
                is_num = bool(typeofs) and set(typeofs) <= {'integer', 'real'}
                avg_len = None
                if not is_num and typeofs:
                    avg_len = con.execute(
                        'SELECT AVG(LENGTH(CAST(%s AS TEXT))) FROM %s WHERE %s IS NOT NULL'
                        % (qc, qt, qc)).fetchone()[0]
                role, ev, note = classify(c, n, nulls, distinct, typeofs,
                                          is_num, avg_len)
                rec = {'name': c, 'role': role, 'evidence': ev,
                       'typeof': typeofs, 'null_count': nulls, 'note': note}
                if is_num and n - nulls:
                    rec['range'] = list(con.execute(
                        'SELECT MIN(%s), MAX(%s) FROM %s' % (qc, qc, qt)).fetchone())
                if 1 < distinct <= 30:
                    rec['levels'] = [str(r[0]) for r in con.execute(
                        'SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL '
                        'ORDER BY 1 LIMIT 30' % (qc, qt, qc)).fetchall()]
                trec['columns'].append(rec)
            out['tables'][t] = trec
    finally:
        con.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    prof = profile_db(args.db)
    traps = [{'table': t, 'column': c['name']}
             for t, tr in prof['tables'].items() for c in tr['columns']
             if c['role'] == 'numeric_coded_category']
    prof['numeric_code_traps'] = traps
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(prof, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'out': args.out, 'tables': len(prof['tables']),
                      'numeric_code_traps': traps}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
