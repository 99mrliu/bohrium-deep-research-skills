#!/usr/bin/env python3
"""Finalize a QC-gated run: honest status from gate evidence (stdlib).

Computes the deliverable status FROM THE GATES, never from intention:

  success  — all gates g0-g5 pass and no contract field is null
  partial  — some gate failed or fields are null; the status_reason names
             the first failing gate and the null fields
  unable_to_determine — only when the material genuinely cannot answer

Writes/updates /app/output/result.json and emits run_report.md (timeline,
per-gate findings, budget usage, limitations) into /app/output — the
process-quality evidence that ships with the answer.

Usage:
  python finalize.py --work /app/work --out /app/output \
      --case /input/case.json [--claim-status success]
"""
import argparse
import json
import os
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', default='/app/work')
    ap.add_argument('--out', default='/app/output')
    ap.add_argument('--case', default='/input/case.json')
    ap.add_argument('--claim-status', default=None,
                    help='status the agent believes is earned; the gates '
                         'decide what actually ships')
    args = ap.parse_args()

    state = json.load(open(os.path.join(args.work, 'run_state.json'),
                           encoding='utf-8'))
    result_path = os.path.join(args.out, 'result.json')
    result = json.load(open(result_path, encoding='utf-8'))
    fields = state.get('contract_fields') or []
    nulls = [f for f in fields if result.get(f) is None]

    gates = state.get('gates', {})
    failing = [g for g in ('g0', 'g1', 'g2', 'g3', 'g4', 'g5')
               if gates.get(g, {}).get('status') == 'fail']
    pending = [g for g in ('g1', 'g2', 'g3', 'g4', 'g5')
               if gates.get(g, {}).get('status') not in ('pass', 'fail')]

    if not failing and not pending and not nulls:
        decided = 'success'
        reason = None
    else:
        decided = 'partial'
        bits = []
        if failing:
            bits.append('failing gates: %s' % ', '.join(failing))
        if pending:
            bits.append('gates never checked: %s' % ', '.join(pending))
        if nulls:
            bits.append('null contract fields: %s' % ', '.join(nulls))
        reason = '; '.join(bits)

    if args.claim_status and args.claim_status != decided:
        print('claimed %r but gates decide %r (%s)'
              % (args.claim_status, decided, reason))
    result['status'] = decided
    if reason:
        result['status_reason'] = reason
    else:
        result.pop('status_reason', None)
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - state.get('started_at', time.time())
    budget = state.get('budget_seconds', 900)
    lines = ['# QC-gated figure-reading run report', '',
             '- case_id: %s' % state.get('case_id'),
             '- decided status: **%s**%s' % (decided,
                                             (' — ' + reason) if reason else ''),
             '- elapsed: %.0f s of %d s budget' % (elapsed, budget), '',
             '## Gates', '']
    for g in ('g0', 'g1', 'g2', 'g3', 'g4', 'g5'):
        info = gates.get(g, {})
        lines.append('- %s: %s%s' % (
            g, info.get('status', 'pending'),
            (' — ' + info.get('desc', '')) if info.get('desc') else ''))
        for f_ in info.get('findings', []):
            lines.append('  - [%s] %s: %s' % (f_['level'], f_['check'],
                                              f_['detail']))
    lines += ['', '## Limitations',
              '',
              'See result.json `uncertainty` for itemized limits; every '
              'unreadable element carries its reason in the element '
              'ledger (work/element_ledger.json).']
    report = os.path.join(args.out, 'run_report.md')
    with open(report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(json.dumps({'decided_status': decided, 'reason': reason,
                      'result': result_path, 'run_report': report,
                      'elapsed_s': round(elapsed, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
