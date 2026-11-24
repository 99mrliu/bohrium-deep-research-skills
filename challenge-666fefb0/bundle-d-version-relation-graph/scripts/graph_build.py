#!/usr/bin/env python3
"""graph_build.py — multi-signal typed relation graph + canonical arbitration.

Signals (mechanical, no model): sha256 equality, normalized-title token
Jaccard, arXiv id match, DOI match, in-text version statements, admin-note
cross references. Edges are typed (duplicate_of / same_work / version_of /
supplement_of / same_work_candidate) and every edge carries its signals and
verbatim evidence. Canonical arbitration is an explicit scored policy with a
full audit trail; insufficient evidence yields canonical=null.
"""
import itertools
import json
import os
import re

from inventory import read_json, write_json

TOKEN_RE = re.compile(r'[a-z0-9]{2,}')
ARXIV_RE = re.compile(r'arXiv[:\s]*(\d{4}\.\d{4,5})', re.I)
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"\'<>)\]]+')


def norm_title(t):
    return set(TOKEN_RE.findall(str(t or '').lower()))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def file_signals(work_dir, rec, cand):
    """Extract per-file identity signals."""
    text = ''
    ext_path = os.path.join(work_dir, 'extracted', f"{rec['fid']}.txt")
    if os.path.isfile(ext_path):
        with open(ext_path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    title = (cand.get('title') or {}).get('value')
    doi = (cand.get('doi') or {}).get('value')
    if doi in (None, 'unknown'):
        doi = None
    arxiv = None
    m = ARXIV_RE.search(text) or ARXIV_RE.search(rec['rel'])
    if m:
        arxiv = m.group(1)
    published_claim = bool(re.search(r'published version', text, re.I))
    is_supp = 'supplementary' in text.lower()[:600] or 'supplementary' in rec['rel'].lower()
    return {'fid': rec['fid'], 'rel': rec['rel'], 'sha256': rec.get('sha256'),
            'title': title, 'title_tokens': sorted(norm_title(title)),
            'doi': doi, 'arxiv': arxiv, 'published_claim': published_claim,
            'is_supplementary': is_supp,
            'content_available': rec.get('extract_status') == 'ok',
            'venue': (cand.get('venue') or {}).get('value'),
            'year': (cand.get('year') or {}).get('value')}


def build_edges(signals, sidecars):
    edges = []
    by_fid = {s['fid']: s for s in signals}
    for a, b in itertools.combinations(signals, 2):
        hits, ev = [], []
        if a['sha256'] and a['sha256'] == b['sha256']:
            hits.append('sha256_equal')
            ev.append(f"SHA-256 identical: {a['sha256'][:16]}…")
        jac = jaccard(set(a['title_tokens']), set(b['title_tokens']))
        if jac >= 0.6:
            hits.append(f'title_jaccard={jac:.2f}')
            ev.append(f"titles: '{a['title']}' ≈ '{b['title']}'")
        if a['arxiv'] and a['arxiv'] == b['arxiv']:
            hits.append('arxiv_match')
            ev.append(f"arXiv id shared: {a['arxiv']}")
        if a['doi'] and a['doi'] == b['doi']:
            hits.append('doi_match')
            ev.append(f"DOI shared: {a['doi']}")
        if (a['published_claim'] or b['published_claim']) and a['arxiv'] and b['arxiv']:
            hits.append('version_statement')
            ev.append('in-text "published version" statement with shared arXiv id')
        if not hits:
            continue
        if 'sha256_equal' in hits:
            etype = 'duplicate_of'
        elif a['is_supplementary'] != b['is_supplementary'] and ('title_jaccard=' in ' '.join(hits) or a['arxiv'] == b['arxiv']):
            etype = 'supplement_of'
        elif (a['arxiv'] and b['arxiv']) or (a['published_claim'] != b['published_claim'] and jac >= 0.6):
            etype = 'version_of'
        elif 'version_statement' in hits or 'doi_match' in hits:
            etype = 'same_work'
        elif any(h.startswith('title_jaccard') for h in hits):
            etype = 'same_work_candidate'
        else:
            etype = 'same_work'
        roles = {}
        if etype == 'version_of':
            for s, other in ((a, b), (b, a)):
                roles[s['fid']] = 'preprint' if s['arxiv'] and not s['published_claim'] else \
                    ('published' if s['published_claim'] or s['doi'] else 'unspecified')
        if etype == 'supplement_of':
            roles = {a['fid']: 'supplement' if a['is_supplementary'] else 'main',
                     b['fid']: 'supplement' if b['is_supplementary'] else 'main'}
        edges.append({'pair': [a['fid'], b['fid']], 'type': etype,
                      'signals': hits, 'evidence': ev, 'roles': roles,
                      'source': 'auto'})

    for sc in sidecars:
        excerpt = sc.get('content_excerpt') or ''
        for ln_i, line in enumerate(excerpt.splitlines(), 1):
            mentioned = [s['fid'] for s in signals
                         if os.path.basename(s['rel']) and os.path.basename(s['rel']) in line]
            if len(mentioned) >= 2 and ('重复' in line or 'duplicate' in line.lower()):
                for x, y in itertools.combinations(mentioned, 2):
                    edges.append({'pair': [x, y], 'type': 'duplicate_of',
                                  'signals': ['admin_note'],
                                  'evidence': [f"{sc['rel']} 行{ln_i}: {line.strip()[:120]}"],
                                  'roles': {}, 'source': 'admin_note'})
            elif len(mentioned) >= 2 and ('正式版' in line or 'canonical' in line.lower() or '预印本' in line):
                hint = None
                for s in signals:
                    if s['fid'] not in mentioned:
                        continue
                    base = os.path.basename(s['rel'])
                    pos = line.find(base)
                    if pos >= 0 and '正式版' in line[pos:pos + len(base) + 40]:
                        hint = s['fid']
                edges.append({'pair': mentioned[:2], 'type': 'version_of',
                              'signals': ['admin_note'],
                              'evidence': [f"{sc['rel']} 行{ln_i}: {line.strip()[:120]}"],
                              'roles': {}, 'source': 'admin_note',
                              'admin_canonical_hint': hint})
    # merge edges with identical pair+type: accumulate signals/evidence/sources
    merged = {}
    for e in edges:
        key = (tuple(sorted(e['pair'])), e['type'])
        if key in merged:
            m = merged[key]
            m['signals'] = sorted(set(m['signals']) | set(e['signals']))
            m['evidence'] = m['evidence'] + [x for x in e['evidence'] if x not in m['evidence']]
            m['source'] = m['source'] + '+' + e['source'] if e['source'] not in m['source'] else m['source']
            if e.get('roles'):
                m['roles'] = m.get('roles') or e['roles']
            if e.get('admin_canonical_hint'):
                m['admin_canonical_hint'] = e['admin_canonical_hint']
        else:
            merged[key] = dict(e)
    return list(merged.values())


def cluster_and_arbitrate(signals, edges):
    """Union-find over edges; canonical per cluster via explicit scoring."""
    parent = {s['fid']: s['fid'] for s in signals}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for e in edges:
        union(e['pair'][0], e['pair'][1])
    clusters = {}
    for s in signals:
        clusters.setdefault(find(s['fid']), []).append(s['fid'])

    by_fid = {s['fid']: s for s in signals}
    out_clusters, log = [], []
    for i, (root, members) in enumerate(sorted(clusters.items()), 1):
        cid = f'C{i}'
        c_edges = [e for e in edges if e['pair'][0] in members and e['pair'][1] in members]
        scores = {}
        for m in members:
            s = by_fid[m]
            sc, why = 0, []
            if s['doi']:
                sc += 3
                why.append('含 DOI (+3)')
            if s['published_claim']:
                sc += 2
                why.append('正文自称 published version (+2)')
            if s['venue'] not in (None, 'unknown') and not s['arxiv']:
                sc += 1
                why.append('含期刊/机构标识且非预印本 (+1)')
            if s['arxiv'] and not s['published_claim']:
                sc -= 1
                why.append('预印本特征 (-1)')
            if s['is_supplementary']:
                sc -= 2
                why.append('补充材料 (-2)')
            if not s['content_available']:
                sc -= 3
                why.append('内容不可用 (-3)')
            scores[m] = (sc, why)
        admin_hint = next((e.get('admin_canonical_hint') for e in c_edges
                           if e.get('admin_canonical_hint') in members), None)
        best = max(members, key=lambda m: scores[m][0])
        top = scores[best][0]
        tied = [m for m in members if scores[m][0] == top]
        only_dup = c_edges and all(e['type'] == 'duplicate_of' for e in c_edges)
        if only_dup:
            canonical, rule = sorted(members)[0], '纯 duplicate 簇：字节级一致，保留最小 fid 为 canonical'
        elif admin_hint:
            canonical, rule = admin_hint, f'管理员说明指定 ({admin_hint})，覆盖打分'
        elif len(members) == 1:
            canonical, rule = members[0], '单节点簇，自身即 canonical'
        elif len(tied) == 1 and top > 0:
            canonical, rule = best, f'打分最高且无并列 (score={top})'
        else:
            canonical, rule = None, f'证据不足（top score={top}, tied={tied}），canonical 诚实为 null'
        out_clusters.append({'cluster_id': cid, 'members': members,
                             'edges': c_edges, 'canonical': canonical,
                             'has_duplicate': any(e['type'] == 'duplicate_of' for e in c_edges)})
        log.append({'cluster_id': cid, 'members': members,
                    'scores': {m: {'score': sc, 'reasons': why} for m, (sc, why) in scores.items()},
                    'admin_hint': admin_hint, 'decision': canonical, 'rule': rule})
    return out_clusters, log


def run_graph(work_dir):
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    cand = read_json(os.path.join(work_dir, 'meta_candidates.json'))
    sidecars = read_json(os.path.join(work_dir, 'sidecars.json')) \
        if os.path.isfile(os.path.join(work_dir, 'sidecars.json')) else []
    signals = [file_signals(work_dir, rec, cand.get(rec['fid'], {})) for rec in files]
    edges = build_edges(signals, sidecars)
    clusters, log = cluster_and_arbitrate(signals, edges)
    graph = {'nodes': [{k: v for k, v in s.items() if k != 'title_tokens'} | {'title_tokens': s['title_tokens']} for s in signals],
             'edges': edges, 'clusters': clusters,
             'candidate_edges_pending_model': [e for e in edges if e['type'] == 'same_work_candidate']}
    write_json(os.path.join(work_dir, 'version_graph.json'), graph)
    write_json(os.path.join(work_dir, 'arbitration_log.json'), log)
    return graph, log


def render_graph_md(work_dir, out_dir, graph, log):
    lines = ['# 版本关系图谱（version relation graph）', '',
             f"节点 {len(graph['nodes'])}；边 {len(graph['edges'])}；簇 {len(graph['clusters'])}",
             '', '## 邻接表与边证据', '']
    by_fid = {n['fid']: n for n in graph['nodes']}
    for c in graph['clusters']:
        lines.append(f"### {c['cluster_id']} — canonical: {c['canonical']}")
        for m in c['members']:
            n = by_fid[m]
            lines.append(f"- `{m}` {n['rel']}"
                         + (' （内容不可用）' if not n['content_available'] else ''))
        for e in c['edges']:
            lines.append(f"  - **{e['type']}** {e['pair'][0]} ↔ {e['pair'][1]}"
                         + (f" roles={e['roles']}" if e.get('roles') else ''))
            for ev in e['evidence']:
                lines.append(f'    - 证据: {ev}')
        lines.append('')
    lines += ['## canonical 仲裁轨迹', '']
    for entry in log:
        lines.append(f"- {entry['cluster_id']}: {entry['rule']} → canonical={entry['decision']}")
    with open(os.path.join(out_dir, 'graph.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
