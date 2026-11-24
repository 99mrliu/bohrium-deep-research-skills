#!/usr/bin/env python3
"""run_case.py — driver for the transactional pipeline.

  init -> (model decisions.json) -> plan -> apply [--stop-after N] -> verify
       -> certify -> finalize ; undo available at any point after apply.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory import run_inventory, read_json, write_json  # noqa: E402
import build_result  # noqa: E402
import tx_engine  # noqa: E402


def log_change(work_dir, phase, note):
    path = os.path.join(work_dir, 'change_log.json')
    log = read_json(path) if os.path.isfile(path) else []
    log.append({'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                'phase': phase, 'note': note})
    write_json(path, log)


def cmd_init(args):
    case, records, aliases = run_inventory(args.input, args.work, args.out)
    build_result.write_partial(args.work, args.out, 'init')
    log_change(args.work, 'init',
               f"inventoried {len(records)} files; {len(aliases)} duplicate group(s); partial result written")
    print(json.dumps({'case_id': case['case_id'], 'files': len(records),
                      'alias_groups': len(aliases)}, ensure_ascii=False))


def cmd_plan(args):
    plan = tx_engine.build_plan(args.work, args.out)
    log_change(args.work, 'plan',
               f"plan {plan['plan_hash'][:12]}…: {len(plan['ops'])} ops, {len(plan['planned_skipped'])} planned skips")
    print(json.dumps({'plan_hash': plan['plan_hash'][:16], 'ops': len(plan['ops']),
                      'planned_skipped': len(plan['planned_skipped'])}, ensure_ascii=False))


def cmd_apply(args):
    rep = tx_engine.apply_plan(args.work, args.out, stop_after=args.stop_after)
    log_change(args.work, 'apply', json.dumps(rep, ensure_ascii=False))
    print(json.dumps(rep, ensure_ascii=False))
    if rep.get('interrupted'):
        sys.exit(3)  # simulated crash: non-zero exit, journal is consistent


def cmd_verify(args):
    rep = tx_engine.verify(args.work, args.out)
    log_change(args.work, 'verify', f"ok={rep['ok']} problems={len(rep['problems'])}")
    print(json.dumps({'ok': rep['ok'], 'problems': len(rep['problems'])}, ensure_ascii=False))


def cmd_certify(args):
    cert = tx_engine.certify(args.work, args.out)
    log_change(args.work, 'certify',
               f"granted={cert['granted']} fp={cert['first_run']['fingerprint'][:12]}…")
    print(json.dumps({'granted': cert['granted'],
                      'fingerprint': cert['first_run']['fingerprint'][:16]}, ensure_ascii=False))


def cmd_undo(args):
    log = tx_engine.undo(args.work, args.out)
    log_change(args.work, 'undo', f"removed {len(log['removed'])} files; rolled_back={log['rolled_back']}")
    print(json.dumps({'removed': len(log['removed']), 'rolled_back': log['rolled_back']},
                     ensure_ascii=False))


def cmd_finalize(args):
    verify = read_json(os.path.join(args.out, 'verify_report.json')) \
        if os.path.isfile(os.path.join(args.out, 'verify_report.json')) else {'ok': False, 'problems': ['verify never run']}
    cert = read_json(os.path.join(args.out, 'idempotency_certificate.json')) \
        if os.path.isfile(os.path.join(args.out, 'idempotency_certificate.json')) else {'granted': False}
    result = build_result.assemble_final(args.work, args.out, verify, cert)
    log_change(args.work, 'finalize', f"status={result['status']}")
    print(json.dumps({'status': result['status'],
                      'indexed': len(result['library_index'] or []),
                      'skipped': len(result['skipped'] or [])}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='idempotent-rerun-controller driver')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def add(name, fn, extra=False):
        p = sub.add_parser(name)
        if name == 'init':
            p.add_argument('--input', required=True)
        p.add_argument('--work', required=True)
        p.add_argument('--out', required=True)
        if extra:
            p.add_argument('--stop-after', type=int, default=None)
        p.set_defaults(fn=fn)

    add('init', cmd_init)
    add('plan', cmd_plan)
    add('apply', cmd_apply, extra=True)
    add('verify', cmd_verify)
    add('certify', cmd_certify)
    add('undo', cmd_undo)
    add('finalize', cmd_finalize)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
