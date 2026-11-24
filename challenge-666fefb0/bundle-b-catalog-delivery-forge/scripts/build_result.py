#!/usr/bin/env python3
"""build_result.py — assemble result.json mirroring the case output_contract."""
import os

from inventory import read_json, write_json

DEFAULT_CONTRACT = ['case_id', 'status', 'library_index', 'operations_log',
                    'version_relations', 'skipped', 'answers', 'sources',
                    'uncertainties', 'change_log']
DELIVERABLES = ['catalog.md', 'catalog.csv', 'tree_diff.md', 'verify_report.md',
                'operations.jsonl', 'library/']


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(__import__('json').loads(line))
    return rows


def maybe_json(path, default):
    return read_json(path) if os.path.isfile(path) else default


def write_partial(work_dir, out_dir, phase):
    case = maybe_json(os.path.join(work_dir, 'case_meta.json'), {})
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    result = {
        'case_id': case.get('case_id', 'unknown'),
        'status': 'in_progress', 'phase_reached': phase,
        'library_index': None, 'operations_log': None, 'version_relations': None,
        'answers': None,
        'skipped': [{'fid': r['fid'], 'rel': r['rel'], 'reason': r.get('extract_status')}
                    for r in files if r.get('extract_status') in
                    ('permission_denied', 'read_error', 'extract_error', 'no_text_layer')],
        'sources': [{'fid': r['fid'], 'rel': r['rel'], 'sha256': r.get('sha256'),
                     'size': r.get('size'), 'extract_status': r.get('extract_status')}
                    for r in files],
        'uncertainties': [f'run interrupted or in progress at phase: {phase}'],
        'change_log': [{'phase': phase, 'note': 'partial result written early by design'}],
    }
    for k in case.get('output_contract') or []:
        result.setdefault(k, None)
    write_json(os.path.join(out_dir, 'result.json'), result)
    return result


def assemble_final(work_dir, out_dir, verify):
    case = maybe_json(os.path.join(work_dir, 'case_meta.json'), {})
    contract = case.get('output_contract') or DEFAULT_CONTRACT
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    ops = load_jsonl(os.path.join(out_dir, 'operations.jsonl'))
    merged = maybe_json(os.path.join(work_dir, 'merged_plan.json'), {})
    skipped = maybe_json(os.path.join(work_dir, 'skipped.json'), [])

    applied = [o for o in ops if o.get('status') in ('copied', 'verified_skip')]
    library_index = [{
        'path': o['dst_rel'], 'sha256': o.get('dst_sha256'), 'fid': o.get('fid'),
        'disposition': o.get('disposition'),
    } for o in applied]

    uncertainties = [f'case parsing: {n}' for n in case.get('parse_notes') or []]
    low_conf = [a['fid'] for a in merged.get('assignments', []) if a.get('confidence') == 'low']
    if low_conf:
        uncertainties.append(f'low-confidence proposals accepted for: {low_conf}; see catalog.md 置信度标记')
    if skipped:
        uncertainties.append(f'{len(skipped)} file(s) not archived; see skipped[]')
    if not case.get('questions'):
        uncertainties.append('case contains no retrieval questions; answers is null')

    status = 'complete' if (not skipped and verify.get('ok')) else 'partial'
    if not files:
        status = 'blocked'

    result = {
        'case_id': case.get('case_id', 'unknown'),
        'status': status,
        'library_index': library_index,
        'operations_log': {
            'journal_path': 'operations.jsonl', 'total_ops': len(ops),
            'applied': len(applied),
            'conflicts': [o for o in ops if o.get('status') == 'conflict_renamed'],
            'verify': verify,
        },
        'version_relations': merged.get('version_relations') or [],
        'skipped': skipped,
        'answers': merged.get('answers') or None,
        'sources': [{'fid': r['fid'], 'rel': r['rel'], 'sha256': r.get('sha256'),
                     'size': r.get('size'), 'kind': r.get('kind'),
                     'extract_status': r.get('extract_status')} for r in files],
        'uncertainties': uncertainties,
        'change_log': maybe_json(os.path.join(work_dir, 'change_log.json'), []),
        'deliverables': DELIVERABLES,
    }
    for k in contract:
        if k not in result:
            result[k] = None
            result['uncertainties'].append(f'contract field "{k}" not produced by this skill; set null honestly')
    write_json(os.path.join(out_dir, 'result.json'), result)
    return result
