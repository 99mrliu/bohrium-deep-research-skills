#!/usr/bin/env python3
"""Retrieval planning: decomposition tree -> wave-based plan with a
dependency DAG, stop conditions, dedup keys and budget allocation."""
import json

DEFAULT_BUDGET = {'model_requests_max': 60, 'retrieval_calls_max': 25,
                  'reserve_for_finalization': 6}


def _layers(sqs):
    ids = {s['id'] for s in sqs}
    deps = {s['id']: [d for d in s.get('depends_on', []) if d in ids]
            for s in sqs}
    done, layers = set(), []
    remaining = set(ids)
    while remaining:
        layer = sorted(i for i in remaining
                       if all(d in done for d in deps[i]))
        if not layer:  # cycle
            layer = sorted(remaining)
        layers.append(layer)
        done |= set(layer)
        remaining -= set(layer)
    return layers


def build_plan(tree, status=None):
    sqs = tree['sub_questions']
    layers = _layers(sqs)
    by_id = {s['id']: s for s in sqs}

    waves = []
    waves.append({'wave': 'W1', 'purpose': '背景定界与术语核实（先行，结果共享给全部 SQ）',
                  'parallel': False,
                  'actions': [
                      {'id': 'W1-1', 'sub_questions': ['ALL'], 'source': 'retrieval_api',
                       'query': by_id.get('SQ-1', {}).get('searchable_form', {}).get('en', ''),
                       'stop': '命中 ≥3 篇相关文献或连续 2 次新增相关数为 0',
                       'dedup_key': 'doi>首作者+年份+标题前30字符'}]})
    w2 = {'wave': 'W2', 'purpose': '各 SQ 并行检索（依赖分层内可并发）',
          'parallel': True, 'actions': []}
    for li, layer in enumerate(layers):
        for sq_id in layer:
            sq = by_id[sq_id]
            for lang in ('en', 'zh'):
                w2['actions'].append({
                    'id': 'W2-%s-%s' % (sq_id, lang),
                    'sub_questions': [sq_id], 'source': 'retrieval_api',
                    'depends_layer': li,
                    'query': sq['searchable_form'][lang],
                    'stop': '每 SQ 相关命中 ≥3 篇或连续 2 次检索新增相关数=0',
                    'dedup_key': 'doi>首作者+年份+标题前30字符',
                    'shared_hits_note': '一次检索的命中可被多个 SQ 标注，'
                                        '禁止为另一 SQ 重复提交同一检索式'})
    waves.append(w2)
    waves.append({'wave': 'W3', 'purpose': '缺口补检（仅当 coverage_matrix 显示 SQ 未达标）',
                  'parallel': True,
                  'trigger': 'coverage_matrix 中该 SQ 所有来源为 未检索/未达标',
                  'actions': [
                      {'id': 'W3-X', 'sub_questions': ['<未达标SQ>'],
                       'source': 'web_or_local_material',
                       'query': '<放宽后的检索式：去限定词/换同义词/降时间精度>',
                       'stop': '补检 1 轮后仍无命中则记为检索缺口，进入空白分析',
                       'dedup_key': 'doi>首作者+年份+标题前30字符'}]})

    n_actions = sum(len(w['actions']) for w in waves)
    budget = dict(DEFAULT_BUDGET)
    budget['planned_retrieval_calls'] = n_actions
    budget['w2_parallelism_note'] = '同层动作可并发提交，合并结果按 dedup_key 去重'
    if budget['planned_retrieval_calls'] > budget['retrieval_calls_max']:
        (status or {}).setdefault('warnings', []).append(
            '计划检索动作数 %d 超过预算 %d，请合并 SQ 或收紧停止条件'
            % (n_actions, budget['retrieval_calls_max']))

    return {'case_id': tree['case_id'], 'waves': waves, 'budget': budget,
            'layers': layers,
            'dispatch_rule': 'W1 完成并修订 draft 拆解后，才允许派发 W2；'
                             'W3 只在 coverage_matrix 证明存在缺口时触发',
            'repeat_search_policy': '同一检索式（规范化后）全链路只允许提交一次；'
                                    '重复需求通过命中共享满足'}


if __name__ == '__main__':
    import sys
    with open(sys.argv[1], encoding='utf-8') as f:
        tree = json.load(f)
    print(json.dumps(build_plan(tree), ensure_ascii=False, indent=2))
