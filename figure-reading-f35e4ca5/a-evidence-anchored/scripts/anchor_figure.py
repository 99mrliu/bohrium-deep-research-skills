#!/usr/bin/env python3
"""Anchor a figure's axis card and readings to the mined evidence (stdlib).

The figure pixels are a *hypothesis*; the case's original tables, caption
and text are the authentic sources. This script gates the three classic
misreads before any number is trusted:

  1. axis-type gate — declared `type` must agree with tick geometry
     (uniform pixel steps => linear; uniform pixel *ratios* => log);
  2. unit-prefix gate — the axis unit must parse, and the data range read
     from the figure must be explainable against candidate table columns
     (mV vs V shows up as a 1e-3 factor here);
  3. provenance gate — every reading series is matched to candidate table
     columns by (unit, name-similarity, range containment).

Inputs:
  --axis         axis_spec.json, authored by the agent while zoomed into the
                 figure: {"axes": [{"axis":"x","label":...,"unit":...,
                 "type":"linear|log","ticks":[{"value":v,"px":p}, ...],
                 "plot_area":[left,top,right,bottom]}]}
  --readings     figure_readings.json (optional): {"series":[{"name":...,
                 "points":[[x,y],...]}]}
  --inventory    inventory.json from mine_case.py

Output: <work>/anchor_map.json with per-tick calibration residuals, hard
FAIL flags, and per-series candidate table columns. Exit code is 0 always;
honesty lives in the flags, so a degraded run still produces a report.
"""
import argparse
import json
import math
import os
import re
import sys

PREFIXES = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6,
            'm': 1e-3, 'c': 1e-2, 'd': 1e-1, 'k': 1e3, 'K': 1e3, 'M': 1e6,
            'G': 1e9, 'T': 1e12}
KNOWN_BASE = {'V', 'A', 'W', 'm', 's', 'g', 'kg', 'mol', 'L', 'l', 'K', '°C',
              'Pa', 'J', 'Hz', 'N', 'cd', 'rad', '%', 'deg', '°', 'counts',
              'a.u.', 'au', 'Ω', 'Ohm', 'S', 'F', 'H', 'T', 'G', 'eV', 'nm',
              'cm', 'mm', 'um', 'µm', 'μm', 'nm', 'C'}


def prefix_scale(unit):
    if not unit:
        return 1.0, unit
    for p in ('µ', 'μ'):
        if unit.startswith(p):
            return PREFIXES[p], unit[1:]
    if unit[0] in PREFIXES:
        return PREFIXES[unit[0]], unit[1:]
    return 1.0, unit


def tick_geometry(ticks):
    """Classify tick spacing from pixel geometry alone."""
    ticks = sorted(ticks, key=lambda t: t['px'])
    gaps = [ticks[i + 1]['px'] - ticks[i]['px'] for i in range(len(ticks) - 1)]
    if len(gaps) < 2:
        return 'insufficient', []
    rel = [abs(g - gaps[0]) / (abs(gaps[0]) or 1) for g in gaps]
    vals = [t['value'] for t in ticks]
    # linear axis: uniform pixel gaps AND uniform value differences
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    drel = [abs(d - diffs[0]) / (abs(diffs[0]) or 1.0) for d in diffs]
    if max(rel) < 0.08 and max(drel) < 0.08:
        return 'linear', rel
    # log axis: uniform pixel gaps AND uniform value ratios
    vr = [vals[i] / vals[i - 1] for i in range(1, len(vals))
          if vals[i - 1] != 0]
    vrel = [abs(r - vr[0]) / (abs(vr[0]) or 1.0) for r in vr] \
        if len(vr) >= 2 else [1.0]
    if max(rel) < 0.08 and max(vrel) < 0.10:
        return 'log', rel
    return 'inconsistent', rel


def lin_fit_residuals(ticks):
    """Least-squares value = a*px + b and per-tick residuals in value units."""
    n = len(ticks)
    if n < 2:
        return None
    sx = sum(t['px'] for t in ticks)
    sy = sum(t['value'] for t in ticks)
    sxx = sum(t['px'] ** 2 for t in ticks)
    sxy = sum(t['px'] * t['value'] for t in ticks)
    den = n * sxx - sx * sx
    if den == 0:
        return None
    a = (n * sxy - sx * sy) / den
    b = (sy - a * sx) / n
    res = [t['value'] - (a * t['px'] + b) for t in ticks]
    scale = (max(t['value'] for t in ticks) -
             min(t['value'] for t in ticks)) or 1.0
    return {'a': a, 'b': b,
            'max_residual_fraction': max(abs(r) for r in res) / abs(scale),
            'per_tick_residuals': res}


def name_tokens(s):
    return set(re.findall(r'[a-zA-Z]+', (s or '').lower())) - {
        'the', 'of', 'vs', 'and', 'in', 'with'}


