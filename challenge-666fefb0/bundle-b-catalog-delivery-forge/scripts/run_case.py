#!/usr/bin/env python3
"""run_case.py — driver: init (inventory + deterministic proposal) ->
(model overrides) -> finalize (apply + render four deliverables + result).

  python3 run_case.py init     --input /input --work /app/work --out /app/output
  python3 run_case.py finalize --work /app/work --out /app/output
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
import build_result  # noqa: E402
import render_catalog  # noqa: E402

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


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def guess_doc_type(rec, cand):
    """Deterministic doc-type proposal with explicit signals."""
    text = ''
    if rec.get('head_text'):
        text = rec['head_text'].lower()
    name = rec['rel'].lower()
    signals, doc, conf = [], None, 'medium'
    has_doi = 'doi' in cand and (cand['doi'] or {}).get('value') not in (None, 'unknown')
    if 'supplementary' in text or 'supplementary' in name or name.startswith('si-'):
        doc = 'supplementary'
        signals.append('标题/文件名含 Supplementary')
    elif 'published version' in text and has_doi:
        doc = 'journal-articles'
        signals.append('正文自称 published version 且含 DOI')
    elif 'arxiv' in name or ('arxiv' in text and 'published version' not in text) or 'preprint' in text:
        doc = 'preprints'
        signals.append('含 arXiv/预印本标识')
    elif 'thesis' in text or 'dissertation' in text or 'thesis' in name:
        doc = 'theses'
        signals.append('含 Thesis/Dissertation 标识')
    elif 'review' in (cand.get('title') or {}).get('value', '').lower():
        doc = 'reviews'
        signals.append('标题含 Review')
    elif rec['kind'] == 'text' or rec['rel'].lower().endswith(('.csv', '.tsv', '.json', '.md', '.bib')):
        base = os.path.basename(name)
        if re.search(r'(meta|notes?|readme|版本|说明)', base):
            doc = 'admin-note'
            signals.append('旁挂说明/元数据表')
        else:
            doc = 'datasets'
            signals.append('数据/文本文件')
    elif text:
        doc = 'journal-articles'
        signals.append('可抽取文本且无其他类型信号（默认）')
    else:
        doc = 'unknown'
        conf = 'low'
        signals.append('无可判定信号')
    if has_doi:
        signals.append('含 DOI')
        conf = 'high' if doc not in ('unknown',) else conf
    if rec.get('extract_status') != 'ok':
        conf = 'low'
    return doc, conf, signals


def first_author(authors_value):
    if not authors_value or authors_value == 'unknown':
        return 'UnknownAuthor'
    first = re.split(r'[,;]| and ', str(authors_value))[0].strip()
    return first.split()[0] if first.split() else 'UnknownAuthor'


def cmd_init(args):
    case, records, aliases = run_inventory(args.input, args.work, args.out)
    cand = read_json(os.path.join(args.work, 'meta_candidates.json'))
    dup_fids = {}
    for g in aliases:
        for fid in g['fids'][1:]:
            dup_fids[fid] = g['fids'][0]
    proposal = []
    for rec in records:
        if not rec.get('readable'):
            proposal.append({'fid': rec['fid'], 'disposition': 'skip',
                             'reason': rec.get('extract_status'), 'confidence': 'high',
                             'signals': ['文件不可读']})
            continue
        if rec.get('extract_status') in ('extract_error', 'no_text_layer'):
            proposal.append({'fid': rec['fid'], 'disposition': 'skip',
                             'reason': rec.get('extract_status'), 'confidence': 'high',
                             'signals': ['无法抽取内容，不猜类别']})
            continue
        c = cand[rec['fid']]
        doc, conf, signals = guess_doc_type(rec, c)
        year = (c.get('year') or {}).get('value') or 'undated'
        title = (c.get('title') or {}).get('value') or 'untitled'
        authors = (c.get('authors') or {}).get('value') or 'unknown'
        disposition = 'keep'
        if rec['fid'] in dup_fids:
            disposition = 'archive_dup'
            signals.append(f"SHA-256 与 {dup_fids[rec['fid']]} 相同")
        new_name = sanitize_name(f"{first_author(authors)}-{year if year != 'unknown' else 'nd'}-{title[:80]}")
        proposal.append({'fid': rec['fid'], 'doc_type': doc, 'category': doc,
                         'subcategory': year if year != 'unknown' else 'undated',
                         'new_name': new_name, 'disposition': disposition,
                         'confidence': conf, 'signals': signals,
                         'metadata': {k: v for k, v in c.items()}})
    write_json(os.path.join(args.work, 'proposal.json'), proposal)
    build_result.write_partial(args.work, args.out, 'init')
    log_change(args.work, 'init',
               f"inventoried {len(records)} files; proposal: {sum(1 for p in proposal if p.get('disposition') == 'keep')} keep, "
               f"{sum(1 for p in proposal if p.get('disposition') == 'archive_dup')} dup, "
               f"{sum(1 for p in proposal if p.get('disposition') == 'skip')} skip; partial result written")
    print(json.dumps({'case_id': case['case_id'], 'files': len(records),
                      'proposal_low_confidence': [p['fid'] for p in proposal if p.get('confidence') == 'low']},
                     ensure_ascii=False))


def cmd_finalize(args):
    work, out = args.work, args.out
    case = read_json(os.path.join(work, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work, 'files.jsonl'))}
    proposal = read_json(os.path.join(work, 'proposal.json'))
    overrides = read_json(os.path.join(work, 'overrides.json')) if os.path.isfile(os.path.join(work, 'overrides.json')) else {}
    ov_by_fid = {o['fid']: o for o in overrides.get('overrides', [])}

    assignments, skipped = [], []
    for p in proposal:
        a = dict(p)
        if p['fid'] in ov_by_fid:
            o = ov_by_fid[p['fid']]
            for k in ('category', 'subcategory', 'new_name', 'disposition', 'doc_type'):
                if k in o:
                    a[k] = o[k]
            a['override_reason'] = o.get('reason', '')
            log_change(work, 'override', f"{p['fid']}: {o.get('reason', 'model override')}")
        assignments.append(a)

    lib_out = os.path.join(out, 'library')
    os.makedirs(lib_out, exist_ok=True)
    journal_path = os.path.join(out, 'operations.jsonl')
    done = {o['fid']: o for o in load_jsonl(journal_path)
            if o.get('status') in ('copied', 'verified_skip')}

    ops_new = []
    for a in assignments:
        fid, rec = a['fid'], files.get(a['fid'])
        if not rec:
            continue
        if a.get('disposition') == 'skip' or not rec.get('readable'):
            skipped.append({'fid': fid, 'rel': rec['rel'],
                            'reason': a.get('reason') or rec.get('extract_status') or 'unreadable',
                            'recovery': 'repair / OCR / fix permissions, then re-run'})
            continue
        src = os.path.join(case['library_dir'], rec['rel'])
        ext = os.path.splitext(rec['rel'])[1]
        if a.get('disposition') == 'archive_dup':
            dst_rel = os.path.join('_archive_dups', sanitize_name(a.get('new_name')) + ext)
        elif a.get('doc_type') == 'admin-note':
            dst_rel = os.path.join('00-admin', os.path.basename(rec['rel']))
            a['disposition'] = 'sidecar_admin'
        else:
            dst_rel = os.path.join(sanitize_name(a.get('category') or 'unsorted'),
                                   sanitize_name(a.get('subcategory') or 'undated'),
                                   sanitize_name(a.get('new_name')) + ext)
        dst = os.path.join(lib_out, dst_rel)
        op = {'op_id': f'op-{fid}', 'fid': fid, 'src': rec['rel'], 'src_sha256': rec.get('sha256'),
              'dst_rel': dst_rel, 'dst': dst, 'disposition': a.get('disposition', 'keep'),
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

    covered = {o['fid'] for o in ops_new} | {s['fid'] for s in skipped}
    for fid, rec in files.items():
        if fid not in covered:
            skipped.append({'fid': fid, 'rel': rec['rel'], 'reason': 'no_assignment',
                            'recovery': 'add override or extend proposal rules, then re-run'})

    with open(journal_path, 'w', encoding='utf-8') as f:
        for op in ops_new:
            entry = dict(op)
            entry['dst_present'] = os.path.isfile(op['dst'])
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    problems = []
    for op in ops_new:
        if not os.path.isfile(op['dst']) or sha256_of(op['dst']) != op.get('dst_sha256'):
            problems.append({'fid': op['fid'], 'problem': 'dst missing or hash mismatch'})
    verify = {'ok': not problems, 'problems': problems, 'checked_ops': len(ops_new),
              'inputs': len(files),
              'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
    write_json(os.path.join(out, 'verify_report.json'), verify)
    write_json(os.path.join(work, 'skipped.json'), skipped)

    merged = {'assignments': assignments,
              'version_relations': overrides.get('version_relations', []),
              'answers': overrides.get('answers', [])}
    write_json(os.path.join(work, 'merged_plan.json'), merged)
    log_change(work, 'finalize',
               f"applied {len(ops_new)} ops, skipped {len(skipped)}, verify ok={verify['ok']}")

    stats = render_catalog.render_all(work, out)
    log_change(work, 'render', f"rendered catalog.md/catalog.csv/tree_diff.md/verify_report.md ({stats['catalog_rows']} rows)")
    result = build_result.assemble_final(work, out, verify)
    print(json.dumps({'status': result['status'], 'ops': len(ops_new),
                      'skipped': len(skipped), 'verify_ok': verify['ok'],
                      'deliverables': ['catalog.md', 'catalog.csv', 'tree_diff.md', 'verify_report.md']},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='catalog-delivery-forge driver')
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
