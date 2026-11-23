#!/usr/bin/env python3
"""Machine-checked QC gates for the figure-reading runbook (stdlib only).

Usage:
  python gate.py --gate 2 --work /app/work [--out /app/output] \
      [--case /input/case.json]

Each gate validates one artifact against hard rules and records the
outcome in run_state.json and gate_report.json. Exit 0 = pass (warnings
allowed), 2 = fail (blocking: do not proceed to reading values until
fixed). The gates are deliberately mechanical: they check PROCESS
ARTIFACTS, not taste.

Gate artifacts (all under --work):
  g1  inventory.json      {"files":[{path,kind}...], "figures":[...],
                           "tables":[...], "contract_fields":[...]}
  g2  axis_card.json      {"axes":[{name,label,unit,type,
                           ticks:[{value,px}...], plot_area:[l,t,r,b]}]}
  g3  element_ledger.json {"entries":[{element_type,id,status,locator,
                           value?,reason?}...], "legend_entries": n}
  g4  crosscheck.json     {"figure_vs_table":{"checked":n,"matched":m},
                           "caption_semantics_checked":bool,"notes":[...]}
  g5  lints /app/output/result.json (or --result PATH)
"""
import argparse
import json
import os
import sys
import time

ELEMENT_TYPES = {'series', 'data_point', 'errorbar', 'significance_mark',
                 'scale_bar', 'annotation', 'legend', 'axis', 'subfigure_label'}
STATUS_VALUES = {'read', 'not_present', 'unreadable'}
KNOWN_PREFIX = set('fpnuµμmc dkKMGT') | {'%'}


def fail(findings, check, detail):
    findings.append({'level': 'fail', 'check': check, 'detail': detail})


def warn(findings, check, detail):
    findings.append({'level': 'warn', 'check': check, 'detail': detail})


def tick_geometry(ticks):
    ticks = sorted(ticks, key=lambda t: t['px'])
    if len(ticks) < 3:
        return 'insufficient'
    gaps = [ticks[i + 1]['px'] - ticks[i]['px'] for i in range(len(ticks) - 1)]
    vals = [t['value'] for t in ticks]
    if any(g <= 0 for g in gaps):
        return 'non_monotonic_px'
    rel = [abs(g - gaps[0]) / (abs(gaps[0]) or 1) for g in gaps]
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    # image y-axes are pixel-inverted: accept either sign, but consistently
    if not (all(d > 0 for d in diffs) or all(d < 0 for d in diffs)):
        return 'non_monotonic_value'
    diffs = [abs(d) for d in diffs]
    drel = [abs(d - diffs[0]) / (abs(diffs[0]) or 1.0) for d in diffs]
    if max(rel) < 0.08 and max(drel) < 0.08:
        return 'linear'
    vr = [vals[i] / vals[i - 1] for i in range(1, len(vals))
          if vals[i - 1] != 0]
    vrel = [abs(r - vr[0]) / (abs(vr[0]) or 1.0) for r in vr] \
        if len(vr) >= 2 else [1.0]
    if max(rel) < 0.08 and max(vrel) < 0.10:
        return 'log'
    return 'inconsistent'


def gate1(work, out, case, findings):
    path = os.path.join(work, 'inventory.json')
    if not os.path.exists(path):
        fail(findings, 'g1.artifact', 'inventory.json missing')
        return
    inv = json.load(open(path, encoding='utf-8'))
    if not inv.get('files'):
        fail(findings, 'g1.files', 'no input files inventoried')
    kinds = {f.get('kind') for f in inv.get('files', [])}
    if 'figure' not in kinds and not inv.get('figures'):
        warn(findings, 'g1.figures', 'no figure image found; confirm the '
                                     'case really has none')
    if not inv.get('contract_fields'):
        fail(findings, 'g1.contract', 'contract_fields empty — the gates '
                                      'cannot guard an unknown contract')


