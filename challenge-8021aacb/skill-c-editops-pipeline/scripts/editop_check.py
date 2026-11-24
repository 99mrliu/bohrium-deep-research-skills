#!/usr/bin/env python3
"""editop_check.py -- 编辑操作 JSON 的机器校验。

每条 op 须满足 editop_dsl.md 的前置条件: op 类型合法、引用的块 ID 存在、
quote 逐字命中目标块、必需字段齐全。校验不过不得进入 apply 阶段。

用法:
    python3 editop_check.py BLOCKS_JSONL OPS_JSON OUT_JSON
"""
import json
import sys

OPS = {'move', 'merge', 'split', 'narrow', 'delete_duplicate', 'insert_transition',
       'reorder_section', 'add_limitation'}
REQUIRED = {
    'move': ['op', 'id', 'target', 'after'],
    'merge': ['op', 'id', 'target', 'into'],
    'split': ['op', 'id', 'target', 'at_quote'],
    'narrow': ['op', 'id', 'target', 'quote', 'replacement'],
    'delete_duplicate': ['op', 'id', 'target', 'duplicate_of'],
    'insert_transition': ['op', 'id', 'before', 'sentence'],
    'reorder_section': ['op', 'id', 'target', 'after'],
    'add_limitation': ['op', 'id', 'after', 'sentence'],
}


def load_blocks(path):
    blocks = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                b = json.loads(line)
                blocks[b['id']] = b
    return blocks


def check(blocks_path, ops_path, out_path):
    blocks = load_blocks(blocks_path)
    with open(ops_path, encoding='utf-8') as f:
        doc = json.load(f)
    ops = doc.get('ops', doc if isinstance(doc, list) else [])

    problems = []
    seen_ids = set()
    for i, op in enumerate(ops):
        oid = op.get('id', 'OP%03d' % (i + 1))
        if oid in seen_ids:
            problems.append({'id': oid, 'kind': 'duplicate_op_id'})
        seen_ids.add(oid)
        kind = op.get('op')
        if kind not in OPS:
            problems.append({'id': oid, 'kind': 'unknown_op', 'value': kind})
            continue
        for k in REQUIRED[kind]:
            if not op.get(k):
                problems.append({'id': oid, 'kind': 'missing_field', 'field': k})
        for ref in ('target', 'into', 'after', 'before', 'duplicate_of'):
            v = op.get(ref)
            if v and v not in blocks:
                problems.append({'id': oid, 'kind': 'bad_block_ref', 'field': ref,
                                 'value': v})
        tgt = blocks.get(op.get('target', ''))
        if tgt and op.get('quote'):
            if ' '.join(op['quote'].split()) not in ' '.join(tgt['text'].split()):
                problems.append({'id': oid, 'kind': 'quote_not_verbatim',
                                 'target': op['target']})
        if tgt and op.get('at_quote'):
            if ' '.join(op['at_quote'].split()) not in ' '.join(tgt['text'].split()):
                problems.append({'id': oid, 'kind': 'at_quote_not_in_target',
                                 'target': op['target']})

    report = {'ops': len(ops), 'problem_count': len(problems),
              'valid': not problems, 'problems': problems}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'ops': len(ops), 'valid': report['valid'],
                      'problems': len(problems)}, ensure_ascii=False))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: editop_check.py BLOCKS_JSONL OPS_JSON OUT_JSON')
    sys.exit(check(*sys.argv[1:4]))
