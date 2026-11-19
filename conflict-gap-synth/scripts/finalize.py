#!/usr/bin/env python3
"""conflict-gap-synth: finalization.

Computes coverage-driven gap analysis, per-topic evidence grades, checks
conflict adjudications are filled, and writes the final result.json.
Stdlib only.
"""
import argparse
import json
import os
import time

RAW_DESIGNS = {'rct', 'cohort'}


def load(path, default=None):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def grade_topic(rows):
    """A/B/C/D grading per the SKILL grading rule."""
    if not rows:
        return 'D', '无研究行'
    raw = [r for r in rows if r.get('design') in RAW_DESIGNS]
    dirs = {r['direction'] for r in rows}
    if len(raw) >= 2 and len(dirs) == 1 and 'mixed' not in dirs:
        return 'A', '%d 项原始数据研究且方向一致(%s)' % (len(raw), dirs)
    if len(raw) == 1:
        return 'B', '1 项原始数据研究（单篇，外推需谨慎）'
    if rows and all(r.get('design') in ('review', 'opinion') for r in rows):
        if len(dirs) == 1 and len(rows) >= 2:
            return 'B', '仅综述但多篇方向一致'
        return 'C', '仅综述/观点且方向不完全一致'
    small = [r for r in rows
             if str(r.get('n') or '').isdigit() and int(r['n']) < 30]
    if len(rows) == 1 and small:
        return 'C', '单项小样本(n<30)'
    return 'C', '证据组合未达 A/B（见各行 design/direction）'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    case = load(args.case, {})
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'
    matrix = load(os.path.join(args.out, 'study_matrix.json'), {'rows': []})
    topics_cfg = load(os.path.join(args.work, 'topics.json'),
                      {'topics': []})
    conflicts = load(os.path.join(args.out, 'conflict_register.json'),
                     {'conflict_pairs': []})

    topics = [t['name'] if isinstance(t, dict) else t
              for t in topics_cfg.get('topics', [])]
    searched = {t['name'] if isinstance(t, dict) else t: bool(
        t.get('searched')) if isinstance(t, dict) else False
        for t in topics_cfg.get('topics', [])}

    rows_by_topic = {}
    for r in matrix['rows']:
        rows_by_topic.setdefault(r['topic'], []).append(r)

    coverage, gaps, grades = {}, {'searched_but_absent': [],
                                  'partially_covered': [],
                                  'not_searched': []}, []
    for t in topics:
        rows = rows_by_topic.get(t, [])
        coverage[t] = {'studies': len(rows), 'searched': searched.get(t, False)}
        if not searched.get(t, False):
            gaps['not_searched'].append(t)
        elif not rows:
            gaps['searched_but_absent'].append(t)
        elif len(rows) < 2:
            gaps['partially_covered'].append(t)
        g, why = grade_topic(rows)
        grades.append({'topic': t, 'grade': g, 'rationale': why,
                       'rows': [matrix['rows'].index(r) + 1 for r in rows]})
    # matrix rows whose topic is outside the topic list still get graded
    for t, rows in rows_by_topic.items():
        if t not in topics:
            g, why = grade_topic(rows)
            grades.append({'topic': t, 'grade': g, 'rationale':
                           why + '（不在 topics.json 清单内，请核对拆解）',
                           'rows': [matrix['rows'].index(r) + 1 for r in rows]})

    write_json(os.path.join(args.out, 'gap_analysis.json'), {
        'case_id': case_id, 'coverage': coverage, 'gaps': gaps,
        'rule': '空白从覆盖矩阵导出：searched 且无研究=高置信缺口；'
                '检索<2篇=部分覆盖；未检索=不下结论'})
    write_json(os.path.join(args.out, 'evidence_grades.json'), {
        'case_id': case_id, 'grades': grades,
        'grading_rule': {'A': '≥2 原始数据研究且方向一致',
                         'B': '1 项原始数据或仅综述多篇一致',
                         'C': '仅综述/观点或单项小样本', 'D': '无法确定'}})

    missing_adj = [p['pair_id'] for p in conflicts['conflict_pairs']
                   if not p.get('adjudication')]
    n_rows = len(matrix['rows'])
    ok = (n_rows > 0 and not missing_adj
          and not gaps['not_searched'])
    status = 'success' if ok else (
        'blocked' if n_rows == 0 else 'partial')

    result_path = os.path.join(args.out, 'result.json')
    result = load(result_path, {})
    result.update({
        'case_id': case_id,
        'status': status,
        'research_output': 'bounded_synthesis.md',
        'sources': [{'row': i + 1, **r} for i, r in
                    enumerate(matrix['rows'])],
        'uncertainty': ([('冲突对缺 adjudication：%s' % ','.join(missing_adj))]
                        if missing_adj else []) + [
            'not_searched 方向不下结论（见 gap_analysis.json）'] *
            (1 if gaps['not_searched'] else 0) + [
            'D 级方向仅表示材料未覆盖，不代表领域内无证据'],
        'six_aspects': {
            '问题拆解': 'topics.json %d 个方向' % len(topics),
            '检索覆盖': '%d 行研究；coverage 见 gap_analysis.json' % n_rows,
            '证据回链': '每行 source 必填；结论引用矩阵行号',
            '冲突证据': '%d 对冲突（裁定依据见 conflict_register.json）' % len(
                conflicts['conflict_pairs']),
            '综合结论': 'bounded_synthesis.md（[事实]/[推断]/[无法确定]+A/B/C/D）',
            '研究空白': '高置信缺口 %d 项；未检索 %d 项' % (
                len(gaps['searched_but_absent']),
                len(gaps['not_searched']))},
        'finalized_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'schema_version': 'cfsynth-c/1.0'})
    oc = case.get('output_contract') or case.get('outputContract') or {}
    keys = oc if isinstance(oc, list) else (
        list(oc.keys()) if isinstance(oc, dict) else [])
    for k in keys:
        result.setdefault(k, result.get(k))
    write_json(result_path, result)
    print(json.dumps({'ok': True, 'status': status,
                      'conflict_pairs': len(conflicts['conflict_pairs']),
                      'gaps': {k: len(v) for k, v in gaps.items()}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
