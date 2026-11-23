#!/usr/bin/env python3
"""Gate 0: start a QC-gated figure-reading run (stdlib only).

Creates the run state and — most importantly — a VALID PARTIAL
result.json at the very first minute, containing case_id, every
output_contract field (null), and an honest "partial" status. From this
moment the case can never end with nothing submittable; later gates only
improve it.

Usage:
  python start_run.py --case /input/case.json --task /input/task.md \
      --work /app/work --out /app/output [--budget-seconds 900]
"""
import argparse
import json
import os
import time

GATES = {
    'g0': 'result-first skeleton written',
    'g1': 'input inventory complete (files, figures, tables, contract)',
    'g2': 'axis card validated (type vs tick geometry, units, >=3 ticks)',
    'g3': 'element ledger complete (series/points/errorbars/significance/'
          'scalebar accounted)',
    'g4': 'crosscheck done (figure vs tables vs caption/text)',
    'g5': 'output lint (units, locators, honest status)',
}


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
    ap.add_argument('--task', default='/input/task.md')
    ap.add_argument('--work', default='/app/work')
    ap.add_argument('--out', default='/app/output')
    ap.add_argument('--budget-seconds', type=int, default=900)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case = {}
    if os.path.exists(args.case):
        case = json.load(open(args.case, encoding='utf-8'))
    case_id = case.get('case_id') or case.get('caseId') or case.get('id')
    fields = contract_fields(case.get('output_contract') or {})

    state = {
        'case_id': case_id,
        'started_at': time.time(),
        'budget_seconds': args.budget_seconds,
        'contract_fields': fields,
        'gates': {g: {'status': 'pending', 'desc': d, 'checked_at': None,
                      'findings': []} for g, d in GATES.items()},
        'checkpoints': {'g1_by': 120, 'g2_by': 300, 'g3_by': 480,
                        'g4_by': 660, 'g5_by': 780,
                        'final_freeze_by': args.budget_seconds - 60},
    }
    state['gates']['g0']['status'] = 'pass'
    state['gates']['g0']['checked_at'] = time.time()
    state_path = os.path.join(args.work, 'run_state.json')
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    result = {'case_id': case_id, 'status': 'partial',
              'status_reason': 'run started; gates g1-g5 pending',
              'sources': [], 'uncertainty': []}
    for fld in fields:
        result.setdefault(fld, None)
    result_path = os.path.join(args.out, 'result.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        'run_state': state_path, 'result_skeleton': result_path,
        'case_id': case_id, 'contract_fields': fields,
        'next': 'g1: build /app/work/inventory.json, then run '
                'gate.py --gate 1',
        'time_checkpoints_seconds': state['checkpoints'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