def candidate_columns(unit, label, lo, hi, tables):
    """Score table columns as anchors for one figure axis/series."""
    scale, base = prefix_scale(unit)
    out = []
    for tname, prof in tables.items():
        for cname, col in prof.get('columns', {}).items():
            cscale, cbase = prefix_scale(col.get('unit_guess'))
            if base and cbase and base.lower() != cbase.lower():
                continue
            if lo is not None and hi is not None:
                span = (hi - lo) or 1e-12
                cover = (min(hi, col['max'] / cscale * scale) -
                         max(lo, col['min'] / cscale * scale)) / span
            else:
                cover = 0.0
            toks = name_tokens(label) & name_tokens(cname)
            score = cover + 0.5 * len(toks)
            if unit and col.get('unit_guess') and \
                    col['unit_guess'].lower() == unit.lower():
                score += 0.5
            if score > 0.05:
                out.append({'table': tname, 'column': cname,
                            'unit_guess': col.get('unit_guess'),
                            'range': [col['min'], col['max']],
                            'overlap_fraction': round(min(max(cover, 0.0), 1.0), 4),
                            'name_tokens_shared': sorted(toks),
                            'score': round(score, 4)})
    out.sort(key=lambda c: -c['score'])
    return out[:5]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--axis', required=True)
    ap.add_argument('--inventory', default='/app/work/inventory.json')
    ap.add_argument('--readings', default=None)
    ap.add_argument('--work', default='/app/work')
    args = ap.parse_args()

    axis = json.load(open(args.axis, encoding='utf-8'))
    inv = json.load(open(args.inventory, encoding='utf-8')) \
        if os.path.exists(args.inventory) else {'tables': {}}
    readings = {}
    if args.readings and os.path.exists(args.readings):
        readings = json.load(open(args.readings, encoding='utf-8'))

    report = {'axes': [], 'series_anchors': [], 'hard_fail': [],
                'warnings': [], 'rules': [
                    'declared axis type must match tick geometry',
                    'unit must parse; figure range must be explainable '
                    'against table ranges modulo SI prefixes',
                    'every series needs >=1 candidate table column or an '
                    'explicit "no_table_anchor" justification']}

    for ax in axis.get('axes', []):
        ticks = ax.get('ticks') or []
        entry = {'axis': ax.get('axis'), 'label': ax.get('label'),
                 'unit': ax.get('unit'), 'type': ax.get('type'),
                 'n_ticks': len(ticks)}
        if len(ticks) < 3:
            report['hard_fail'].append(
                {'check': 'min_ticks', 'axis': ax.get('axis'),
                 'detail': 'fewer than 3 calibrated ticks; reading '
                           'cannot be trusted'})
        geo, rel = tick_geometry(ticks)
        entry['geometry_says'] = geo
        if ax.get('type') not in ('linear', 'log'):
            report['hard_fail'].append(
                {'check': 'axis_type_declared', 'axis': ax.get('axis'),
                 'detail': 'type must be linear or log'})
        elif geo != 'insufficient' and geo != ax.get('type') and \
                geo != 'inconsistent':
            report['hard_fail'].append(
                {'check': 'axis_type_gate', 'axis': ax.get('axis'),
                 'detail': 'declared %s but tick geometry says %s — '
                           're-read the tick labels before any value '
                           'is trusted' % (ax.get('type'), geo)})
        elif geo == 'inconsistent':
            report['warnings'].append(
                {'check': 'tick_geometry', 'axis': ax.get('axis'),
                 'detail': 'tick spacing matches neither linear nor log; '
                           're-measure tick pixels'})
        fit = lin_fit_residuals(ticks) if ax.get('type') == 'linear' and \
            len(ticks) >= 2 else None
        if fit:
            entry['calibration'] = fit
            if fit['max_residual_fraction'] > 0.02:
                report['warnings'].append(
                    {'check': 'calibration_residual', 'axis': ax.get('axis'),
                     'detail': 'max tick residual %.4f of axis span; '
                               're-measure' % fit['max_residual_fraction']})
        scale, base = prefix_scale(ax.get('unit'))
        if ax.get('unit') and base not in KNOWN_BASE and \
                not re.fullmatch(r'[a-zA-Zµμ°/%·.*+-]+', ax.get('unit')):
            report['hard_fail'].append(
                {'check': 'unit_parse', 'axis': ax.get('axis'),
                 'detail': 'unit %r does not parse; copy it verbatim '
                           'from the axis title' % ax.get('unit')})
        lo = hi = None
        for s in readings.get('series', []):
            pts = [p for p in s.get('points', []) if p and len(p) >= 2]
            if not pts:
                continue
            idx = 0 if ax.get('axis') == 'x' else 1
            vals = [p[idx] for p in pts]
            lo = min(lo, min(vals)) if lo is not None else min(vals)
            hi = max(hi, max(vals)) if hi is not None else max(vals)
        entry['readings_range'] = [lo, hi] if lo is not None else None
        entry['candidate_columns'] = candidate_columns(
            ax.get('unit'), ax.get('label'), lo, hi, inv.get('tables', {}))
        report['axes'].append(entry)

    tables = inv.get('tables', {})
    for s in readings.get('series', []):
        pts = s.get('points') or []
        lo = min((p[1] for p in pts), default=None)
        hi = max((p[1] for p in pts), default=None)
        xlo = min((p[0] for p in pts), default=None)
        xhi = max((p[0] for p in pts), default=None)
        anchors = candidate_columns(
            (axis.get('axes') or [{}])[1].get('unit') if
            len(axis.get('axes') or []) > 1 else None,
            s.get('name'), lo, hi, tables)
        entry = {'series': s.get('name'), 'n_points': len(pts),
                 'y_range': [lo, hi] if lo is not None else None,
                 'candidate_columns': anchors}
        if not anchors:
            report['warnings'].append(
                {'check': 'series_anchor', 'series': s.get('name'),
                 'detail': 'no table column anchors this series; add '
                           '"no_table_anchor" justification with a figure '
                           'region locator or treat values as unverified'})
        report['series_anchors'].append(entry)

    os.makedirs(args.work, exist_ok=True)
    out = os.path.join(args.work, 'anchor_map.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'anchor_map': out,
                      'hard_fail': len(report['hard_fail']),
                      'warnings': len(report['warnings']),
                      'axes': [a['axis'] for a in report['axes']]},
                     ensure_ascii=False))
    if report['hard_fail']:
        print('HARD FAIL — fix the axis card before extracting any value',
              file=sys.stderr)


if __name__ == '__main__':
    main()