def gate2(work, out, case, findings):
    path = os.path.join(work, 'axis_card.json')
    if not os.path.exists(path):
        fail(findings, 'g2.artifact', 'axis_card.json missing')
        return
    card = json.load(open(path, encoding='utf-8'))
    axes = card.get('axes')
    if not axes:
        fail(findings, 'g2.axes', 'axis_card has no axes')
        return
    for ax in axes:
        name = ax.get('name', '?')
        for req in ('label', 'type', 'ticks', 'plot_area'):
            if req not in ax:
                fail(findings, 'g2.schema', 'axis %s missing %r'
                     % (name, req))
        ticks = ax.get('ticks') or []
        if len(ticks) < 3:
            fail(findings, 'g2.min_ticks', 'axis %s: fewer than 3 ticks '
                 '— calibration cannot be trusted' % name)
            continue
        geo = tick_geometry(ticks)
        if geo in ('non_monotonic_px', 'non_monotonic_value'):
            fail(findings, 'g2.monotonic', 'axis %s: tick %s'
                 % (name, geo.replace('_', ' ')))
        elif geo == 'inconsistent':
            fail(findings, 'g2.geometry', 'axis %s: ticks match neither '
                 'linear nor log spacing — re-measure' % name)
        elif geo != 'insufficient' and ax.get('type') in ('linear', 'log') \
                and geo != ax.get('type'):
            fail(findings, 'g2.axis_type_gate',
                 'axis %s declared %s but tick geometry says %s'
                 % (name, ax.get('type'), geo))
        if ax.get('type') not in ('linear', 'log'):
            fail(findings, 'g2.type', 'axis %s type must be linear|log'
                 % name)
        unit = ax.get('unit')
        if unit is None or unit == '':
            if not ax.get('dimensionless'):
                warn(findings, 'g2.unit', 'axis %s has no unit; set '
                     '"dimensionless": true if truly unitless' % name)
        elif not isinstance(unit, str):
            fail(findings, 'g2.unit_type', 'axis %s unit not a string' % name)
        elif unit and unit not in KNOWN_PREFIX and \
                unit[0] not in KNOWN_PREFIX and not unit.isalpha() and \
                not any(ch in unit for ch in '°/%·*'):
            warn(findings, 'g2.unit_odd',
                 'axis %s unit %r unusual — verify character by character '
                 '(mV vs V, µm vs nm)' % (name, unit))
        pa = ax.get('plot_area')
        if not (isinstance(pa, list) and len(pa) == 4 and
                pa[0] < pa[2] and pa[1] < pa[3]):
            fail(findings, 'g2.plot_area', 'axis %s plot_area must be '
                 '[left,top,right,bottom] with left<right, top<bottom'
                 % name)


def gate3(work, out, case, findings):
    path = os.path.join(work, 'element_ledger.json')
    if not os.path.exists(path):
        fail(findings, 'g3.artifact', 'element_ledger.json missing')
        return
    led = json.load(open(path, encoding='utf-8'))
    entries = led.get('entries') or []
    if not entries:
        fail(findings, 'g3.entries', 'ledger empty')
        return
    n_series = 0
    for e in entries:
        et, st = e.get('element_type'), e.get('status')
        if et not in ELEMENT_TYPES:
            fail(findings, 'g3.type', 'unknown element_type %r' % et)
        if st not in STATUS_VALUES:
            fail(findings, 'g3.status', 'entry %r: status must be one of '
                 '%s' % (e.get('id'), sorted(STATUS_VALUES)))
        if st == 'read' and not e.get('locator'):
            fail(findings, 'g3.locator', 'entry %r marked read without a '
                 'locator (figure region / table cell)' % e.get('id'))
        if st == 'unreadable' and not e.get('reason'):
            fail(findings, 'g3.reason', 'entry %r unreadable without a '
                 'reason' % e.get('id'))
        if et == 'series' and st == 'read':
            n_series += 1
    legend_n = led.get('legend_entries')
    if isinstance(legend_n, int) and legend_n > 0 and n_series < legend_n:
        fail(findings, 'g3.legend_coverage',
             'legend has %d entries but only %d series marked read — '
             'missed series or legend mapping not done'
             % (legend_n, n_series))
    if n_series == 0:
        warn(findings, 'g3.no_series', 'no series read yet')


