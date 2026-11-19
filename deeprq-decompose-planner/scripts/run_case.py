#!/usr/bin/env python3
"""deeprq-decompose-planner: phase 1 entrypoint.

Reads /input/case.json + task.md, runs decomposition + retrieval planning,
writes all skeleton artifacts (incl. a partial result.json) to --out, and
creates the append-only run journal with its genesis hash-chain entry.
Stdlib only; deterministic; safe to re-run (idempotent overwrite).
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decompose
import plan
import journal as journal_mod


def sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def load_inputs(case_path, input_dir):
    with open(case_path, encoding='utf-8') as f:
        case = json.load(f)
    task = ''
    task_path = os.path.join(input_dir, 'task.md')
    if os.path.exists(task_path):
        with open(task_path, encoding='utf-8') as f:
            task = f.read()
    materials = []
    for root, _dirs, files in os.walk(input_dir):
        for name in sorted(files):
            p = os.path.join(root, name)
            rel = os.path.relpath(p, input_dir)
            if rel in ('case.json', 'task.md'):
                continue
            try:
                with open(p, 'rb') as f:
                    digest = sha16(f.read())
                materials.append({'path': rel, 'sha256_16': digest,
                                  'size': os.path.getsize(p)})
            except OSError as e:
                materials.append({'path': rel, 'error': str(e)})
    return case, task, materials


def contract_fields(case):
    oc = case.get('output_contract') or case.get('outputContract') or {}
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return []


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
    case, task, materials = load_inputs(args.case, args.input_dir)
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'

    status = {'blocked': [], 'warnings': []}
    if not task.strip():
        status['blocked'].append('task.md 缺失或为空：无法拆解研究问题')
    if not materials:
        status['warnings'].append('input-dir 除 case.json/task.md 外无材料文件')

    tree = decompose.build_tree(task, case_id, status)
    retrieval_plan = plan.build_plan(tree, status)

    write_json(os.path.join(args.out, 'decomposition_tree.json'), tree)
    write_json(os.path.join(args.out, 'retrieval_plan.json'), retrieval_plan)

    # coverage matrix skeleton: rows = sub-questions, columns = sources
    sources = sorted({a['source'] for w in retrieval_plan['waves']
                      for a in w['actions']}) or ['retrieval_api']
    coverage = {'case_id': case_id,
                'note': 'covered=已有成功检索并标注该SQ; failed=检索失败且未恢复; '
                        '未检索=尚无日志记录。可由 Agent 写 coverage_overrides.json 修正并注明理由。',
                'rows': [{'sub_question': sq['id'], 'title': sq['title'],
                          'depends_on': sq.get('depends_on', []),
                          **{s: '未检索' for s in sources}}
                         for sq in tree['sub_questions']]}
    write_json(os.path.join(args.out, 'coverage_matrix.json'), coverage)

    # journal genesis entry
    journal_path = os.path.join(args.out, 'run_journal.jsonl')
    journal_mod.init(journal_path, case_id)
    journal_mod.append(journal_path, tool='run_case', args={
        'case': args.case, 'input_dir': args.input_dir},
        results_count=1, results_digest=sha16(json.dumps(
            tree, ensure_ascii=False, sort_keys=True).encode()),
        note='phase1 完成：拆解树与检索计划已生成', sq='ALL', status='ok')

    # synthesis skeleton
    with open(os.path.join(args.out, 'synthesis.md'), 'w', encoding='utf-8') as f:
        f.write('# 综合结论骨架（%s）\n\n' % case_id)
        f.write('> 填写规则：每条结论句末尾必须带 [SQ-n][E-xx] 锚点；'
                '写不出锚点的句子移入"无法确定"段。\n\n')
        for sq in tree['sub_questions']:
            f.write('## %s %s\n\n（待填：结论句 + [E-xx] 证据锚点）\n\n' %
                    (sq['id'], sq['title']))
        f.write('## 冲突证据\n\n（待填：相互冲突的结论必须并置呈现，不得只取一方）\n\n')
        f.write('## 研究空白（仅依据 coverage_matrix 导出）\n\n'
                '- searched_but_absent：…\n- partially_covered：…\n'
                '- not_searched（不下结论）：…\n\n## 无法确定\n\n')

    fields = contract_fields(case)
    result = {
        'case_id': case_id,
        'status': 'partial' if not status['blocked'] else 'blocked',
        'research_output': None,
        'sources': [],
        'uncertainty': status['warnings'] + status['blocked'] + [
            'phase1 仅完成问题拆解与检索规划，证据与结论尚未回填'],
        'six_aspects': {
            '问题拆解': 'decomposition_tree.json（%d 个子问题，依赖 DAG 已标注）' %
                        len(tree['sub_questions']),
            '检索覆盖': 'retrieval_plan.json 三波次 + coverage_matrix.json（当前全"未检索"）',
            '证据回链': '待 W2/W3 波次回填 E-xx 证据后由 finalize 校验',
            '冲突证据': 'synthesis.md 冲突段待填',
            '综合结论': 'synthesis.md 骨架待填',
            '研究空白': '待 coverage_matrix 有数据后由 finalize 导出'},
        'artifacts': sorted(os.listdir(args.out)),
        'schema_version': 'deeprq-a/1.0'}
    for k in fields:
        result.setdefault(k, None)
    write_json(os.path.join(args.out, 'result.json'), result)

    manifest = {'case_id': case_id, 'skill': 'deeprq-decompose-planner/1.0',
                'python': sys.version.split()[0],
                'input_files': materials,
                'phase1_seconds': round(time.time() - t0, 3),
                'run_steps': ['load_inputs', 'decompose', 'plan',
                              'coverage_skeleton', 'journal_genesis',
                              'synthesis_skeleton', 'partial_result']}
    write_json(os.path.join(args.out, 'run_manifest.json'), manifest)

    print(json.dumps({'ok': True, 'case_id': case_id,
                      'sub_questions': len(tree['sub_questions']),
                      'waves': len(retrieval_plan['waves']),
                      'blocked': status['blocked'],
                      'out': args.out}, ensure_ascii=False))


if __name__ == '__main__':
    main()
