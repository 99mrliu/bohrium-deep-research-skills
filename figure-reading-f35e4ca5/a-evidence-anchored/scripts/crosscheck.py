#!/usr/bin/env python3
"""Bidirectional figure-reading vs table crosscheck (stdlib).

Runs the authenticity test both ways:

  * every figure reading is matched to the nearest row of its anchored
    table column (from anchor_map.json), with a relative error;
  * every table row that lies inside the figure's x-range is checked for a
    matching reading — an unexplained table row usually means a missed
    curve segment or a mis-assigned legend entry.

Inputs:
  --readings  figure_readings.json {"series":[{"name":..., "points":[[x,y]]}]}
  --anchor    anchor_map.json from anchor_figure.py
  --inventory inventory.json (needs the raw tables; re-reads the table
              files listed there from --input-dir)
  --input-dir /input (to reload the raw table values)
  --tol       relative tolerance, default 0.05

Output: <work>/crosscheck_matrix.json. `all_matched` is False unless every
reading and every in-range table row is explained. The matrix is deliverable
evidence; paste its summary into result.json under the contract's
evidence/verification field.
"""
import argparse
import csv
import io
import json
import os


def load_table(path):
    raw = open(path, encoding='utf-8', errors='replace').read()
    if path.endswith('.tsv'):
        delim = '\t'
    else:
        try:
            delim = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t|').delimiter
        except csv.Error:
            delim = ','
    rows = [r for r in csv.reader(io.StringIO(raw), delimiter=delim)
            if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    header = [h.strip() for h in rows[0]]
    width = len(header)
    data = []
    for r in rows[1:]:
        rec = {}
        for ci in range(min(len(r), width)):
            try:
                rec[header[ci]] = float(r[ci])
            except (ValueError, IndexError):
                pass
        if rec:
            data.append(rec)
    return header, data


def nearest(v, candidates, floor):
    """Nearest candidate with scale-aware error: relative to |v|, but with
    an absolute floor of 10% of the data span so near-zero readings are
    judged like every other pixel reading."""
    best, bd = None, None
    for c in candidates:
        d = abs(c - v) / max(abs(v), floor)
        if bd is None or d < bd:
            best, bd = c, d
    return best, bd


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--readings', required=True)
    ap.add_argument('--anchor', required=True)
    ap.add_argument('--inventory', required=True)
    ap.add_argument('--input-dir', default='/input')
    ap.add_argument('--tol', type=float, default=0.05)
    ap.add_argument('--work', default='/app/work')
    args = ap.parse_args()

    readings = json.load(open(args.readings, encoding='utf-8'))
    anchor = json.load(open(args.anchor, encoding='utf-8'))
    anchor_by_series = {a['series']: a for a in anchor.get('series_anchors', [])}

    matrix = {'tol_rel': args.tol, 'series': [], 'unexplained_table_rows': [],
              'all_matched': True, 'notes': []}

    for s in readings.get('series', []):
        name = s.get('name')
        pts = s.get('points') or []
        anc = anchor_by_series.get(name) or {}
        cands = anc.get('candidate_columns') or []
        entry = {'series': name, 'n_points': len(pts),
                 'matched': [], 'unmatched_readings': []}
        if not cands:
            entry['note'] = 'no table anchor — readings stand on the ' \
                            'figure alone (state this in uncertainty)'
            matrix['series'].append(entry)
            matrix['all_matched'] = False
            continue
        best = cands[0]
        table_path = os.path.join(args.input_dir, best['table'])
        if not os.path.exists(table_path):
            matrix['notes'].append('table file missing: %s' % best['table'])
            matrix['all_matched'] = False
            matrix['series'].append(entry)
            continue
        loaded = load_table(table_path)
        if not loaded:
            matrix['notes'].append('table unparsable: %s' % best['table'])
            matrix['all_matched'] = False
            matrix['series'].append(entry)
            continue
        header, data = loaded
        ycol = best['column']
        xcols = [h for h in header if h != ycol]
        xcol = xcols[0] if xcols else None
        ys = [d.get(ycol) for d in data if d.get(ycol) is not None]
        span = (max(ys) - min(ys)) if ys else 0.0
        floor = max(1e-12, 0.1 * abs(span))
        xs = [d.get(xcol) for d in data
              if xcol and d.get(xcol) is not None]
        entry['anchor_table'] = best['table']
        entry['anchor_column'] = ycol
        entry['anchor_x_column'] = xcol
        xspan = (max(xs) - min(xs)) if xs else 0.0
        xtol = 0.02 * abs(xspan) + 1e-12
        rows_used = set()
        for p in pts:
            x, y = p[0], p[1]
            # match the table row by x first (same condition), then compare y
            cand = [(abs(d[xcol] - x), d) for d in data
                    if xcol and d.get(xcol) is not None
                    and d.get(ycol) is not None] if xcol else []
            row = min(cand, key=lambda t: t[0])[1] if cand and \
                min(cand, key=lambda t: t[0])[0] <= xtol else None
            if row is None:
                # no x anchor: fall back to nearest y anywhere in the table
                tv, terr = nearest(y, ys, floor)
                rec = {'point': p, 'table_value': tv, 'matched_by': 'y',
                       'rel_err': round(terr, 5) if terr is not None else None,
                       'within_tol': terr is not None and terr <= args.tol}
            else:
                rows_used.add(id(row))
                tv = row[ycol]
                terr = abs(tv - y) / max(abs(y), floor)
                rec = {'point': p, 'table_value': tv, 'matched_by': 'x_row',
                       'table_x': row.get(xcol),
                       'rel_err': round(terr, 5),
                       'within_tol': terr <= args.tol}
            (entry['matched'] if rec['within_tol']
             else entry['unmatched_readings']).append(rec)
            if not rec['within_tol']:
                matrix['all_matched'] = False
        xlo = min((p[0] for p in pts), default=None)
        xhi = max((p[0] for p in pts), default=None)
        if xcol and xlo is not None:
            for d in data:
                xv = d.get(xcol)
                if xv is None or not (xlo - 1e-12 <= xv <= xhi + 1e-12):
                    continue
                if id(d) in rows_used:
                    continue
                ry = [p[1] for p in pts]
                if not ry:
                    break
                _, dist = nearest(d.get(ycol), ry, floor)
                if dist is None or dist > args.tol:
                    matrix['unexplained_table_rows'].append({
                        'table': best['table'], 'column': ycol,
                        'x': xv, 'value': d.get(ycol),
                        'note': 'in-range table row with no figure '
                                'reading within tolerance'})
                    matrix['all_matched'] = False
        errs = [m['rel_err'] for m in entry['matched'] if m['rel_err'] is not None]
        entry['median_rel_err'] = sorted(errs)[len(errs) // 2] if errs else None
        matrix['series'].append(entry)

    os.makedirs(args.work, exist_ok=True)
    out = os.path.join(args.work, 'crosscheck_matrix.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    summary = {
        'crosscheck': out,
        'all_matched': matrix['all_matched'],
        'per_series': [{'series': e['series'],
                        'matched': len(e['matched']),
                        'unmatched': len(e['unmatched_readings']),
                        'median_rel_err': e.get('median_rel_err')}
                       for e in matrix['series']],
        'unexplained_table_rows': len(matrix['unexplained_table_rows']),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
