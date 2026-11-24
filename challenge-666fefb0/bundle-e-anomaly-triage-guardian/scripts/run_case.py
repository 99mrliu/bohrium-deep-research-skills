#!/usr/bin/env python3
"""run_case.py — driver: init (inventory + triage + partial) -> (optional model
answers) -> finalize (archive healthy, quarantine anomalies, honest result).

Never-block guarantee: every per-file step is isolated in try/except; an
unexpected failure becomes triage class `processing_error` and the run
continues. Even if ALL files fail, a valid partial result.json is written.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory import run_inventory, read_json, write_json, sha256_of  # noqa: E402
import triage  # noqa: E402
import build_result  # noqa: E402

BAD_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def sanitize_name(name, cap=120):
    name = BAD_CHARS.sub('-', str(name or 'untitled'))
    name = re.sub(r'\s+', ' ', name).strip(' .-') or 'untitled'
    return name[:cap]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def log_change(work_dir, phase, note):
    path = os.path.join(work_dir, 'change_log.json')
    log = read_json(path) if os.path.isfile(path) else []
    log.append({'ts': now(), 'phase': phase, 'note': note})
    write_json(path, log)


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def cmd_init(args):
    case, records, aliases = run_inventory(args.input, args.work, args.out)
    triage_records, counts = triage.run_triage(args.work, args.out)
    build_result.write_partial(args.work, args.out, 'init+triage')
    log_change(args.work, 'init',
               f"inventoried {len(records)} files; triage classes: {counts}; partial result written")
    print(json.dumps({'case_id': case['case_id'], 'files': len(records),
                      'triage_classes': counts}, ensure_ascii=False))


def doc_category(rec, cand):
    text = (rec.get('head_text') or '').lower()
    name = rec['rel'].lower()
    if 'supplementary' in text[:600] or 'supplementary' in name:
        return 'supplementary'
    if 'published version' in text:
        return 'journal-articles'
    if 'arxiv' in text or 'arxiv' in name:
        return 'preprints'
    if 'thesis' in text or 'thesis' in name:
        return 'theses'
    return 'journal-articles'


def first_author(v):
    if not v or v == 'unknown':
        return 'UnknownAuthor'
    first = re.split(r'[,;]| and ', str(v))[0].strip()
    return first.split()[0] if first.split() else 'UnknownAuthor'


def cmd_finalize(args):
    work, out = args.work, args.out
    case = read_json(os.path.join(work, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work, 'files.jsonl'))}
    triage_records = load_jsonl(os.path.join(work, 'triage.jsonl'))
    cand = read_json(os.path.join(work, 'meta_candidates.json'))
    answers_doc = read_json(os.path.join(work, 'answers.json')) \
        if os.path.isfile(os.path.join(work, 'answers.json')) else {}

    lib_out = os.path.join(out, 'library')
    os.makedirs(lib_out, exist_ok=True)
    journal_path = os.path.join(out, 'operations.jsonl')
    done = {o['fid']: o for o in load_jsonl(journal_path)}

    ops_new, skipped, quarantine = [], [], []
    for t in triage_records:
        fid = t['fid']
        rec = files.get(fid)
        if not rec:
            continue
        try:
            dst_rel = None
            disposition = t['disposition']
            if disposition == 'archive':
                c = cand.get(fid, {})
                year = (c.get('year') or {}).get('value') or 'undated'
                title = (c.get('title') or {}).get('value') or os.path.splitext(os.path.basename(rec['rel']))[0]
                authors = (c.get('authors') or {}).get('value') or 'unknown'
                cat = doc_category(rec, c)
                new_name = sanitize_name(f"{first_author(authors)}-{year if year != 'unknown' else 'nd'}-{str(title)[:80]}")
                dst_rel = os.path.join(sanitize_name(cat),
                                       sanitize_name(str(year) if year != 'unknown' else 'undated'),
                                       new_name + os.path.splitext(rec['rel'])[1])
            elif disposition == 'archive_dup':
                dst_rel = os.path.join('_archive_dups', os.path.basename(rec['rel']))
            elif disposition == 'sidecar_admin':
                dst_rel = os.path.join('00-admin', os.path.basename(rec['rel']))
            elif disposition == 'quarantine':
                dst_rel = os.path.join('_quarantine', t['triage_class'], os.path.basename(rec['rel']))
                if not rec.get('readable'):
                    skipped.append({'fid': fid, 'rel': rec['rel'], 'triage_class': t['triage_class'],
                                    'reason': t['evidence'], 'recovery': t['recovery'],
                                    'preserved_at': None,
                                    'note': '源文件不可读，无法复制入隔离区；未丢失，仍在原路径'})
                    ops_new.append({'op_id': f'op-{fid}', 'fid': fid, 'src': rec['rel'],
                                    'src_sha256': rec.get('sha256'), 'disposition': 'quarantine',
                                    'triage_class': t['triage_class'], 'status': 'failed',
                                    'note': 'source unreadable at apply time', 'ts': now()})
                    continue
                skipped.append({'fid': fid, 'rel': rec['rel'], 'triage_class': t['triage_class'],
                                'reason': t['evidence'], 'recovery': t['recovery'],
                                'preserved_at': f"library/{dst_rel}"})
                quarantine.append({'fid': fid, 'rel': rec['rel'], 'triage_class': t['triage_class'],
                                   'preserved_at': f"library/{dst_rel}", 'sha256': rec.get('sha256'),
                                   'recovery': t['recovery']})
            else:
                skipped.append({'fid': fid, 'rel': rec['rel'], 'triage_class': t['triage_class'],
                                'reason': f'unknown disposition {disposition}', 'recovery': 'manual review'})
                continue

            dst = os.path.join(lib_out, dst_rel)
            op = {'op_id': f'op-{fid}', 'fid': fid, 'src': rec['rel'],
                  'src_sha256': rec.get('sha256'), 'dst_rel': dst_rel, 'dst': dst,
                  'disposition': disposition, 'triage_class': t['triage_class'], 'ts': now()}
            prev = done.get(fid)
            if prev and os.path.isfile(prev.get('dst', '')) and sha256_of(prev['dst']) == rec.get('sha256'):
                op.update(status='verified_skip', dst=prev['dst'], dst_rel=prev['dst_rel'],
                          dst_sha256=prev.get('dst_sha256'))
                ops_new.append(op)
                continue
            if not rec.get('readable'):
                op.update(status='failed', note='source unreadable at apply time')
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
                op.update(dst=dst, dst_rel=os.path.relpath(dst, lib_out),
                          status='conflict_renamed',
                          note='target existed with different content; suffixed, nothing overwritten')
            else:
                op['status'] = 'copied' if disposition != 'quarantine' else 'quarantined'
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(case['library_dir'], rec['rel']), dst)
            op['dst_sha256'] = sha256_of(dst)
            ops_new.append(op)
        except Exception as e:  # noqa: BLE001 — never-block guarantee
            skipped.append({'fid': fid, 'rel': rec.get('rel'), 'triage_class': 'processing_error',
                            'reason': f'unexpected error: {e}', 'recovery': 'inspect file manually, then re-run'})
            log_change(work, 'processing_error', f'{fid}: {e}')

    with open(journal_path, 'w', encoding='utf-8') as f:
        for op in ops_new:
            entry = dict(op)
            entry['dst_present'] = os.path.isfile(op.get('dst', ''))
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    problems = []
    for op in ops_new:
        if op.get('status') in ('copied', 'verified_skip', 'quarantined', 'conflict_renamed'):
            if not os.path.isfile(op['dst']) or sha256_of(op['dst']) != op.get('dst_sha256'):
                problems.append({'fid': op['fid'], 'problem': 'dst missing or hash mismatch'})
    covered = {o['fid'] for o in ops_new} | {s['fid'] for s in skipped}
    for fid in files:
        if fid not in covered:
            problems.append({'fid': fid, 'problem': 'uncovered input file'})
    verify = {'ok': not problems, 'problems': problems, 'checked_ops': len(ops_new),
              'inputs': len(files), 'ts': now()}
    write_json(os.path.join(out, 'verify_report.json'), verify)
    write_json(os.path.join(work, 'skipped.json'), skipped)
    write_json(os.path.join(out, 'quarantine_manifest.json'), quarantine)
    log_change(work, 'finalize',
               f"ops={len(ops_new)} quarantined={len(quarantine)} skipped={len(skipped)} verify ok={verify['ok']}")

    result = build_result.assemble_final(work, out, verify, answers_doc.get('answers'))
    print(json.dumps({'status': result['status'], 'ops': len(ops_new),
                      'quarantined': len(quarantine), 'skipped': len(skipped),
                      'verify_ok': verify['ok']}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='anomaly-triage-guardian driver')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('--input', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser('finalize')
    p.add_argument('--work', required=True)
    p.add_argument('--out', required=True)
    p.set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
