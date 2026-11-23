#!/usr/bin/env python3
"""Assemble the contract-complete result.json for redraw-proof reading.

Usage:
  python make_result.py --case /input/case.json \
      --fragment /app/work/result_fragment.json \
      --metrics /app/output/verify.metrics.json \
      --out /app/output/result.json --status success

Honesty rules enforced here:
  * status "success" requires every output_contract field non-null
    (otherwise auto-downgraded to partial);
  * if --metrics is given and its verdict is "rejected", success is
    refused: the reconstruction did not reproduce the figure, so the
    extracted data cannot be claimed correct;
  * fields absent from the fragment keep their previous value or null —
    nothing is invented.
"""
import argparse
import json
import os
import sys


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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', default='/input/case.json')
    ap.add_argument('--fragment', default=None)
    ap.add_argument('--metrics', default=None)
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

    if args.metrics and os.path.exists(args.metrics):
        m = json.load(open(args.metrics, encoding='utf-8'))
        result['verification'] = {
            'method': 'reconstruction overlay diff',
            'ink_recall': m.get('ink_recall'),
            'ink_precision': m.get('ink_precision'),
            'verdict': m.get('verdict'),
            'diff_png': m.get('diff_png'),
            'per_series_recall': m.get('per_series_recall'),
        }
        if m.get('verdict') == 'rejected' and args.status == 'success':
            print('verification verdict is rejected; refusing success '
                  'status — fix the spec or report partial', file=sys.stderr)
            args.status = 'partial'
            args.status_reason = ('reconstruction diff rejected the '
                                  'readings; see verification.verdict')

    if args.status:
        result['status'] = args.status
    if args.status_reason:
        result['status_reason'] = args.status_reason
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
                      'null_contract_fields': missing}, ensure_ascii=False))


if __name__ == '__main__':
    main()
