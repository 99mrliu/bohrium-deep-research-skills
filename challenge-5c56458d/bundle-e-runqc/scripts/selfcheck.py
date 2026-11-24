#!/usr/bin/env python3
"""Pre-submission self-audit: does /app/output satisfy the contract?

Checks (each one printed with evidence):
  C1 result.json exists and parses;
  C2 case_id present and matches case.json;
  C3 every output_contract field is present;
  C4 no field still holds the bare placeholder "unable_to_determine" without
     an accompanying explanation (limitations/exceptions field or notes);
  C5 status is "complete" or an honestly labelled "partial" with limits;
  C6 every file path referenced inside result.json exists under the output
     directory;
  C7 analysis notes exist.
Verdict: GO (all hard checks pass) or NO-GO with the blocking list.
Standard library only.

Usage:
  python selfcheck.py --case /input/case.json --outdir /app/output \
      --out /app/work/selfcheck.json --md /app/work/selfcheck.md
"""
import argparse
import json
import os
import re
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
    ap.add_argument('--out', required=True)
    ap.add_argument('--md')
    args = ap.parse_args()
    checks = []
    blocking = []

    def record(cid, ok, detail, hard=True):
        checks.append({'check': cid, 'ok': ok, 'detail': detail})
        if hard and not ok:
            blocking.append('%s: %s' % (cid, detail))

    case = json.load(open(args.case, encoding='utf-8'))
    exp_id = find_key(case, 'case_id') or find_key(case, 'id')
    fields = contract_fields(find_key(case, 'output_contract'))
    rpath = os.path.join(args.outdir, 'result.json')
    if not os.path.exists(rpath):
        record('C1', False, 'result.json missing in %s' % args.outdir)
        result = {}
    else:
        try:
            result = json.load(open(rpath, encoding='utf-8'))
            record('C1', True, 'result.json parses')
        except json.JSONDecodeError as exc:
            record('C1', False, 'invalid JSON: %s' % exc)
            result = {}
    record('C2', bool(result.get('case_id')) and
           (exp_id is None or result.get('case_id') == exp_id),
           'case_id=%r expected=%r' % (result.get('case_id'), exp_id))
    missing = [f for f in fields if f not in result]
    record('C3', not missing, 'missing contract fields: %s' % missing or 'none')
    bare = [f for f in fields
            if result.get(f) == PLACEHOLDER]
    explained = bool(result.get('limitations') or result.get('exceptions')
                     or result.get('uncertainty'))
    record('C4', not (bare and not explained),
           'unexplained placeholders: %s' % bare if bare else 'none')
    status = result.get('status')
    record('C5', status in ('complete', 'partial'),
           'status=%r' % status)
    if status == 'partial' and not result.get('limitations'):
        record('C5b', False, 'partial status without limitations statement')
    refs = set(re.findall(r'"([^"]+\.(?:csv|png|md|json|jsonl|pdf))"',
                          json.dumps(result, ensure_ascii=False)))
    bad_refs = [r for r in refs if not r.startswith(('http', '/'))
                and not os.path.exists(os.path.join(args.outdir, r))]
    bad_abs = [r for r in refs if r.startswith('/') and not os.path.exists(r)]
    record('C6', not bad_refs and not bad_abs,
           'dangling file references: %s' % (bad_refs + bad_abs)
           if (bad_refs or bad_abs) else 'all referenced files exist',
           hard=False)
    notes = [f for f in os.listdir(args.outdir)
             if 'note' in f.lower() or 'readme' in f.lower()] \
        if os.path.isdir(args.outdir) else []
    record('C7', bool(notes), 'notes files: %s' % notes or 'none', hard=False)

    verdict = 'GO' if not blocking else 'NO-GO'
    report = {'verdict': verdict, 'blocking': blocking, 'checks': checks,
              'outdir': args.outdir}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(report, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    if args.md:
        lines = ['# Self-check: %s' % verdict, '']
        for c in checks:
            lines.append('- [%s] %s — %s' % ('PASS' if c['ok'] else 'FAIL',
                                             c['check'], c['detail']))
        if blocking:
            lines += ['', '## Blocking', ''] + ['- ' + b for b in blocking]
        open(args.md, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({'verdict': verdict, 'blocking': blocking},
                     ensure_ascii=False))
    return 0 if verdict == 'GO' else 2


if __name__ == '__main__':
    sys.exit(main())
