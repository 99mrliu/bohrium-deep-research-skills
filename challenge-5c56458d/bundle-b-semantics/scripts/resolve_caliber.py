#!/usr/bin/env python3
"""Turn a task question + data dictionary into an explicit caliber statement.

科研口径声明 (caliber statement) pins down, BEFORE querying: which fields the
question actually refers to, the analysis grain, the aggregations, the
filters/units, and — crucially — which task terms could NOT be mapped and
must not be guessed. The mapper is a transparent heuristic (name/alias/
meaning token overlap); every mapping shows its matched token so a reviewer
can veto it. Standard library only.

Usage:
  python resolve_caliber.py --task-file /input/task.md \
      --dictionary /app/work/data_dictionary.json \
      --out /app/work/caliber.json --md /app/work/caliber.md
"""
import argparse
import json
import os
import re
import sys

AGG_WORDS = {
    'mean': ['mean', 'average', 'avg', '平均', '均值'],
    'sum': ['sum', 'total', '总计', '合计', '总和'],
    'count': ['count', 'number of', '多少', '计数', '样本数', '多少条'],
    'max': ['max', 'maximum', 'largest', '最大', '最高'],
    'min': ['min', 'minimum', 'smallest', '最小', '最低'],
    'median': ['median', '中位数'],
    'std': ['std', 'standard deviation', '标准差'],
}
GROUP_WORDS = ['group by', 'by ', 'per ', 'each', '按', '分组', '各类', '每个', '不同']
FILTER_HINTS = ['where', 'only', '>=', '<=', '>', '<', 'between', '≥', '≤',
                '大于', '小于', '至少', '不超过', '仅', '筛选', '介于']


def tokens(text):
    return set(re.findall(r'[a-z0-9_]+|[一-鿿]+', text.lower()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--task', help='task text; or use --task-file')
    ap.add_argument('--task-file')
    ap.add_argument('--dictionary', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--md', required=True)
    args = ap.parse_args()
    text = args.task or ''
    if args.task_file and os.path.exists(args.task_file):
        text += '\n' + open(args.task_file, encoding='utf-8').read()
    if not text.strip():
        ap.error('empty task text')
    dic = json.load(open(args.dictionary, encoding='utf-8'))
    low = text.lower()
    tok = tokens(text)

    mappings, unmapped_notes = [], []
    for tname, tbody in dic['tables'].items():
        for f in tbody['fields']:
            cands = {f['column'].lower(), re.sub(r'[^a-z0-9]+', '_',
                                                 f['column'].lower())}
            if f.get('canonical'):
                cands.add(f['canonical'].lower())
            if f.get('meaning'):
                cands.add(f['meaning'].lower())
                cands.update(w for w in f['meaning'].lower().split() if len(w) > 3)
            hit = sorted(c for c in cands if c and (c in low or c in tok))
            if hit:
                mappings.append({'table': tname, 'column': f['column'],
                                 'role': f['role'], 'unit': f.get('unit'),
                                 'caliber': f.get('caliber'),
                                 'matched_tokens': hit[:4],
                                 'warning': f.get('warning')})
    aggs = sorted({a for a, words in AGG_WORDS.items()
                   if any(w in low for w in words)})
    groups = [m for m in mappings
              if m['role'] in ('coded_categorical', 'text_label',
                               'numeric_coded_category')
              and any(w in low for w in GROUP_WORDS)]
    filters = [w for w in FILTER_HINTS if w in low]
    mentioned = {m['column'] for m in mappings}
    for tname, tbody in dic['tables'].items():
        for a in dic.get('ambiguity_queue', []):
            if a['table'] == tname:
                unmapped_notes.append(a)

    traps = [m for m in mappings if m['role'] == 'numeric_coded_category'
             and any(a in aggs for a in ('mean', 'sum', 'std', 'median'))]
    caliber = {
        'tool': 'resolve_caliber.py (transparent heuristic; reviewer may veto)',
        'field_mappings': mappings,
        'aggregations_detected': aggs,
        'candidate_group_fields': [g['column'] for g in groups],
        'filter_hint_tokens': filters,
        'grain': ('one output row per %s' % ' × '.join(g['column'] for g in groups)
                  if groups else 'unspecified — state explicitly before querying'),
        'coded_field_trap': [{'column': t['column'], 'aggregations': aggs}
                             for t in traps],
        'unresolved_from_dictionary': unmapped_notes,
        'rules': [
            'grain must be stated in the final report',
            'coded/categorical fields: counts and proportions only',
            'every numeric result carries its unit from the dictionary',
            'unmapped task terms go to the ambiguity list, never guessed']}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(caliber, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lines = ['# 口径声明 (caliber statement, draft)', '',
             '## 字段映射（含匹配证据 token，可否决）', '']
    for m in mappings:
        lines.append('- `%s.%s`（%s；单位 %s）← 命中 %s%s' % (
            m['table'], m['column'], m['role'], m.get('unit') or '—',
            m['matched_tokens'],
            ' ⚠ ' + m['warning'] if m.get('warning') else ''))
    lines += ['', '## 聚合与粒度', '',
              '- 检测到的聚合：%s' % (', '.join(aggs) or '未检测到'),
              '- 候选分组字段：%s' % (', '.join(g['column'] for g in groups) or '无'),
              '- 粒度声明：%s' % caliber['grain'], '']
    if traps:
        lines.append('## ⚠ 编码型字段聚合陷阱')
        for t in traps:
            lines.append('- `%s` 是编码型字段，任务却要求数值聚合：按规则只给计数/比例，并在异常中说明。' % t['column'])
        lines.append('')
    if unmapped_notes:
        lines.append('## 未解决歧义（不得猜测，需任务方字典或显式取舍）')
        for a in unmapped_notes:
            lines.append('- `%s.%s`: %s' % (a['table'], a['column'], a['issue']))
        lines.append('')
    open(args.md, 'w', encoding='utf-8').write('\n'.join(lines))
    print(json.dumps({'out': args.out, 'mapped_fields': len(mappings),
                      'aggregations': aggs, 'traps': len(traps),
                      'unresolved': len(unmapped_notes)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
