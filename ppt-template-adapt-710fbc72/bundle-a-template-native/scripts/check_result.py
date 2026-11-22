#!/usr/bin/env python3
"""Validate /app/output/result.json against the case's output_contract.

Reads /input/case.json, extracts the required output fields (from
output_contract in whatever shape the organizer used: list of names, list of
objects with name/key/field, or dict of name->spec), and checks that
result.json contains every one of them plus the original case_id, that the
declared artifact paths exist, and that status is one of the honest values.

Usage:
    python check_result.py --case /input/case.json \
        --result /app/output/result.json --base /app \
        --out result_check.json
Exit 0 when the contract is satisfied.
"""
import argparse
import json
import os
import sys

VALID_STATUS = {'success', 'partial', 'unable_to_determine', 'refused'}


def required_fields(contract):
    if contract is None:
        return []
    if isinstance(contract, dict):
        for key in ('fields', 'required', 'output_fields', 'properties'):
            if key in contract:
                return required_fields(contract[key])
        return list(contract.keys())
    if isinstance(contract, list):
        out = []
        for item in contract:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for key in ('name', 'field', 'key', 'id'):
                    if key in item:
                        out.append(item[key])
                        break
        return out
    return []


def iter_paths(obj):
    """Yield values that look like artifact file paths."""
    if isinstance(obj, str):
        if '/' in obj and not obj.startswith('http') and len(obj) < 300:
            yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('path', 'file', 'pptx', 'pdf', 'previews', 'report') \
               or isinstance(v, (dict, list)):
                yield from iter_paths(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_paths(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', required=True)
    ap.add_argument('--result', required=True)
    ap.add_argument('--base', default='/app')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    case = json.load(open(args.case, encoding='utf-8'))
    result = json.load(open(args.result, encoding='utf-8'))
    findings = []

    def rec(level, msg):
        findings.append({'level': level, 'msg': msg})

    cid = case.get('case_id') or case.get('id')
    if cid and result.get('case_id') != cid:
        rec('fail', 'case_id mismatch: case=%r result=%r'
            % (cid, result.get('case_id')))
    fields = required_fields(case.get('output_contract'))
    missing = [f for f in fields if f not in result]
    if missing:
        rec('fail', 'output_contract fields missing: %s' % missing)
    status = result.get('status')
    if status not in VALID_STATUS:
        rec('warn', 'status %r not in %s' % (status, sorted(VALID_STATUS)))
    if status == 'partial' and not (result.get('limitations')
                                    or result.get('uncertainty')):
        rec('fail', 'partial result must state its limits/uncertainty')
    checked, absent = 0, []
    for p in set(iter_paths(result.get('artifacts',
                                       result.get('outputs', {})))):
        full = p if os.path.isabs(p) else os.path.join(args.base, p)
        checked += 1
        if not os.path.exists(full):
            absent.append(p)
    for p in absent:
        rec('fail', 'declared artifact missing on disk: %s' % p)
    if checked == 0:
        rec('warn', 'no artifact paths found to verify')

    fails = [f for f in findings if f['level'] == 'fail']
    report = {'status': 'fail' if fails else 'pass',
              'required_fields': fields, 'findings': findings}
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('result_check: %s (%d fail) -> %s'
          % (report['status'], len(fails), args.out))
    for f in findings:
        print('%s: %s' % (f['level'].upper(), f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
