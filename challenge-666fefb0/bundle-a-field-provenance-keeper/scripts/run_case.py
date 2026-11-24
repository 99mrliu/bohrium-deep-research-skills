#!/usr/bin/env python3
"""run_case.py — driver: init -> (model decisions) -> lint -> finalize.

  python3 run_case.py init     --input /input --work /app/work --out /app/output
  python3 run_case.py lint     --work /app/work
  python3 run_case.py finalize --work /app/work --out /app/output

Input tree is never modified. Apply is idempotent: completed ops whose target
hash verifies are skipped on re-run; name collisions never overwrite.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory import run_inventory, read_json, write_json, sha256_of  # noqa: E402
import build_result  # noqa: E402
import provenance_lint  # noqa: E402

BAD_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def sanitize_name(name, cap=120):
    name = BAD_CHARS.sub('-', str(name or 'untitled'))
    name = re.sub(r'\s+', ' ', name).strip(' .-') or 'untitled'
    return name[:cap]


def log_change(work_dir, phase, note):
    path = os.path.join(work_dir, 'change_log.json')
    log = read_json(path) if os.path.isfile(path) else []
    log.append({'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                'phase': phase, 'note': note})
    write_json(path, log)


def cmd_init(args):
    case, records, aliases = run_inventory(args.input, args.work, args.out)
    build_result.write_partial(args.input, args.work, args.out, 'init')
    log_change(args.work, 'init',
               f"inventoried {len(records)} files from {case['library_dir']}; {len(aliases)} duplicate group(s); partial result.json written")
    print(json.dumps({'case_id': case['case_id'], 'files': len(records),
                      'alias_groups': len(aliases)}, ensure_ascii=False))


def cmd_lint(args):
    report, conflicts = provenance_lint.run_lint(args.work)
    log_change(args.work, 'lint',
               f"anchor lint: {report['passed']}/{report['checked']} passed, {len(report['downgraded'])} downgraded")
    print(json.dumps({'checked': report['checked'], 'passed': report['passed'],
                      'downgraded': len(report['downgraded'])}, ensure_ascii=False))


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def cmd_finalize(args):
    work, out = args.work, args.out
    case = read_json(os.path.join(work, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work, 'files.jsonl'))}
    dec_path = os.path.join(work, 'decisions.linted.json')
    if not os.path.isfile(dec_path):
        dec_path = os.path.join(work, 'decisions.json')
    decisions = read_json(dec_path)
    sidecars = read_json(os.path.join(work, 'sidecars.json')) if os.path.isfile(os.path.join(work, 'sidecars.json')) else []

    lib_out = os.path.join(out, 'library')
    os.makedirs(lib_out, exist_ok=True)
    journal_path = os.path.join(out, 'operations.jsonl')
    done = {}
    for o in load_jsonl(journal_path):
        if o.get('status') in ('copied', 'verified_skip') and o.get('dst'):
            done[o['fid']] = o

    ops_new, assigned, skipped = [], set(), []
    assignments = decisions.get('assignments', [])
    for a in assignments:
        fid = a.get('fid')
        if fid in files:
            assigned.add(fid)

    for a in assignments:
        fid = a.get('fid')
        rec = files.get(fid)
        if not rec:
            continue
        disposition = a.get('disposition', 'keep')
        if not rec.get('readable'):
            skipped.append({'fid': fid, 'rel': rec['rel'], 'reason': rec.get('extract_status') or 'unreadable',
                            'recovery': 'fix permissions or restore file, then re-run'})
            continue
        if rec.get('extract_status') in ('extract_error', 'no_text_layer', 'binary_no_extract') and disposition == 'keep':
            skipped.append({'fid': fid, 'rel': rec['rel'], 'reason': rec['extract_status'],
                            'recovery': 'repair file / run OCR externally, then re-run with an assignment'})
            continue
        src = os.path.join(case['library_dir'], rec['rel'])
        ext = os.path.splitext(rec['rel'])[1]
        if disposition == 'archive_dup':
            dst_rel = os.path.join('_archive_dups', sanitize_name(a.get('new_name') or os.path.basename(rec['rel'])) + ext)
        else:
            cat = sanitize_name(a.get('category') or 'unsorted')
            sub = sanitize_name(a.get('subcategory') or 'undated')
            dst_rel = os.path.join(cat, sub, sanitize_name(a.get('new_name')) + ext)
        dst = os.path.join(lib_out, dst_rel)
        op = {'op_id': f"op-{fid}", 'fid': fid, 'src': rec['rel'], 'src_sha256': rec.get('sha256'),
              'dst_rel': dst_rel, 'dst': dst, 'disposition': disposition,
              'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
        prev = done.get(fid)
        if prev and os.path.isfile(prev['dst']) and sha256_of(prev['dst']) == rec.get('sha256'):
            op.update(status='verified_skip', dst=prev['dst'], dst_rel=prev['dst_rel'],
                      dst_sha256=prev.get('dst_sha256'))
            ops_new.append(op)
            continue
        if os.path.isfile(dst):
            if sha256_of(dst) == rec.get('sha256'):
                op.update(status='copied', dst_sha256=rec.get('sha256'), note='already present, identical')
                ops_new.append(op)
                continue
            base, e2 = os.path.splitext(dst)
            n = 2
            while os.path.isfile(f'{base}-{n}{e2}'):
                n += 1
            dst = f'{base}-{n}{e2}'
            op.update(dst=dst, dst_rel=os.path.relpath(dst, lib_out), status='conflict_renamed',
                      note='target existed with different content; suffixed, nothing overwritten')
        else:
            op['status'] = 'copied'
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        op['dst_sha256'] = sha256_of(dst)
        ops_new.append(op)

    admin_dir = os.path.join(lib_out, '00-admin')
    for sc in sidecars:
        rec = files.get(sc['fid'])
        if not rec or not rec.get('readable') or sc['fid'] in assigned:
            continue
        assigned.add(sc['fid'])
        os.makedirs(admin_dir, exist_ok=True)
        dst = os.path.join(admin_dir, os.path.basename(rec['rel']))
        if not os.path.isfile(dst) or sha256_of(dst) != rec.get('sha256'):
            shutil.copy2(os.path.join(case['library_dir'], rec['rel']), dst)
        ops_new.append({'op_id': f"op-{sc['fid']}", 'fid': sc['fid'], 'src': rec['rel'],
                        'src_sha256': rec.get('sha256'), 'dst_rel': os.path.relpath(dst, lib_out),
                        'dst': dst, 'dst_sha256': sha256_of(dst), 'disposition': 'sidecar_admin',
                        'status': 'copied',
                        'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')})

    for fid, rec in files.items():
        if fid not in assigned:
            skipped.append({'fid': fid, 'rel': rec['rel'],
                            'reason': rec.get('extract_status') if not rec.get('readable') or rec.get('extract_status') in ('extract_error', 'no_text_layer', 'permission_denied', 'read_error') else 'no_assignment',
                            'recovery': 'add an assignment in decisions.json and re-run finalize'})

    with open(journal_path, 'w', encoding='utf-8') as f:
        for op in ops_new:
            entry = dict(op)
            entry['dst_present'] = os.path.isfile(op['dst'])
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    problems = []
    for op in ops_new:
        if op['status'] in ('copied', 'verified_skip', 'conflict_renamed'):
            if not os.path.isfile(op['dst']):
                problems.append({'fid': op['fid'], 'problem': 'dst missing'})
            elif sha256_of(op['dst']) != op.get('dst_sha256'):
                problems.append({'fid': op['fid'], 'problem': 'dst hash mismatch'})
    covered = {o['fid'] for o in ops_new} | {s['fid'] for s in skipped}
    for fid in files:
        if fid not in covered:
            problems.append({'fid': fid, 'problem': 'uncovered input file'})
    verify = {'ok': not problems, 'problems': problems,
              'checked_ops': len(ops_new), 'inputs': len(files),
              'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
    write_json(os.path.join(out, 'verify_report.json'), verify)
    write_json(os.path.join(work, 'skipped.json'), skipped)
    log_change(work, 'finalize',
               f"applied {len(ops_new)} ops ({sum(1 for o in ops_new if o['status']=='conflict_renamed')} conflict-renamed), skipped {len(skipped)}, verify ok={verify['ok']}")

    result = build_result.assemble_final(work, out, verify)
    print(json.dumps({'status': result['status'], 'ops': len(ops_new),
                      'skipped': len(skipped), 'verify_ok': verify['ok']}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='field-provenance-keeper driver')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('--input', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser('lint')
    p.add_argument('--work', required=True)
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser('finalize')
    p.add_argument('--work', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
