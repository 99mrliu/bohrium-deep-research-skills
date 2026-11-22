#!/usr/bin/env python3
"""Final delivery check for the render-proof pipeline.

Verifies, before the run ends:
- result.json carries the case's case_id and every output_contract field
  (contract parsed from list or dict shapes)
- status is honest; a partial result names its limits
- every declared artifact exists on disk
- the render report exists, and if its final status is not "pass" the
  result's uncertainty mentions the deviation table (no silent renders)

Usage:
    python final_check.py --case /input/case.json \
        --result /app/output/result.json \
        --render-report /app/output/render_report.json \
        --base /app --out final_check.json
"""
import argparse
import json
import os
import sys

STATUSES = {'success', 'partial', 'unable_to_determine', 'refused'}


def fields(contract):
    if isinstance(contract, dict):
        for k in ('fields', 'required', 'output_fields'):
            if k in contract:
                return fields(contract[k])
        return list(contract.keys())
    if isinstance(contract, list):
        out = []
        for it in contract:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(next((it[k] for k in ('name', 'field', 'key')
                                 if k in it), str(it)))
        return out
    return []


def paths_in(obj):
    if isinstance(obj, str):
        if obj.endswith(('.pptx', '.pdf', '.json', '.png')) or \
                obj.startswith('/'):
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from paths_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from paths_in(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', required=True)
    ap.add_argument('--result', required=True)
    ap.add_argument('--render-report', required=True)
    ap.add_argument('--base', default='/app')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    findings = []
    rec = lambda lvl, m: findings.append({'level': lvl, 'msg': m})
    case = json.load(open(args.case, encoding='utf-8'))
    result = json.load(open(args.result, encoding='utf-8'))

    cid = case.get('case_id') or case.get('id')
    if cid and result.get('case_id') != cid:
        rec('fail', 'case_id mismatch')
    missing = [f for f in fields(case.get('output_contract'))
               if f not in result]
    if missing:
        rec('fail', 'missing contract fields: %s' % missing)
    if result.get('status') not in STATUSES:
        rec('warn', 'status %r' % result.get('status'))
    if result.get('status') == 'partial' and not (
            result.get('uncertainty') or result.get('limitations')):
        rec('fail', 'partial result without stated limits')
    for p in sorted(set(paths_in(result.get('artifacts',
                                           result.get('outputs', {}))))):
        if p.startswith('http'):
            continue
        if not os.path.exists(p if os.path.isabs(p)
                              else os.path.join(args.base, p)):
            rec('fail', 'artifact missing: %s' % p)

    if not os.path.exists(args.render_report):
        rec('fail', 'render report missing: %s' % args.render_report)
    else:
        rr = json.load(open(args.render_report, encoding='utf-8'))
        if rr.get('status') != 'pass':
            unc = json.dumps(result.get('uncertainty', []),
                             ensure_ascii=False)
            if 'deviation' not in unc and 'render' not in unc \
                    and '渲染' not in unc:
                rec('fail', 'render report not clean but result.uncertainty '
                            'does not mention the render deviations')

    fails = [f for f in findings if f['level'] == 'fail']
    report = {'status': 'fail' if fails else 'pass', 'findings': findings}
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('final_check: %s (%d fail) -> %s'
          % (report['status'], len(fails), args.out))
    for f in findings:
        print('%s: %s' % (f['level'].upper(), f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
