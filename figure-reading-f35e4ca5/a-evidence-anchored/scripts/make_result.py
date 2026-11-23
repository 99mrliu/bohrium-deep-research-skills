#!/usr/bin/env python3
"""Assemble the contract-complete result.json from provenance-tagged claims.

Usage:
  python make_result.py --case /input/case.json \
      --fragment /app/work/result_fragment.json \
      --claims /app/work/claims.json \
      --out /app/output/result.json --status success

Claims file (optional): a JSON list of
  {"claim": str, "value": number|str, "unit": str|null,
   "evidence": [{"source_type": "table_cell|figure_region|caption_verbatim|"
                 "text_sentence|derived",
                 "locator": str, "verbatim": str}],
   "crosscheck": "matched|unmatched|no_anchor"}

Rules enforced here, not by convention:
  * a claim may carry status success only if every claim has >=1 evidence
    record with a non-empty locator;
  * claims whose crosscheck is "unmatched" are copied into
    result.uncertainty, never silently dropped;
  * "success" requires every contract field non-null (auto-downgraded to
    partial otherwise);
  * nothing is invented: fields absent from the fragment keep their
    previous value or null.
"""
import argparse
import json
import os
import sys

SOURCE_TYPES = {'table_cell', 'figure_region', 'caption_verbatim',
                'text_sentence', 'derived'}


def contract_fields(contract):
    fields = []
    if isinstance(contract, dict):
        for k, v in contract.items():
            fields.append(k)
            sub = v.get('fields') if isinstance(v, dict) else None
            if isinstance(sub, dict):
                fields.extend(sub.keys())
            elif isinstance(sub, list):
                fields.extend(contract_fields(sub))
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get('name') or item.get('field') or item.get('key')
                if name:
                    fields.append(name)
    seen, out = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def validate_claims(claims):
    problems = []
    for i, c in enumerate(claims):
        ev = c.get('evidence') or []
        if not ev:
            problems.append('claim %d (%r) has no evidence record' %
                            (i, c.get('claim')))
            continue
        for e in ev:
            if not e.get('locator'):
                problems.append('claim %d (%r): evidence without locator'
                                % (i, c.get('claim')))
            st = e.get('source_type')
            if st not in SOURCE_TYPES:
                problems.append('claim %d (%r): unknown source_type %r'
                                % (i, c.get('claim'), st))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', default='/input/case.json')
    ap.add_argument('--fragment', default=None)
    ap.add_argument('--claims', default=None)
    ap.add_argument('--out', default='/app/output/result.json')
    ap.add_argument('--status', default=None,
                    choices=['success', 'partial', 'unable_to_determine',
                             'refused'])
    ap.add_argument('--status-reason', default=None)
    args = ap.parse_args()

    case = {}
    if os.path.exists(args.case):
        case = json.load(open(args.case, encoding='utf-8'))
    case_id = case.get('case_id') or case.get('caseId') or case.get('id')
    fields = contract_fields(case.get('output_contract') or {})

    result = {}
    if os.path.exists(args.out):
        result = json.load(open(args.out, encoding='utf-8'))
    result.setdefault('case_id', case_id)

    fragment = {}
    if args.fragment:
        fragment = json.load(open(args.fragment, encoding='utf-8'))
    if not isinstance(fragment, dict):
        raise SystemExit('fragment must be a JSON object')
    result.update(fragment)
    for fld in fields:
        result.setdefault(fld, result.get(fld))

    claims = []
    if args.claims and os.path.exists(args.claims):
        claims = json.load(open(args.claims, encoding='utf-8'))
    if claims:
        problems = validate_claims(claims)
        result['provenance_records'] = claims
        unmatched = [c for c in claims if c.get('crosscheck') == 'unmatched']
        uncer = result.get('uncertainty') or []
        for c in unmatched:
            note = 'unverified reading: %s (value %s %s) — no table match' % (
                c.get('claim'), c.get('value'), c.get('unit') or '')
            if note not in uncer:
                uncer.append(note)
        result['uncertainty'] = uncer
        if problems:
            prev = result.get('uncertainty') or []
            prev.extend('claim problem: %s' % p for p in problems)
            result['uncertainty'] = prev
            if args.status == 'success':
                print('claims have problems; refusing success status',
                      file=sys.stderr)
                args.status = 'partial'

    if args.status:
        result['status'] = args.status
    if args.status_reason:
        result['status_reason'] = args.status_reason
    elif args.status and 'skeleton' in str(result.get('status_reason', '')):
        result.pop('status_reason', None)
    result.setdefault('status', 'partial')
    result.setdefault('sources', [])
    result.setdefault('uncertainty', [])

    missing = [f for f in fields if result.get(f) is None]
    if result['status'] == 'success' and missing:
        print('WARNING: success with null contract fields: %s; '
              'downgrading to partial' % ', '.join(missing), file=sys.stderr)
        result['status'] = 'partial'
        result['status_reason'] = ('auto-downgraded: unfilled contract '
                                   'fields: ' + ', '.join(missing))

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'written': args.out, 'case_id': result.get('case_id'),
                      'status': result['status'],
                      'claims': len(claims),
                      'null_contract_fields': missing}, ensure_ascii=False))


if __name__ == '__main__':
    main()
