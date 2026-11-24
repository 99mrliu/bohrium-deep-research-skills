#!/usr/bin/env python3
"""build_result.py — assemble result.json; version_relations exported from the graph."""
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
                if line.strip():
                    rows.append(json.loads(line))
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


def assemble_final(work_dir, out_dir, verify, graph, adjudication):
    case = maybe_json(os.path.join(work_dir, 'case_meta.json'), {})
    contract = case.get('output_contract') or DEFAULT_CONTRACT
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    ops = load_jsonl(os.path.join(out_dir, 'operations.jsonl'))
    skipped = maybe_json(os.path.join(work_dir, 'skipped.json'), [])

    applied = [o for o in ops if o.get('status') in ('copied', 'verified_skip')]
    library_index = [{'path': o['dst_rel'], 'sha256': o.get('dst_sha256'),
                      'fid': o.get('fid'), 'disposition': o.get('disposition')}
                     for o in applied]

    version_relations = []
    for c in graph.get('clusters', []):
        if len(c.get('members', [])) > 1:
            version_relations.append({
                'cluster_id': c['cluster_id'], 'members': c['members'],
                'edge_types': sorted({e['type'] for e in c.get('edges', [])}),
                'canonical': c.get('canonical'),
                'evidence': [ev for e in c.get('edges', []) for ev in e.get('evidence', [])][:5],
            })

    uncertainties = [f'case parsing: {n}' for n in case.get('parse_notes') or []]
    null_canon = [c['cluster_id'] for c in graph.get('clusters', [])
                  if len(c.get('members', [])) > 1 and not c.get('canonical')]
    if null_canon:
        uncertainties.append(f'clusters with insufficient canonical evidence (canonical=null): {null_canon}')
    if graph.get('rejected_edges'):
        uncertainties.append(f"{len(graph['rejected_edges'])} auto edge(s) rejected by model adjudication; see version_graph.json")
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
        'version_relations': version_relations,
        'skipped': skipped,
        'answers': adjudication.get('answers') or None,
        'sources': [{'fid': r['fid'], 'rel': r['rel'], 'sha256': r.get('sha256'),
                     'size': r.get('size'), 'kind': r.get('kind'),
                     'extract_status': r.get('extract_status')} for r in files],
        'uncertainties': uncertainties,
        'change_log': maybe_json(os.path.join(work_dir, 'change_log.json'), []),
        'graph_artifacts': ['version_graph.json', 'graph.md', 'arbitration_log.json'],
    }
    for k in contract:
        if k not in result:
            result[k] = None
            result['uncertainties'].append(f'contract field "{k}" not produced by this skill; set null honestly')
    write_json(os.path.join(out_dir, 'result.json'), result)
    return result
