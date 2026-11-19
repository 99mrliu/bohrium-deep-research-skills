#!/usr/bin/env python3
"""Question decomposition: task text -> six-facet decomposition tree.

Deterministic scaffold + heuristic facet extraction. The scaffold is always
marked draft=True; the running agent must refine every sub-question's
search strings and acceptance criteria before wave W2 (the retrieval plan
refuses to compile non-draft SQ data into executable actions otherwise).
"""
import json
import re

FACETS = ['研究对象', '机制或干预', '对照', '结局指标', '时间范围', '证据要求']

_TIME_RE = re.compile(r'(20\d\d|19\d\d|近[一二三四五六七八九十\d]+\s*年|last\s+\d+\s+years?)')
_EN_TOKEN_RE = re.compile(r'[A-Za-z][A-Za-z0-9\-]{2,}')
_QUOTED_RE = re.compile(r'[“"]([^”"]{2,60})[”"]')

TYPE_RULES = [
    ('背景定界', ['背景', '概述', '现状', 'background', 'overview', 'landscape']),
    ('机制或方法', ['机制', '原理', '方法', '路径', 'mechanism', 'pathway', 'method']),
    ('比较与效果', ['比较', '对比', '优于', '效果', 'vs', 'versus', 'compare',
                 'outperform', 'effectiveness']),
    ('趋势与时间', ['趋势', '发展', '演变', '近年', 'trend', 'evolution',
                 'progress', 'recent']),
    ('研究空白', ['空白', '不足', '挑战', '局限', 'gap', 'challenge',
               'limitation', 'bottleneck']),
]


def _sentences(text):
    parts = re.split(r'[。！？!?；;\n]', text)
    return [p.strip() for p in parts if len(p.strip()) >= 6]


def extract_facets(task):
    sents = _sentences(task)
    facets = {k: [] for k in FACETS}
    for s in sents:
        if _TIME_RE.search(s):
            facets['时间范围'].append(s[:120])
        if any(k in s.lower() for k in
               ('比较', '对比', 'vs', 'versus', '优于', '相对')):
            facets['对照'].append(s[:120])
        if any(k in s.lower() for k in
               ('机制', '原理', '路径', 'mechanism', 'pathway')):
            facets['机制或干预'].append(s[:120])
        if any(k in s.lower() for k in
               ('指标', '评价', '性能', '效果', 'metric', 'outcome',
                'performance', 'efficacy')):
            facets['结局指标'].append(s[:120])
        if any(k in s.lower() for k in
               ('随机', '荟萃', 'meta', 'rct', 'cohort', '队列', '系统评价')):
            facets['证据要求'].append(s[:120])
    quoted = _QUOTED_RE.findall(task)
    if quoted:
        facets['研究对象'] = quoted[:5]
    en = [t for t in _EN_TOKEN_RE.findall(task)
          if t.lower() not in ('the', 'and', 'for', 'with', 'from', 'this',
                               'that', 'task', 'case', 'json', 'md')]
    facets['检索关键词候选'] = list(dict.fromkeys(en))[:12]
    return facets


def _classify(task):
    low = task.lower()
    types = [t for t, kws in TYPE_RULES if any(k in low for k in kws)]
    return types or ['背景定界', '比较与效果', '研究空白']


def build_tree(task, case_id, status):
    facets = extract_facets(task or '')
    types = _classify(task or '')
    kw = facets.get('检索关键词候选') or []
    core = ' '.join(kw[:4]) if kw else '<待提炼核心术语>'

    sqs = [
        {'id': 'SQ-1', 'title': '背景与对象定界', 'type': '背景定界',
         'depends_on': [],
         'searchable_form': {
             'zh': '%s 研究现状 综述' % core,
             'en': '%s review landscape state of the art' % core},
         'acceptance': '找到 ≥1 篇综述或立场论文可界定研究对象与术语口径',
         'fields_to_extract': ['研究对象定义', '常用术语', '综述性文献 DOI']},
        {'id': 'SQ-2', 'title': '机制/方法证据', 'type': '机制或方法',
         'depends_on': ['SQ-1'],
         'searchable_form': {
             'zh': '%s 机制 实验证据' % core,
             'en': '%s mechanism experimental evidence' % core},
         'acceptance': '找到 ≥2 篇含原始数据或明确机制主张的文献',
         'fields_to_extract': ['主张的结论句', '实验体系', '样本量/材料数',
                               '效应方向与量级']},
        {'id': 'SQ-3', 'title': '比较与效果证据', 'type': '比较与效果',
         'depends_on': ['SQ-1'],
         'searchable_form': {
             'zh': '%s 对比 基准 性能' % core,
             'en': '%s comparison benchmark performance' % core},
         'acceptance': '找到 ≥2 篇含对照/基准比较的研究，提取可比字段',
         'fields_to_extract': ['对照条件', '指标数值', '比较结论']},
        {'id': 'SQ-4', 'title': '趋势与时间范围', 'type': '趋势与时间',
         'depends_on': ['SQ-1'],
         'searchable_form': {
             'zh': '%s 发展趋势 年度' % core,
             'en': '%s trend recent years progress' % core},
         'acceptance': '按时间范围组织证据，说明该领域近年的方法/结论演变',
         'fields_to_extract': ['年份', '方法演进节点', '指标随时间变化']},
        {'id': 'SQ-5', 'title': '研究空白与局限', 'type': '研究空白',
         'depends_on': ['SQ-2', 'SQ-3'],
         'searchable_form': {
             'zh': '%s 局限 挑战 未解决' % core,
             'en': '%s limitations challenges open problems' % core},
         'acceptance': '空白结论必须能对应 coverage_matrix 中的检索缺口，'
                       '而非凭空判断',
         'fields_to_extract': ['被多篇文献共同承认的局限', '检索未覆盖的方向']},
    ]
    # keep only sub-question types the task actually asks about, but always
    # keep 背景定界 + 研究空白 as backbone
    keep = set(types) | {'背景定界', '研究空白'}
    selected = [s for s in sqs if s['type'] in keep]
    for i, sq in enumerate(selected, 1):
        sq['id'] = 'SQ-%d' % i
    idmap = {s['title']: s['id'] for s in selected}
    for sq in selected:
        sq['depends_on'] = [idmap.get('背景与对象定界', 'SQ-1') if d == 'SQ-1'
                            else d for d in sq['depends_on']]
        sq['depends_on'] = [d for d in sq['depends_on'] if d != sq['id']]
    if len(selected) < 3:
        status['warnings'].append('任务类型识别较窄，仅 %d 个子问题，建议人工复核拆解'
                                  % len(selected))
    return {'case_id': case_id,
            'facets': facets,
            'facet_note': '六要素中标注"检索关键词候选"的为启发式提取，'
                          'Agent 须在 W1 后核实修订',
            'sub_questions': selected,
            'draft': True,
            'quality_bar': ['每个 SQ 可独立检索（自带中英文检索式）',
                            'acceptance 字段给出明确的达标判据',
                            'depends_on 表达可并行/须先行的调度约束',
                            '禁止把原句改写成关键词充当 SQ']}
