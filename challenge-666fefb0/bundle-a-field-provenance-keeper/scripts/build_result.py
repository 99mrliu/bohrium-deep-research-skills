#!/usr/bin/env python3
"""build_result.py — assemble result.json mirroring the case output_contract.

Every contract field is filled from real artifacts or set to null with an
explicit reason recorded in uncertainties. Status is honest: complete only when
nothing was skipped and verification passed.
"""
import json
import os

from inventory import read_json, write_json

DEFAULT_CONTRACT = ['case_id', 'status', 'library_index', 'operations_log',
                    'version_relations', 'skipped', 'answers', 'sources',
                    'uncertainties', 'change_log']


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def maybe_json(path, default):
    return read_json(path) if os.path.isfile(path) else default


def write_partial(input_dir_unused, work_dir, out_dir, phase):
    case = maybe_json(os.path.join(work_dir, 'case_meta.json'), {})
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    result = {
        'case_id': case.get('case_id', 'unknown'),
        'status': 'in_progress',
        'phase_reached': phase,
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
    decisions = maybe_json(os.path.join(work_dir, 'decisions.linted.json'),
                           maybe_json(os.path.join(work_dir, 'decisions.json'), {}))
    lint = maybe_json(os.path.join(work_dir, 'lint_report.json'), None)
    conflicts = maybe_json(os.path.join(work_dir, 'conflicts.json'), [])
    skipped = maybe_json(os.path.join(work_dir, 'skipped.json'), [])

    applied = [o for o in ops if o.get('status') in ('copied', 'verified_skip')]
    library_index = [{
        'path': o['dst_rel'], 'sha256': o.get('dst_sha256'), 'fid': o.get('fid'),
        'disposition': o.get('disposition'),
        'metadata': (next((a.get('metadata') for a in decisions.get('assignments', [])
                           if a.get('fid') == o.get('fid')), None)),
    } for o in applied]

    uncertainties = []
    if lint:
        if lint.get('downgraded'):
            uncertainties.append(
                f"{len(lint['downgraded'])} metadata value(s) failed anchor lint and were downgraded to unknown; see conflicts.json")
        if lint.get('evidence_issues'):
            uncertainties.append(f"{len(lint['evidence_issues'])} evidence snippet(s) could not be anchored")
    for note in case.get('parse_notes') or []:
        uncertainties.append(f'case parsing: {note}')
    if skipped:
        uncertainties.append(f'{len(skipped)} file(s) not archived; see skipped[]')
    if not case.get('questions'):
        uncertainties.append('case contains no retrieval questions; answers is null')

    status = 'complete' if (not skipped and verify.get('ok')) else 'partial'
    if not files:
        status = 'blocked'

    answers = decisions.get('answers')
    if not answers:
        answers = None
    result = {
        'case_id': case.get('case_id', 'unknown'),
        'status': status,
        'library_index': library_index,
        'operations_log': {
            'journal_path': 'operations.jsonl',
            'total_ops': len(ops),
            'applied': len(applied),
            'conflicts': [o for o in ops if o.get('status') == 'conflict_renamed'],
            'verify': verify,
        },
        'version_relations': decisions.get('version_relations') or [],
        'skipped': skipped,
        'answers': answers,
        'sources': [{'fid': r['fid'], 'rel': r['rel'], 'sha256': r.get('sha256'),
                     'size': r.get('size'), 'kind': r.get('kind'),
                     'extract_status': r.get('extract_status')} for r in files],
        'uncertainties': uncertainties,
        'change_log': maybe_json(os.path.join(work_dir, 'change_log.json'), []),
        'metadata_ledger_path': 'metadata_ledger.jsonl',
        'lint_summary': lint,
        'conflicts_path': 'conflicts.json',
    }
    for k in contract:
        if k not in result:
            result[k] = None
            uncertainties_note = f'contract field "{k}" not produced by this skill; set null honestly'
            if uncertainties_note not in result['uncertainties']:
                result['uncertainties'].append(uncertainties_note)
    write_json(os.path.join(out_dir, 'result.json'), result)

    ledger_path = os.path.join(out_dir, 'metadata_ledger.jsonl')
    with open(ledger_path, 'w', encoding='utf-8') as f:
        for a in decisions.get('assignments', []):
            for field_name, entry in (a.get('metadata') or {}).items():
                f.write(json.dumps({'fid': a.get('fid'), 'field': field_name,
                                    **(entry if isinstance(entry, dict) else {'value': entry})},
                                   ensure_ascii=False) + '\n')
    if conflicts:
        write_json(os.path.join(out_dir, 'conflicts.json'), conflicts)
    return result
