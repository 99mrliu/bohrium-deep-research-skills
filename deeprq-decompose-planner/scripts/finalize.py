#!/usr/bin/env python3
"""deeprq-decompose-planner: finalization.

Recomputes the coverage matrix from the run journal, merges optional
agent overrides (with reasons), derives research gaps strictly from
coverage, verifies the journal chain, and writes the final result.json.
Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journal as journal_mod


def load(path, default=None):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    case = load(args.case, {})
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'
    tree = load(os.path.join(args.out, 'decomposition_tree.json'),
                {'sub_questions': []})
    journal_path = os.path.join(args.out, 'run_journal.jsonl')
    coverage = load(os.path.join(args.out, 'coverage_matrix.json'),
                    {'rows': []})
    overrides = load(os.path.join(args.work, 'coverage_overrides.json'), {})

    # journal integrity first
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = journal_mod.verify(journal_path)
    verdict = json.loads(buf.getvalue())

    # recompute coverage from journal
    sq_tool_status = {}
    with open(journal_path, encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            sq = e.get('sq')
            if not sq or sq == 'ALL':
                continue
            st = e.get('status')
            cur = sq_tool_status.setdefault(sq, set())
            if st == 'ok' and e.get('results_count'):
                cur.add('covered')
            elif st == 'failed':
                cur.add('failed')
            else:
                cur.add('attempted')
    for row in coverage.get('rows', []):
        sid = row['sub_question']
        states = sq_tool_status.get(sid, set())
        if 'covered' in states:
            computed = 'covered'
        elif 'failed' in states:
            computed = 'failed'
        elif states:
            computed = '未达标'
        else:
            computed = '未检索'
        ov = overrides.get(sid)
        row['computed'] = computed
        if ov:
            row['override'] = ov  # must contain {'value':..., 'reason':...}
            row['final'] = ov.get('value', computed)
        else:
            row['final'] = computed

    # gap analysis strictly from coverage
    gaps = {'searched_but_absent': [], 'partially_covered': [],
            'not_searched': []}
    for row in coverage.get('rows', []):
        sid = '%s %s' % (row['sub_question'], row.get('title', ''))
        fin = row.get('final')
        if fin == '未检索':
            gaps['not_searched'].append(sid)
        elif fin in ('未达标', 'failed'):
            gaps['partially_covered'].append(sid)
    write_json(os.path.join(args.out, 'coverage_matrix.json'), coverage)
    write_json(os.path.join(args.out, 'gap_analysis.json'), {
        'case_id': case_id,
        'rule': '空白只从覆盖矩阵导出：未检索=不下结论；未达标/失败=部分覆盖；'
                '无任何检索命中支持的方向=高置信缺口（须在 evidence 中引用检索日志）',
        **gaps})

    result_path = os.path.join(args.out, 'result.json')
    result = load(result_path, {})
    result.update({
        'case_id': case_id,
        'status': 'success' if (verdict['ok'] and rc == 0 and
                                not gaps['not_searched']) else 'partial',
        'uncertainty': [u for u in (result.get('uncertainty') or [])
                        if 'phase1' not in str(u)] + [
            'journal_integrity_ok=%s' % verdict['ok'],
            'not_searched 子问题不下结论（见 gap_analysis.json）'],
        'six_aspects': {
            '问题拆解': 'decomposition_tree.json：%d 个子问题，依赖分层 %s' % (
                len(tree['sub_questions']),
                json.dumps(load(os.path.join(args.out, 'retrieval_plan.json'),
                                {}).get('layers'), ensure_ascii=False)),
            '检索覆盖': 'coverage_matrix.json（由 run_journal.jsonl 重算，override 均要求理由）',
            '证据回链': '见 evidence 回填与 synthesis.md 的 [E-xx] 锚点（由 Agent 填写）',
            '冲突证据': 'synthesis.md 冲突段：相互冲突的结论须并置呈现',
            '综合结论': 'synthesis.md（每条结论句带 [SQ-n][E-xx]）',
            '研究空白': 'gap_analysis.json（严格从覆盖矩阵导出）'},
        'journal': {'path': 'run_journal.jsonl', 'entries': verdict['entries'],
                    'chain_head': verdict['chain_head'],
                    'integrity_ok': verdict['ok']},
        'finalized_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'schema_version': 'deeprq-a/1.0'})
    oc = case.get('output_contract') or case.get('outputContract') or {}
    keys = oc if isinstance(oc, list) else (list(oc.keys()) if isinstance(oc, dict) else [])
    for k in keys:
        result.setdefault(k, result.get(k))
    write_json(result_path, result)

    print(json.dumps({'ok': True, 'journal_ok': verdict['ok'],
                      'status': result['status'],
                      'gaps': {k: len(v) for k, v in gaps.items()}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
