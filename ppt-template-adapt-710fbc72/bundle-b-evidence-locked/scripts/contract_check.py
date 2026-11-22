#!/usr/bin/env python3
"""Final gate: result.json honors the case output_contract AND the evidence
map covers every slide of the deck.

Checks:
1. result.json exists, parses, and its case_id equals the case's case_id.
2. Every field named by output_contract (list of names, list of objects, or
   dict shape) is present in result.json.
3. status is one of success/partial/unable_to_determine/refused; a partial
   result names its limits.
4. Declared artifact files exist on disk (under --base for relative paths).
5. evidence_map.json has an entry for every slide in deck.pptx, and no
   source entry is left with status other than "verified" unless the result
   lists it under uncertainty.

Usage:
    python contract_check.py --case /input/case.json \
        --result /app/output/result.json --deck /app/output/deck.pptx \
        --evidence-map /app/output/evidence_map.json --base /app \
        --out contract_check.json
"""
import argparse
import json
import os
import sys

from pptx import Presentation

STATUSES = {'success', 'partial', 'unable_to_determine', 'refused'}


def contract_fields(contract):
    if isinstance(contract, dict):
        for k in ('fields', 'required', 'output_fields'):
            if k in contract:
                return contract_fields(contract[k])
        return list(contract.keys())
    if isinstance(contract, list):
        out = []
        for it in contract:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(next((it[k] for k in ('name', 'field', 'key', 'id')
                                 if k in it), json.dumps(it)))
        return out
    return []


def artifact_strings(obj):
    if isinstance(obj, str):
        if obj.startswith('/') or obj.endswith(
                ('.pptx', '.pdf', '.json', '.png', '.md')):
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from artifact_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from artifact_strings(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', required=True)
    ap.add_argument('--result', required=True)
    ap.add_argument('--deck', required=True)
    ap.add_argument('--evidence-map', required=True)
    ap.add_argument('--base', default='/app')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    findings = []
    rec = lambda lvl, msg: findings.append({'level': lvl, 'msg': msg})

    case = json.load(open(args.case, encoding='utf-8'))
    result = json.load(open(args.result, encoding='utf-8'))
    cid = case.get('case_id') or case.get('id')
    if cid and result.get('case_id') != cid:
        rec('fail', 'case_id mismatch (%r vs %r)' % (cid,
                                                     result.get('case_id')))
    fields = contract_fields(case.get('output_contract'))
    missing = [f for f in fields if f not in result]
    if missing:
        rec('fail', 'missing output_contract fields: %s' % missing)
    if result.get('status') not in STATUSES:
        rec('warn', 'unusual status %r' % result.get('status'))
    if result.get('status') == 'partial' and not (
            result.get('uncertainty') or result.get('limitations')):
        rec('fail', 'partial result without stated limits')
    for p in sorted(set(artifact_strings(
            result.get('artifacts', result.get('outputs', {}))))):
        if p.startswith('http'):
            continue
        full = p if os.path.isabs(p) else os.path.join(args.base, p)
        if not os.path.exists(full):
            rec('fail', 'artifact missing on disk: %s' % p)

    n_slides = len(Presentation(args.deck).slides._sldIdLst)
    emap = json.load(open(args.evidence_map, encoding='utf-8'))
    covered = {e['slide'] for e in emap}
    uncovered = [i for i in range(1, n_slides + 1) if i not in covered]
    if uncovered:
        rec('fail', 'evidence map misses slides %s' % uncovered)
    unc_txt = json.dumps(result.get('uncertainty', []), ensure_ascii=False)
    for e in emap:
        for s in e.get('sources', []):
            if s.get('status') not in (None, 'verified'):
                tag = '%s %s' % (s.get('kind', ''), s.get('ref', ''))
                if tag.strip() and tag.split()[-1] not in unc_txt:
                    rec('warn', 'slide %d source %s status=%s not echoed in '
                                'uncertainty' % (e['slide'], tag,
                                                 s.get('status')))

    fails = [f for f in findings if f['level'] == 'fail']
    report = {'status': 'fail' if fails else 'pass', 'findings': findings,
              'slides': n_slides, 'evidence_entries': len(emap)}
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('contract_check: %s (%d fail, %d warn) -> %s'
          % (report['status'], len(fails), len(findings) - len(fails),
             args.out))
    for f in findings:
        print('%s: %s' % (f['level'].upper(), f['msg']))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
