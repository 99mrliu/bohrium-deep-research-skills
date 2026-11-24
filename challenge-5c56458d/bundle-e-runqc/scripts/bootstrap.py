#!/usr/bin/env python3
"""Write the honest-partial result.json skeleton required by the contract.

Reads /input/case.json, extracts case_id and output_contract (both are
searched recursively because case layouts vary), and writes
/app/output/result.json with status="partial", every contract field present
with an explicit "unable_to_determine" placeholder, and a progress note.
This guarantees a gradeable deliverable exists from minute one; later steps
replace placeholders with real values and flip status to "complete".
Standard library only.

Usage:
  python bootstrap.py --case /input/case.json --outdir /app/output
"""
import argparse
import json
import os
import sys

PLACEHOLDER = 'unable_to_determine'


def find_key(obj, name):
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        for v in obj.values():
            r = find_key(v, name)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, name)
            if r is not None:
                return r
    return None


def contract_fields(spec):
    """Normalize output_contract (list or dict) to an ordered field list."""
    if isinstance(spec, list):
        return [f if isinstance(f, str) else f.get('name', str(f))
                for f in spec]
    if isinstance(spec, dict):
        if 'fields' in spec:
            return contract_fields(spec['fields'])
        return list(spec.keys())
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--case', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()
    case = json.load(open(args.case, encoding='utf-8'))
    case_id = find_key(case, 'case_id') or find_key(case, 'id')
    contract = find_key(case, 'output_contract')
    fields = contract_fields(contract)
    result = {'case_id': case_id if case_id is not None else PLACEHOLDER,
              'status': 'partial',
              'skill': 'run-gate-keeper',
              'progress': ('bootstrap: contract skeleton written before any '
                           'analysis; placeholders will be replaced by real '
                           'results as gates pass'),
              'limitations': 'no analysis has run yet at bootstrap time'}
    for f in fields:
        if f not in result:
            result[f] = PLACEHOLDER
    os.makedirs(args.outdir, exist_ok=True)
    out = os.path.join(args.outdir, 'result.json')
    json.dump(result, open(out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'result': out, 'case_id': result['case_id'],
                      'contract_fields': fields}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
