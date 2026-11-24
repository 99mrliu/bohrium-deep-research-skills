#!/usr/bin/env python3
"""Gate-controlled pipeline runner with checkpoints and honest failure.

The analysis plan is a JSON file written by the agent at runtime:
{
  "steps": [
    {"name": "G1_schema", "gate": "G1",
     "cmd": ["python3", "scripts/inspect.py", "..."],
     "produces": ["work/schema.json"]},
    ...
  ]
}
Each step runs as a subprocess with its stdout/stderr captured to a log.
A step passes its gate only when the command exits 0 AND every declared
product exists and is non-empty. State is checkpointed after every step:
re-running the script skips completed steps (resume after failure), and a
failed step leaves the pipeline in a documented state instead of a silent
half-finish. Gates G0-G4 are defined in references/gate_checklists.md.
Standard library only.

Usage:
  python gate.py --plan /app/work/plan.json --state /app/work/run_state.json \
      --logdir /app/work/logs
"""
import argparse
import json
import os
import subprocess
import sys
import time


def load_state(path):
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    return {'steps': {}, 'status': 'running'}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--plan', required=True)
    ap.add_argument('--state', required=True)
    ap.add_argument('--logdir', required=True)
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding='utf-8'))
    state = load_state(args.state)
    os.makedirs(args.logdir, exist_ok=True)
    failed = None
    for step in plan['steps']:
        name = step['name']
        if state['steps'].get(name, {}).get('status') == 'passed':
            print(json.dumps({'step': name, 'status': 'skipped (checkpoint)'}))
            continue
        t0 = time.time()
        log_path = os.path.join(args.logdir, name + '.log')
        with open(log_path, 'w', encoding='utf-8') as log:
            log.write('$ %s\n\n' % ' '.join(step['cmd']))
            proc = subprocess.run(step['cmd'], capture_output=True, text=True)
            log.write(proc.stdout)
            if proc.stderr:
                log.write('\n[stderr]\n' + proc.stderr)
        missing = [p for p in step.get('produces', [])
                   if not (os.path.exists(p) and os.path.getsize(p) > 0)]
        ok = proc.returncode == 0 and not missing
        state['steps'][name] = {
            'gate': step.get('gate'), 'status': 'passed' if ok else 'failed',
            'exit_code': proc.returncode, 'seconds': round(time.time() - t0, 3),
            'log': log_path,
            'missing_products': missing or None}
        state['status'] = 'running'
        json.dump(state, open(args.state, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print(json.dumps({'step': name, 'status': state['steps'][name]['status'],
                          'exit': proc.returncode, 'missing': missing or []},
                         ensure_ascii=False))
        if not ok:
            failed = name
            break
    if failed:
        state['status'] = 'failed_at_%s' % failed
        state['recovery'] = ('fix the failing step (see its log), then re-run '
                             'this script; completed steps resume from '
                             'checkpoint and are not re-executed')
    else:
        state['status'] = 'all_gates_passed'
    json.dump(state, open(args.state, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(json.dumps({'pipeline': state['status']}, ensure_ascii=False))
    return 0 if not failed else 2


if __name__ == '__main__':
    sys.exit(main())
