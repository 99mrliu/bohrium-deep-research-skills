#!/usr/bin/env python3
"""outline_graph.py -- 把稿件解析成结构图 JSON, 供渲染与对照分析。

节点: section(标题) / claim(含论断线索的句子) / evidence(含数据/引用线索的句子)。
边: contains(节->段), supports(evidence->claim, 同节内就近匹配, 仅供可视化,
不代替人工判断论证关系)。

用法:
    python3 outline_graph.py MANUSCRIPT_MD GRAPH_JSON
"""
import json
import re
import sys

CLAIM_CUES = ['表明', '证明', '说明', '意味着', '因此', 'shows', 'demonstrates',
              'indicates', 'implies', 'therefore', '最优', '最佳', '关键']
EVID_CUES = ['图', '表', '数据', '实验', 'n=', 'p<', '%', 'Fig.', 'Table',
             'et al.', '[', '测得', '观察到']
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$|^([一二三四五六七八九十]+、\S.*)$')


def parse(ms_path, graph_path):
    with open(ms_path, encoding='utf-8') as f:
        text = f.read()

    nodes, edges = [], []
    cur_sec = None
    sec_seq = 0
    sent_seq = 0
    section_nodes = {}
    for chunk in re.split(r'\n[ \t]*\n', text):
        t = chunk.strip()
        if not t:
            continue
        m = HEADING_RE.match(t)
        if m:
            sec_seq += 1
            cur_sec = 'SEC%02d' % sec_seq
            title = (m.group(2) or m.group(3) or t).strip()
            nodes.append({'id': cur_sec, 'kind': 'section', 'title': title[:60]})
            section_nodes[cur_sec] = []
            continue
        for sent in re.split(r'(?<=[。！？.!?])', t):
            s = sent.strip()
            if len(s) < 6:
                continue
            sent_seq += 1
            sid = 'N%03d' % sent_seq
            is_claim = any(c in s for c in CLAIM_CUES)
            is_evid = any(c in s for c in EVID_CUES)
            kind = 'claim' if is_claim else ('evidence' if is_evid else 'plain')
            if kind == 'plain':
                continue
            nodes.append({'id': sid, 'kind': kind, 'section': cur_sec,
                          'text': s[:120]})
            if cur_sec:
                edges.append({'from': cur_sec, 'to': sid, 'rel': 'contains'})
                section_nodes[cur_sec].append(sid)
    # supports: 同节内 evidence -> 其后最近的 claim (可视化近似)
    for sec, ids in section_nodes.items():
        last_evid = None
        for sid in ids:
            n = next(x for x in nodes if x['id'] == sid)
            if n['kind'] == 'evidence':
                last_evid = sid
            elif n['kind'] == 'claim' and last_evid:
                edges.append({'from': last_evid, 'to': sid, 'rel': 'supports?'})
                last_evid = None
    claims = [n for n in nodes if n['kind'] == 'claim']
    orphan_claims = [n['id'] for n in claims
                     if not any(e['to'] == n['id'] and e['rel'] == 'supports?'
                                for e in edges)]
    graph = {'manuscript': ms_path, 'nodes': nodes, 'edges': edges,
             'stats': {'sections': sec_seq,
                       'claims': len(claims),
                       'evidence': sum(1 for n in nodes if n['kind'] == 'evidence'),
                       'orphan_claims_visual': orphan_claims},
             'note': 'supports? 边为可视化近似, 不代表人工判定的论证关系'}
    with open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(json.dumps(graph['stats'], ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: outline_graph.py MANUSCRIPT_MD GRAPH_JSON')
    parse(*sys.argv[1:3])