def gate4(work, out, case, findings):
    path = os.path.join(work, 'crosscheck.json')
    if not os.path.exists(path):
        fail(findings, 'g4.artifact', 'crosscheck.json missing — even a '
             '"nothing to crosscheck against" record is required')
        return
    cc = json.load(open(path, encoding='utf-8'))
    fvt = cc.get('figure_vs_table') or {}
    checked = fvt.get('checked', 0)
    matched = fvt.get('matched', 0)
    if checked == 0:
        warn(findings, 'g4.nothing_checked',
             'no figure-vs-table pairs checked; state explicitly why '
             '(no tables shipped?) in crosscheck.notes')
        if not cc.get('notes'):
            fail(findings, 'g4.notes', 'unchecked crosscheck needs '
                 'explanatory notes')
    elif matched < checked * 0.5:
        fail(findings, 'g4.match_rate',
             'only %d/%d figure values match tables — calibration or '
             'legend mapping is likely wrong' % (matched, checked))
    if not cc.get('caption_semantics_checked'):
        warn(findings, 'g4.caption', 'caption semantics (error bars, n, '
             'significance) not checked — quote the caption verbatim')


def scan_units(obj, path, findings):
    """Recursively require unit on numeric 'value' leaves."""
    if isinstance(obj, dict):
        if 'value' in obj and isinstance(obj['value'], (int, float)):
            if not obj.get('unit'):
                fail(findings, 'g5.unit',
                     '%s: numeric value without unit' % path)
        for k, v in obj.items():
            scan_units(v, '%s.%s' % (path, k), findings)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_units(v, '%s[%d]' % (path, i), findings)


def gate5(work, out, case, findings, result_path):
    if not os.path.exists(result_path):
        fail(findings, 'g5.artifact', 'result.json missing at %s'
             % result_path)
        return
    result = json.load(open(result_path, encoding='utf-8'))
    fields = []
    if case:
        cf = (case.get('output_contract') or {})
        if isinstance(cf, dict):
            fields = list(cf.keys())
        elif isinstance(cf, list):
            fields = [i if isinstance(i, str) else i.get('name')
                      for i in cf]
            fields = [f for f in fields if f]
    nulls = [f for f in fields if result.get(f) is None]
    if result.get('status') == 'success' and nulls:
        fail(findings, 'g5.honesty',
             'status success with null contract fields: %s'
             % ', '.join(nulls))
    if result.get('status') != 'success' and not result.get('status_reason'):
        warn(findings, 'g5.reason', 'non-success status without '
             'status_reason')
    scan_units(result, 'result', findings)
    cid = case and (case.get('case_id') or case.get('caseId')
                    or case.get('id'))
    if cid and result.get('case_id') != cid:
        fail(findings, 'g5.case_id', 'result.case_id %r != case %r'
             % (result.get('case_id'), cid))


GATE_FUNCS = {1: gate1, 2: gate2, 3: gate3, 4: gate4, 5: gate5}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gate', type=int, required=True, choices=[1, 2, 3, 4, 5])
    ap.add_argument('--work', default='/app/work')
    ap.add_argument('--out', default='/app/output')
    ap.add_argument('--case', default='/input/case.json')
    ap.add_argument('--result', default=None)
    args = ap.parse_args()

    case = {}
    if os.path.exists(args.case):
        case = json.load(open(args.case, encoding='utf-8'))
    findings = []
    if args.gate == 5:
        gate5(args.work, args.out, case, findings,
              args.result or os.path.join(args.out, 'result.json'))
    else:
        GATE_FUNCS[args.gate](args.work, args.out, case, findings)

    state_path = os.path.join(args.work, 'run_state.json')
    state = {}
    if os.path.exists(state_path):
        state = json.load(open(state_path, encoding='utf-8'))
    gkey = 'g%d' % args.gate
    failed = [f for f in findings if f['level'] == 'fail']
    state.setdefault('gates', {})[gkey] = {
        'status': 'fail' if failed else 'pass',
        'checked_at': time.time(),
        'findings': findings,
    }
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    report_path = os.path.join(args.work, 'gate_report.json')
    report = []
    if os.path.exists(report_path):
        report = json.load(open(report_path, encoding='utf-8'))
    report.append({'gate': gkey, 'at': time.time(),
                   'status': 'fail' if failed else 'pass',
                   'findings': findings})
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({'gate': gkey, 'status': 'fail' if failed else 'pass',
                      'failures': len(failed),
                      'warnings': len(findings) - len(failed),
                      'findings': findings}, ensure_ascii=False))
    if failed:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
