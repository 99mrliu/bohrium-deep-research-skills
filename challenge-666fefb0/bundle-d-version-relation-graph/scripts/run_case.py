#!/usr/bin/env python3
"""run_case.py — driver: init -> graph -> (model adjudication) -> finalize.

Archiving policy is derived from the graph: within a duplicate_of group only
the lowest fid is kept (rest archived, never deleted); same-work versions are
ALL kept; names are generated deterministically from anchored candidates.
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
import graph_build  # noqa: E402
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
    build_result.write_partial(args.work, args.out, 'init')
    log_change(args.work, 'init', f"inventoried {len(records)} files; partial result written")
    print(json.dumps({'case_id': case['case_id'], 'files': len(records)}, ensure_ascii=False))


def cmd_graph(args):
    graph, log = graph_build.run_graph(args.work)
    log_change(args.work, 'graph',
               f"graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges, "
               f"{len(graph['clusters'])} clusters, {len(graph['candidate_edges_pending_model'])} candidate edges")
    print(json.dumps({'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                      'clusters': len(graph['clusters']),
                      'pending_candidate_edges': len(graph['candidate_edges_pending_model'])},
                     ensure_ascii=False))


def derive_assignments(graph, files, adjudication):
    """Graph -> archiving assignments (deterministic)."""
    by_fid = {n['fid']: n for n in graph['nodes']}
    rejected = {tuple(sorted(e['edge'])) for e in adjudication.get('reject', []) if 'edge' in e}
    confirmed = {tuple(sorted(e['edge'])): e.get('type') for e in adjudication.get('confirm', []) if 'edge' in e}
    edges = []
    for e in graph['edges']:
        key = tuple(sorted(e['pair']))
        if key in rejected:
            continue
        if key in confirmed:
            e = dict(e, type=confirmed[key], source='model_confirmed')
        edges.append(e)

    dup_parent = {}

    def find(x):
        dup_parent.setdefault(x, x)
        while dup_parent[x] != x:
            dup_parent[x] = dup_parent[dup_parent[x]]
            x = dup_parent[x]
        return x

    for e in edges:
        if e['type'] == 'duplicate_of':
            dup_parent[find(e['pair'][0])] = find(e['pair'][1])
    dup_groups = {}
    for n in graph['nodes']:
        if n['fid'] in dup_parent:
            dup_groups.setdefault(find(n['fid']), []).append(n['fid'])
    dup_keep = {g: sorted(m)[0] for g, m in dup_groups.items()}

    assignments = []
    for n in graph['nodes']:
        fid = n['fid']
        rec = files[fid]
        if not rec.get('readable') or rec.get('extract_status') in ('extract_error', 'no_text_layer', 'binary_no_extract'):
            assignments.append({'fid': fid, 'disposition': 'skip',
                                'reason': rec.get('extract_status') or 'unreadable'})
            continue
        if rec['rel'].lower().endswith(('.md', '.csv', '.json', '.bib', '.txt')) and rec['kind'] == 'text':
            assignments.append({'fid': fid, 'disposition': 'sidecar_admin'})
            continue
        root = find(fid) if fid in dup_parent else None
        disposition = 'keep'
        if root and dup_keep.get(root) != fid:
            disposition = 'archive_dup'
        if n['is_supplementary']:
            cat = 'supplementary'
        elif n['arxiv'] and not n['published_claim']:
            cat = 'preprints'
        elif n['published_claim'] or n['doi']:
            cat = 'journal-articles'
        else:
            cat = 'others'
        year = n.get('year') if n.get('year') not in (None, 'unknown') else 'undated'
        title = n.get('title') if n.get('title') not in (None, 'unknown') else os.path.splitext(os.path.basename(rec['rel']))[0]
        authors = 'UnknownAuthor'
        assignments.append({'fid': fid, 'category': cat, 'subcategory': str(year),
                            'new_name': sanitize_name(f'{authors}-{year}-{str(title)[:80]}'),
                            'disposition': disposition})
    return assignments, edges


def cmd_finalize(args):
    work, out = args.work, args.out
    case = read_json(os.path.join(work, 'case_meta.json'))
    files = {r['fid']: r for r in load_jsonl(os.path.join(work, 'files.jsonl'))}
    graph = read_json(os.path.join(work, 'version_graph.json'))
    adj_path = os.path.join(work, 'adjudication.json')
    adjudication = read_json(adj_path) if os.path.isfile(adj_path) else {}
    for ov in adjudication.get('canonical_overrides', []):
        for c in graph['clusters']:
            if c['cluster_id'] == ov.get('cluster'):
                c['canonical'] = ov.get('canonical')
                log_change(work, 'adjudication',
                           f"canonical override {ov.get('cluster')}: {ov.get('canonical')} — {ov.get('reason', '')}")

    assignments, edges = derive_assignments(graph, files, adjudication)
    graph['edges'] = edges
    rejected = adjudication.get('reject', [])
    if rejected:
        graph['rejected_edges'] = rejected

    lib_out = os.path.join(out, 'library')
    os.makedirs(lib_out, exist_ok=True)
    journal_path = os.path.join(out, 'operations.jsonl')
    done = {o['fid']: o for o in load_jsonl(journal_path)}
    ops_new, skipped = [], []
    for a in assignments:
        fid, rec = a['fid'], files.get(a['fid'])
        if not rec:
            continue
        if a['disposition'] == 'skip':
            skipped.append({'fid': fid, 'rel': rec['rel'], 'reason': a.get('reason'),
                            'recovery': 'repair / OCR / fix permissions, then re-run'})
            continue
        src = os.path.join(case['library_dir'], rec['rel'])
        ext = os.path.splitext(rec['rel'])[1]
        if a['disposition'] == 'sidecar_admin':
            dst_rel = os.path.join('00-admin', os.path.basename(rec['rel']))
        elif a['disposition'] == 'archive_dup':
            dst_rel = os.path.join('_archive_dups', sanitize_name(a['new_name']) + ext)
        else:
            dst_rel = os.path.join(sanitize_name(a['category']), sanitize_name(a['subcategory']),
                                   sanitize_name(a['new_name']) + ext)
        dst = os.path.join(lib_out, dst_rel)
        op = {'op_id': f'op-{fid}', 'fid': fid, 'src': rec['rel'], 'src_sha256': rec.get('sha256'),
              'dst_rel': dst_rel, 'dst': dst, 'disposition': a['disposition'], 'ts': now()}
        prev = done.get(fid)
        if prev and os.path.isfile(prev.get('dst', '')) and sha256_of(prev['dst']) == rec.get('sha256'):
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

    with open(journal_path, 'w', encoding='utf-8') as f:
        for op in ops_new:
            entry = dict(op)
            entry['dst_present'] = os.path.isfile(op['dst'])
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    problems = []
    for op in ops_new:
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
    write_json(os.path.join(out, 'version_graph.json'), graph)
    shutil.copy2(os.path.join(work, 'arbitration_log.json'), os.path.join(out, 'arbitration_log.json'))
    graph_build.render_graph_md(work, out, graph, read_json(os.path.join(work, 'arbitration_log.json')))
    log_change(work, 'finalize', f"applied {len(ops_new)} ops, skipped {len(skipped)}, verify ok={verify['ok']}")

    result = build_result.assemble_final(work, out, verify, graph, adjudication)
    print(json.dumps({'status': result['status'], 'ops': len(ops_new),
                      'skipped': len(skipped), 'verify_ok': verify['ok'],
                      'clusters': len(graph['clusters'])}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description='version-relation-graph driver')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn in (('init', cmd_init), ('graph', cmd_graph), ('finalize', cmd_finalize)):
        p = sub.add_parser(name)
        if name == 'init':
            p.add_argument('--input', required=True)
        p.add_argument('--work', required=True)
        p.add_argument('--out', required=True)
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
