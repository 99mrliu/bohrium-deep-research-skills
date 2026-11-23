#!/usr/bin/env python3
"""Validate an agent-authored figure_spec.json into a canonical spec.

The spec is the skill's single source of truth: everything the agent read
from the figure — axes with verbatim labels and units, series with points,
bars with errors, annotations — is declared here BEFORE any rendering.
Validation is a hard gate: a spec with missing units or inconsistent
series never reaches the renderer.

Usage:
  python to_spec.py --spec work/figure_spec.json --out work/spec_canonical.json

Exit 0 and prints {"valid": true, ...} on success; exit 2 with the full
error list otherwise. Warnings (unusual unit prefixes, legend gaps) do not
block.
"""
import argparse
import json
import math
import os
import re
import sys

HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
NAMED_COLORS = {'black', 'gray', 'grey', 'red', 'green', 'blue', 'orange',
                'purple', 'brown', 'pink', 'cyan', 'magenta', 'yellow',
                'olive', 'navy', 'teal', 'maroon', 'white'}
MARKERS = {'o', 's', '^', 'v', 'D', 'x', '+', '*', '.', 'none', None}
KINDS = {'line', 'scatter', 'bar'}
PREFIX_RE = re.compile(r'^[fpnuµμmc dkKMGT]?')


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and \
        math.isfinite(v)


def check_axis(name, ax, errors, warnings):
    for req in ('label', 'type', 'range'):
        if req not in ax:
            errors.append('axis %s: missing %r' % (name, req))
    label = ax.get('label')
    if isinstance(label, str):
        if not re.search(r'[\(\[][^()\[\]]+[\)\]]|%',
                         label) and not ax.get('unit'):
            warnings.append('axis %s: label %r shows no unit in '
                            'parentheses and no "unit" field — copy the '
                            'axis title verbatim' % (name, label))
    unit = ax.get('unit')
    if unit is not None and not isinstance(unit, str):
        errors.append('axis %s: unit must be a string' % name)
    if ax.get('type') not in ('linear', 'log'):
        errors.append('axis %s: type must be "linear" or "log", got %r'
                      % (name, ax.get('type')))
    rng = ax.get('range')
    if not (isinstance(rng, list) and len(rng) == 2 and all(map(is_num, rng))):
        errors.append('axis %s: range must be [min, max] numbers' % name)
    else:
        if not rng[0] < rng[1]:
            errors.append('axis %s: range min >= max' % name)
        if ax.get('type') == 'log' and rng[0] <= 0:
            errors.append('axis %s: log axis range must be > 0' % name)


def check_series(idx, s, errors, warnings):
    tag = 'series[%d] (%r)' % (idx, s.get('name'))
    if not s.get('name'):
        errors.append('%s: missing name (must match the legend verbatim)'
                      % tag)
    kind = s.get('kind', 'line')
    if kind not in KINDS:
        errors.append('%s: kind must be one of %s' % (tag, sorted(KINDS)))
    color = s.get('color')
    if color is not None and not (HEX_RE.match(str(color)) or
                                  str(color).lower() in NAMED_COLORS):
        warnings.append('%s: color %r is neither #rrggbb nor a basic name; '
                        'renderer will pass it through verbatim'
                        % (tag, color))
    if kind in ('line', 'scatter'):
        pts = s.get('points')
        if not (isinstance(pts, list) and len(pts) >= 2):
            errors.append('%s: needs >=2 points' % tag)
        else:
            for pi, p in enumerate(pts):
                if not (isinstance(p, list) and len(p) >= 2 and
                        is_num(p[0]) and is_num(p[1])):
                    errors.append('%s: point %d is not [x, y] numbers'
                                  % (tag, pi))
                    break
        if s.get('marker') not in MARKERS:
            warnings.append('%s: unknown marker %r' % (tag, s.get('marker')))
    if kind == 'bar':
        cats, vals = s.get('categories'), s.get('values')
        if not (isinstance(cats, list) and cats and
                all(isinstance(c, str) for c in cats)):
            errors.append('%s: bar series needs string categories' % tag)
        if not (isinstance(vals, list) and vals and all(map(is_num, vals))):
            errors.append('%s: bar series needs numeric values' % tag)
        if isinstance(cats, list) and isinstance(vals, list) and \
                len(cats) != len(vals):
            errors.append('%s: categories (%d) and values (%d) length '
                          'mismatch' % (tag, len(cats), len(vals)))
        errs = s.get('errors')
        if errs is not None and not (isinstance(errs, list) and
                                     all(map(is_num, errs))):
            errors.append('%s: errors must be numbers' % tag)
        elif isinstance(errs, list) and isinstance(vals, list) and \
                len(errs) != len(vals):
            errors.append('%s: errors length must equal values length' % tag)
        if errs is not None and not s.get('error_semantics'):
            warnings.append('%s: error bars without error_semantics '
                            '(SD/SEM/CI95/unknown) — check the caption' % tag)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    errors, warnings = [], []
    try:
        spec = json.load(open(args.spec, encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({'valid': False, 'errors': ['unreadable spec: %s' % e],
                          'warnings': []}, ensure_ascii=False))
        raise SystemExit(2)

    if not isinstance(spec, dict):
        print(json.dumps({'valid': False, 'errors': ['spec must be an object'],
                          'warnings': []}))
        raise SystemExit(2)

    axes = spec.get('axes')
    if not isinstance(axes, dict) or 'x' not in axes or 'y' not in axes:
        errors.append('spec.axes must contain "x" and "y" axis objects')
    else:
        for name, ax in axes.items():
            if isinstance(ax, dict):
                check_axis(name, ax, errors, warnings)
            else:
                errors.append('axis %s must be an object' % name)

    series = spec.get('series')
    if not isinstance(series, list) or not series:
        errors.append('spec.series must be a non-empty list')
    else:
        names = [s.get('name') for s in series if isinstance(s, dict)]
        if len(names) != len(set(names)):
            errors.append('duplicate series names: %r' % names)
        for i, s in enumerate(series):
            if isinstance(s, dict):
                check_series(i, s, errors, warnings)
            else:
                errors.append('series[%d] must be an object' % i)

    for i, ann in enumerate(spec.get('annotations') or []):
        if not isinstance(ann, dict) or 'text' not in ann:
            errors.append('annotation %d needs a text field' % i)

    out = {'valid': not errors, 'errors': errors, 'warnings': warnings,
           'n_series': len(spec.get('series') or []),
           'chart_kinds': sorted({(s.get('kind') or 'line')
                                  for s in spec.get('series') or []
                                  if isinstance(s, dict)})}
    if not errors and args.out:
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        out['canonical'] = args.out
    print(json.dumps(out, ensure_ascii=False))
    if errors:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
