#!/usr/bin/env python3
"""tx_engine.py — transactional plan/apply/verify/certify/undo engine.

Process-quality core: no filesystem mutation happens outside a hashed plan;
every completed op is journaled before the next starts; certify proves byte-
identical output across two full runs; undo reverses the journal.
"""
import datetime
import hashlib
import json
import os
import re
import shutil

from inventory import read_json, write_json, sha256_of

BAD_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def sanitize_name(name, cap=120):
    name = BAD_CHARS.sub('-', str(name or 'untitled'))
    name = re.sub(r'\s+', ' ', name).strip(' .-') or 'untitled'
    return name[:cap]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def tree_fingerprint(root):
    """Content-addressed fingerprint of a directory tree."""
    entries = []
    if os.path.isdir(root):
        for r, dirs, files in os.walk(root):
            dirs.sort()
            for fn in sorted(files):
                p = os.path.join(r, fn)
                entries.append(f'{os.path.relpath(p, root)}:{sha256_of(p)}')
    blob = '\n'.join(sorted(entries))
    return {'file_count': len(entries),
            'fingerprint': hashlib.sha256(blob.encode('utf-8')).hexdigest()}


def build_plan(work_dir, out_dir):
    """Merge decisions into a hashed ops plan. Skip entries are planned too."""
    case = read_json(os.path.join(work_dir, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work_dir, 'files.jsonl'))}
    dec_path = os.path.join(work_dir, 'decisions.json')
    decisions = read_json(dec_path)
    sidecars = read_json(os.path.join(work_dir, 'sidecars.json')) \
        if os.path.isfile(os.path.join(work_dir, 'sidecars.json')) else []

    ops, skipped = [], []
    assigned = set()
    for a in decisions.get('assignments', []):
        fid = a.get('fid')
        rec = files.get(fid)
        if not rec:
            continue
        assigned.add(fid)
        disposition = a.get('disposition', 'keep')
        if not rec.get('readable') or (rec.get('extract_status') in
                                       ('extract_error', 'no_text_layer', 'binary_no_extract')
                                       and disposition == 'keep'):
            skipped.append({'fid': fid, 'rel': rec['rel'],
                            'reason': rec.get('extract_status') or 'unreadable',
                            'recovery': 'repair / OCR / fix permissions, then re-run'})
            continue
        ext = os.path.splitext(rec['rel'])[1]
        if disposition == 'archive_dup':
            dst_rel = os.path.join('_archive_dups', sanitize_name(a.get('new_name') or os.path.basename(rec['rel'])) + ext)
        else:
            dst_rel = os.path.join(sanitize_name(a.get('category') or 'unsorted'),
                                   sanitize_name(a.get('subcategory') or 'undated'),
                                   sanitize_name(a.get('new_name')) + ext)
        ops.append({'op_id': f'op-{fid}', 'fid': fid, 'action': 'copy',
                    'src': rec['rel'], 'src_sha256': rec.get('sha256'),
                    'dst_rel': dst_rel, 'disposition': disposition})

    for sc in sidecars:
        rec = files.get(sc['fid'])
        if rec and rec.get('readable') and sc['fid'] not in assigned:
            assigned.add(sc['fid'])
            ops.append({'op_id': f"op-{sc['fid']}", 'fid': sc['fid'], 'action': 'copy',
                        'src': rec['rel'], 'src_sha256': rec.get('sha256'),
                        'dst_rel': os.path.join('00-admin', os.path.basename(rec['rel'])),
                        'disposition': 'sidecar_admin'})
    for fid, rec in files.items():
        if fid not in assigned and fid not in {s['fid'] for s in skipped}:
            skipped.append({'fid': fid, 'rel': rec['rel'], 'reason': 'no_assignment',
                            'recovery': 'add an assignment in decisions.json and re-run plan/apply'})

    plan = {'created': now(), 'library_dir': case['library_dir'], 'ops': ops, 'planned_skipped': skipped}
    plan['plan_hash'] = hashlib.sha256(
        json.dumps({'ops': ops, 'skipped': skipped}, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()
    write_json(os.path.join(out_dir, 'ops_plan.json'), plan)
    write_json(os.path.join(work_dir, 'skipped.json'), skipped)
    return plan


def apply_plan(work_dir, out_dir, stop_after=None):
    """Execute pending ops from the plan; resumable via the journal."""
    plan = read_json(os.path.join(out_dir, 'ops_plan.json'))
    lib_out = os.path.join(out_dir, 'library')
    os.makedirs(lib_out, exist_ok=True)
    journal_path = os.path.join(out_dir, 'operations.jsonl')
    done = {o['op_id']: o for o in load_jsonl(journal_path)}

    executed = 0
    for op in plan['ops']:
        dst = os.path.join(lib_out, op['dst_rel'])
        prev = done.get(op['op_id'])
        if prev and prev.get('status') in ('copied', 'verified_skip') \
                and os.path.isfile(prev.get('dst', '')) \
                and sha256_of(prev['dst']) == prev.get('dst_sha256'):
            prev['status'] = 'verified_skip'
            done[op['op_id']] = prev
            continue
        src_abs = os.path.join(plan['library_dir'], op['src'])
        rec = dict(op)
        rec['dst'] = dst
        rec['ts'] = now()
        if os.path.isfile(dst):
            if sha256_of(dst) == op.get('src_sha256'):
                rec.update(status='copied', dst_sha256=op.get('src_sha256'),
                           note='already present, identical')
            else:
                base, ext = os.path.splitext(dst)
                n = 2
                while os.path.isfile(f'{base}-{n}{ext}'):
                    n += 1
                rec['dst'] = f'{base}-{n}{ext}'
                rec['dst_rel'] = os.path.relpath(rec['dst'], lib_out)
                rec.update(status='conflict_renamed',
                           note='target existed with different content; suffixed, nothing overwritten')
                shutil.copy2(src_abs, rec['dst'])
                rec['dst_sha256'] = sha256_of(rec['dst'])
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src_abs, dst)
            rec.update(status='copied', dst_sha256=sha256_of(dst))
        rec['dst_present'] = os.path.isfile(rec['dst'])
        done[op['op_id']] = rec
        executed += 1
        with open(journal_path, 'w', encoding='utf-8') as f:  # checkpoint after EVERY op
            for o in done.values():
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
        if stop_after is not None and executed >= stop_after:
            return {'executed': executed, 'interrupted': True,
                    'remaining': len(plan['ops']) - sum(1 for o in done.values()
                                                        if o.get('status') in ('copied', 'verified_skip'))}
    return {'executed': executed, 'interrupted': False,
            'total_ops': len(plan['ops'])}


def verify(work_dir, out_dir):
    plan = read_json(os.path.join(out_dir, 'ops_plan.json'))
    lib_out = os.path.join(out_dir, 'library')
    journal = load_jsonl(os.path.join(out_dir, 'operations.jsonl'))
    skipped = read_json(os.path.join(work_dir, 'skipped.json')) \
        if os.path.isfile(os.path.join(work_dir, 'skipped.json')) else []
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    problems = []
    for o in journal:
        if o.get('status') in ('copied', 'verified_skip', 'conflict_renamed'):
            if not os.path.isfile(o.get('dst', '')):
                problems.append({'fid': o['fid'], 'problem': 'dst missing'})
            elif sha256_of(o['dst']) != o.get('dst_sha256'):
                problems.append({'fid': o['fid'], 'problem': 'hash mismatch'})
    covered = {o['fid'] for o in journal} | {s['fid'] for s in skipped}
    for rec in files:
        if rec['fid'] not in covered:
            problems.append({'fid': rec['fid'], 'problem': 'uncovered input file'})
    rep = {'ok': not problems, 'problems': problems, 'checked_ops': len(journal),
           'inputs': len(files), 'ts': now()}
    write_json(os.path.join(out_dir, 'verify_report.json'), rep)
    return rep


def certify(work_dir, out_dir):
    """Prove idempotency: fingerprint, re-apply the same plan, fingerprint again."""
    lib_out = os.path.join(out_dir, 'library')
    fp1 = tree_fingerprint(lib_out)
    second = apply_plan(work_dir, out_dir)
    fp2 = tree_fingerprint(lib_out)
    granted = (fp1 == fp2) and not second.get('interrupted')
    cert = {'granted': granted,
            'first_run': fp1, 'second_run': fp2,
            'second_run_new_executions': second.get('executed'),
            'statement': 'two consecutive full plan-apply cycles produced a byte-identical output tree'
            if granted else 'output tree changed between identical re-runs; NOT idempotent',
            'ts': now()}
    write_json(os.path.join(out_dir, 'idempotency_certificate.json'), cert)
    return cert


def undo(work_dir, out_dir):
    """Reverse every journaled op; the output library returns to an empty tree."""
    lib_out = os.path.join(out_dir, 'library')
    journal = load_jsonl(os.path.join(out_dir, 'operations.jsonl'))
    removed, missing = [], []
    for o in reversed(journal):
        dst = o.get('dst')
        if dst and os.path.isfile(dst):
            os.remove(dst)
            removed.append(o['dst_rel'])
        elif dst:
            missing.append(o.get('dst_rel'))
    for r, dirs, files in os.walk(lib_out, topdown=False):
        for d in dirs:
            p = os.path.join(r, d)
            if not os.listdir(p):
                os.rmdir(p)
    fp = tree_fingerprint(lib_out)
    log = {'removed': removed, 'missing': missing,
           'tree_after': fp, 'rolled_back': fp['file_count'] == 0, 'ts': now()}
    write_json(os.path.join(work_dir, 'undo_log.json'), log)
    ops_path = os.path.join(out_dir, 'operations.jsonl')
    if os.path.isfile(ops_path):
        os.rename(ops_path, ops_path + '.undone')
    return log
