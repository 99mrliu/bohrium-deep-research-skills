#!/usr/bin/env python3
"""conflict-gap-synth: phase 1 entrypoint.

Scaffolds the study matrix, conflict register, grading and gap-analysis
artifacts and writes a partial result.json. Stdlib only; idempotent.
"""
import argparse
import json
import os
import sys
import time


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    t0 = time.time()
    with open(args.case, encoding='utf-8') as f:
        case = json.load(f)
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'
    task_path = os.path.join(args.input_dir, 'task.md')
    task = ''
    if os.path.exists(task_path):
        with open(task_path, encoding='utf-8') as f:
            task = f.read()

    # sub-topic scaffold: agent edits topics.json in work dir if needed
    topics_path = os.path.join(args.work, 'topics.json')
    if not os.path.exists(topics_path):
        write_json(topics_path, {'case_id': case_id,
                                 'note': '从 task.md 拆解的子问题方向；Agent 可修订；'
                                         'searched=true 表示已执行过检索动作',
                                 'topics': [{'name': t.strip(),
                                             'searched': False}
                                            for t in ('综述对象定界,机制或方法,'
                                                      '比较与效果,趋势,'
                                                      '研究空白').split(',')]})

    write_json(os.path.join(args.out, 'study_matrix.json'), {
        'case_id': case_id,
        'schema': {'study': 'str 必填，首作者+年份', 'design':
                   'rct|meta|cohort|review|opinion|n/a', 'n':
                   'int|str|null 样本量', 'population': 'str 人群/材料体系',
                   'topic': 'str 子问题方向', 'outcome': 'str 指标',
                   'direction': 'positive|negative|mixed|none',
                   'magnitude': 'str|null 效应量级', 'limits': 'str 局限',
                   'source': 'str 必填 DOI/URL/材料路径'},
        'rows': []})
    write_json(os.path.join(args.out, 'conflict_register.json'), {
        'case_id': case_id, 'conflict_pairs': [],
        'rule': '同 (topic,outcome) 内 direction 互斥的研究对；每对必须填'
                ' adjudication（设计层级/样本量/一致性依据），禁止空话'})
    write_json(os.path.join(args.out, 'evidence_grades.json'), {
        'case_id': case_id, 'grades': [], 'grading_rule': {
            'A': '≥2 项原始数据研究(design=rct/cohort)且方向一致',
            'B': '1 项原始数据研究，或仅综述但多篇一致',
            'C': '仅综述/观点或单项小样本(n<30)',
            'D': '无法确定/材料未覆盖'}})
    write_json(os.path.join(args.out, 'gap_analysis.json'), {
        'case_id': case_id, 'coverage': {}, 'gaps': {
            'searched_but_absent': [], 'partially_covered': [],
            'not_searched': []},
        'rule': '空白从覆盖矩阵导出：有检索无研究=高置信；部分覆盖=中等；'
                '未检索=不下结论'})

    with open(os.path.join(args.out, 'bounded_synthesis.md'), 'w',
              encoding='utf-8') as f:
        f.write('# 有边界的综合结论（%s）\n\n' % case_id)
        f.write('> 逐句前缀 [事实]/[推断]/[无法确定]；结论句末带证据等级'
                '（A/B/C/D）与矩阵行号引用。\n\n')
        f.write('## 结论\n\n（待填）\n\n## 冲突证据（并置呈现 + 裁定依据）'
                '\n\n（待填）\n\n## 研究空白（引用 gap_analysis 字段）\n\n'
                '（待填）\n\n## 无法确定\n\n（待填）\n')

    result = {
        'case_id': case_id,
        'status': 'partial',
        'research_output': None,
        'sources': [],
        'uncertainty': ['phase1 仅生成比较矩阵与空白骨架，研究行与结论待回填'],
        'six_aspects': {
            '问题拆解': 'work/topics.json 的子问题方向（Agent 可修订）',
            '检索覆盖': '矩阵行数即当前覆盖；gap_analysis 待 finalize 计算',
            '证据回链': '每行 source 字段必填；结论引用矩阵行号',
            '冲突证据': 'conflict_register.json 待 conflicts.py 检出',
            '综合结论': 'bounded_synthesis.md（[事实]/[推断]/[无法确定]+等级）',
            '研究空白': 'gap_analysis.json（从覆盖矩阵导出）'},
        'schema_version': 'cfsynth-c/1.0'}
    oc = case.get('output_contract') or case.get('outputContract') or {}
    keys = oc if isinstance(oc, list) else (
        list(oc.keys()) if isinstance(oc, dict) else [])
    for k in keys:
        result.setdefault(k, None)
    write_json(os.path.join(args.out, 'result.json'), result)
    write_json(os.path.join(args.out, 'run_manifest.json'), {
        'case_id': case_id, 'skill': 'conflict-gap-synth/1.0',
        'python': sys.version.split()[0],
        'phase1_seconds': round(time.time() - t0, 3),
        'run_steps': ['scaffold_matrix', 'scaffold_conflict_register',
                      'scaffold_grades', 'scaffold_gaps',
                      'bounded_synthesis_skeleton', 'partial_result']})
    print(json.dumps({'ok': True, 'scaffold': ['study_matrix',
                      'conflict_register', 'evidence_grades', 'gap_analysis'],
                      'studies': 0, 'task_chars': len(task)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
