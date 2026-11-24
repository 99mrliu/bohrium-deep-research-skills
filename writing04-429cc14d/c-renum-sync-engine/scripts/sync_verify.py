#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_verify.py — 双向一致性核验 V1–V8（确定性 · 仅标准库 · 无网络）

对「编辑后稿件 + 编辑后文献表（可选 label_map）」执行八条规则：

  V1 无悬空：每个正文标记都能解析到文献列表条目
  V2 无多余：每个列表条目至少被引一次，或带 【未引用·保留】 标注按任务要求保留
  V3 编号连续：列表编号自 1 连续无跳号；正文实际使用的编号也自 1 连续
  V4 区间合法：所有 [a-b] 满足 a<=b 且端点存在于列表
  V5 样式统一：全稿数字标记只用一种形态（[n] 与 ^[n]^ 不混用；不与著者-年混用）；
               且无未渲染占位符残留
  V6 著者-年一致：正文 (作者, 年份+后缀) 与列表条目一一对应（纯数字稿自动跳过）
  V7 区域覆盖：图注/表注/脚注/附录中的标记全部纳入编号序列
  V8 重算幂等：对已同步稿件以空 ops 再跑一次重编号，要求零变化（自证幂等）

用法：
  python3 sync_verify.py --manuscript FILE --references FILE [--label_map FILE] --out DIR
输出：sync_report.json + sync_report.md。
退出码：0 全部通过；1 存在违规；2 输入/参数错误。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cite_scan
import renumber
from cite_scan import scan_manuscript_text, parse_references_text, RETAIN_TAG

RULE_NAMES = {
    'V1': '无悬空标记（每个正文标记可解析到列表条目）',
    'V2': '无多余条目（每条被引至少一次，或带保留标注）',
    'V3': '编号自 1 连续无跳号（列表与正文使用双侧检查）',
    'V4': '区间合法（a<=b 且端点存在）',
    'V5': '样式统一（不混用标记形态，无占位符残留）',
    'V6': '著者-年后缀正文与列表一致',
    'V7': '图注/表注/脚注/附录标记全部纳入编号',
    'V8': '重算幂等（空 ops 重跑零变化）',
}

RANGE_PART_RE = re.compile(r'^(\d+)\s*(?:--|-|–|—)\s*(\d+)$')
SPECIAL_REGIONS = ('figure_caption', 'table_caption', 'footnote', 'appendix')


def _detect_style(occs, entries, label_map):
    if label_map and label_map.get('style'):
        return label_map['style']
    styles = {o['style'] for o in occs}
    if 'numeric-superscript' in styles and 'numeric-bracket' not in styles:
        return 'numeric-superscript'
    if any(o['style'].startswith('numeric') for o in occs) or \
            any(e['kind'] == 'numeric' for e in entries):
        return 'numeric-bracket'
    return 'author-year'


def run_verification(mtext, rtext, label_map=None):
    occs, meta = scan_manuscript_text(mtext)
    entries, unparsed = parse_references_text(rtext)
    numeric_labels = sorted(int(e['label']) for e in entries
                            if e['kind'] == 'numeric' and e['label'] != '*')
    numeric_set = {str(n) for n in numeric_labels}
    star_entries = [e for e in entries if e['label'] == '*']
    ay_entries = [e for e in entries if e['kind'] == 'author-year']
    ay_list_keys = {e['label'] for e in ay_entries}

    num_occs = [o for o in occs if o['style'] in ('numeric-bracket', 'numeric-superscript')]
    ay_occs = [o for o in occs if o['style'].startswith('author-year')]
    cited = []
    for o in num_occs:
        cited.extend(o['refs'])
    cited_set = set(cited)

    results = {}

    # ---- V1 无悬空 ----
    dangling = [{'reading_order': o['reading_order'], 'line': o['line'], 'col': o['col'],
                 'region': o['region'], 'raw': o['raw'],
                 'unresolved': [r for r in o['refs'] if r not in numeric_set]}
                for o in num_occs if any(r not in numeric_set for r in o['refs'])]
    results['V1'] = {'pass': not dangling,
                     'detail': '全部 %d 个数字标记均可解析' % len(num_occs) if not dangling
                     else '%d 个悬空标记: %s' % (len(dangling), json.dumps(
                         dangling[:10], ensure_ascii=False))}

    # ---- V2 无多余条目 ----
    problems = []
    for e in entries:
        if e['kind'] == 'numeric' and e['label'] != '*':
            if e['label'] not in cited_set and RETAIN_TAG not in e['text']:
                problems.append({'label': e['label'], 'ref_line': e['line'],
                                 'problem': '列表条目未被引用且无保留标注'})
        elif e['label'] == '*':
            if RETAIN_TAG not in e['text']:
                problems.append({'label': '*', 'ref_line': e['line'],
                                 'problem': '保留条目缺少 ' + RETAIN_TAG + ' 标注'})
    for e in ay_entries:
        if e['label'] not in {r for o in ay_occs for r in o['refs']} \
                and RETAIN_TAG not in e['text']:
            problems.append({'label': e['label'], 'ref_line': e['line'],
                             'problem': '著者-年条目未被引用且无保留标注'})
    results['V2'] = {'pass': not problems,
                     'detail': '全部列表条目均被引用或已标注保留' if not problems
                     else json.dumps(problems[:10], ensure_ascii=False)}

    # ---- V3 编号连续 ----
    v3_problems = []
    if numeric_labels != list(range(1, len(numeric_labels) + 1)):
        v3_problems.append('列表编号 %s 不是自 1 连续' % numeric_labels)
    if cited_set:
        cited_sorted = sorted(int(c) for c in cited_set)
        if cited_sorted != list(range(1, cited_sorted[-1] + 1)):
            v3_problems.append('正文使用的编号 %s 存在跳号' % cited_sorted)
    results['V3'] = {'pass': not v3_problems,
                     'detail': '列表与正文编号均自 1 连续' if not v3_problems
                     else '；'.join(v3_problems)}

    # ---- V4 区间合法 ----
    bad_ranges = []
    for o in num_occs:
        for part in re.split(r'[,，]', o['body']):
            m = RANGE_PART_RE.match(part.strip())
            if not m:
                continue
            a, b = int(m.group(1)), int(m.group(2))
            probs = []
            if a > b:
                probs.append('起点 %d 大于终点 %d' % (a, b))
            for x in (a, b):
                if str(x) not in numeric_set:
                    probs.append('端点 %d 不在文献列表中' % x)
            if probs:
                bad_ranges.append({'line': o['line'], 'raw': o['raw'], 'problems': probs})
    results['V4'] = {'pass': not bad_ranges,
                     'detail': '全部区间合法' if not bad_ranges
                     else json.dumps(bad_ranges[:10], ensure_ascii=False)}

    # ---- V5 样式统一 ----
    v5_problems = []
    num_styles = {o['style'] for o in num_occs}
    if len(num_styles) > 1:
        v5_problems.append('数字标记形态混用: %s' % sorted(num_styles))
    if num_occs and ay_occs:
        v5_problems.append('数字标记与著者-年标记混用（%d/%d 处）' % (len(num_occs), len(ay_occs)))
    if '⟦' in mtext or '⟧' in mtext:
        v5_problems.append('存在未渲染占位符 ⟦…⟧')
    results['V5'] = {'pass': not v5_problems,
                     'detail': '标记样式全稿统一' if not v5_problems
                     else '；'.join(v5_problems)}

    # ---- V6 著者-年后缀一致 ----
    if not ay_occs and not ay_entries:
        results['V6'] = {'pass': True, 'detail': '不适用（非著者-年制），自动跳过'}
    else:
        ay_text_keys = {r for o in ay_occs for r in o['refs']}
        only_text = sorted(ay_text_keys - ay_list_keys)
        only_list = sorted(ay_list_keys - ay_text_keys)
        ok = not only_text and not (only_list and False)  # 列表多出的未引条目由 V2 管
        detail = '著者-年后缀正文与列表一致' if ok else \
            '正文出现而列表缺失: %s' % only_text
        results['V6'] = {'pass': ok, 'detail': detail}

    # ---- V7 区域覆盖 ----
    region_counts = {}
    region_bad = []
    for o in occs:
        if o['region'] in SPECIAL_REGIONS:
            region_counts[o['region']] = region_counts.get(o['region'], 0) + 1
            if o['style'].startswith('numeric') and any(r not in numeric_set for r in o['refs']):
                region_bad.append({'region': o['region'], 'line': o['line'], 'raw': o['raw']})
    results['V7'] = {'pass': not region_bad,
                     'detail': '特殊区域标记计数 %s，全部纳入编号' % region_counts if not region_bad
                     else '特殊区域存在未纳入编号的标记: %s' % json.dumps(
                         region_bad[:10], ensure_ascii=False)}

    # ---- V8 重算幂等 ----
    style = _detect_style(occs, entries, label_map)
    try:
        lm = renumber.compute_plan(mtext, rtext, [], style)
        identity = all(m['new_label'] == m['original_label']
                       or m['status'] == 'uncited_retained' for m in lm['mappings'])
        same_text = (lm['edited_manuscript_text'] == mtext
                     and lm['edited_references_text'] == rtext)
        v8_pass = identity and same_text
        if v8_pass:
            v8_detail = '空 ops 重算零变化（样式 %s）' % style
        else:
            why = []
            if not identity:
                why.append('映射非恒等: %s' % [
                    (m['original_label'], m['new_label']) for m in lm['mappings']
                    if m['new_label'] != m['original_label']
                    and m['status'] != 'uncited_retained'][:10])
            if not same_text:
                why.append('重渲染文本与输入不一致')
            v8_detail = '；'.join(why)
    except renumber.PlanError as e:
        v8_pass = False
        v8_detail = '空 ops 重算抛错: %s' % e
    results['V8'] = {'pass': v8_pass, 'detail': v8_detail}

    all_pass = all(r['pass'] for r in results.values())
    return {
        'all_pass': all_pass,
        'style_detected': style,
        'rules': {k: {'name': RULE_NAMES[k], 'pass': v['pass'], 'detail': v['detail']}
                  for k, v in results.items()},
        'summary': {
            'occurrences': len(occs),
            'numeric_markers': len(num_occs),
            'author_year_markers': len(ay_occs),
            'reference_entries': len(entries),
            'numeric_labels': numeric_labels,
            'retained_uncited_entries': len(star_entries),
            'unparsed_reference_lines': unparsed,
            'failed_rules': [k for k, v in results.items() if not v['pass']],
        },
    }


def render_markdown(report):
    lines = ['# 双向一致性核验报告（V1–V8）', '']
    lines.append('总体结论：**%s**' % ('全部通过 ✅' if report['all_pass'] else '存在违规 ❌'))
    lines.append('')
    lines.append('| 规则 | 内容 | 结果 | 说明 |')
    lines.append('| --- | --- | --- | --- |')
    for k in sorted(report['rules']):
        r = report['rules'][k]
        lines.append('| %s | %s | %s | %s |' % (
            k, r['name'], '通过' if r['pass'] else '**违规**',
            str(r['detail']).replace('|', '\\|').replace('\n', ' ')))
    lines.append('')
    s = report['summary']
    lines.append('- 标记总数 %d（数字 %d / 著者-年 %d），列表条目 %d，保留未引用条目 %d'
                 % (s['occurrences'], s['numeric_markers'], s['author_year_markers'],
                    s['reference_entries'], s['retained_uncited_entries']))
    if s['failed_rules']:
        lines.append('- 未通过规则：%s' % ', '.join(s['failed_rules']))
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='双向一致性核验 V1–V8（确定性，仅标准库）')
    ap.add_argument('--manuscript', required=True, help='编辑后稿件')
    ap.add_argument('--references', required=True, help='编辑后文献表')
    ap.add_argument('--label_map', default=None, help='可选 label_map.json（提供样式等信息）')
    ap.add_argument('--out', default='.', help='报告输出目录')
    args = ap.parse_args(argv)

    try:
        with open(args.manuscript, 'r', encoding='utf-8') as f:
            mtext = f.read()
        with open(args.references, 'r', encoding='utf-8') as f:
            rtext = f.read()
        label_map = None
        if args.label_map:
            with open(args.label_map, 'r', encoding='utf-8') as f:
                label_map = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print('sync_verify: 读取输入失败: %s' % e, file=sys.stderr)
        return 2

    report = run_verification(mtext, rtext, label_map)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'sync_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    with open(os.path.join(args.out, 'sync_report.md'), 'w', encoding='utf-8') as f:
        f.write(render_markdown(report))

    print(json.dumps({'all_pass': report['all_pass'],
                      'failed_rules': report['summary']['failed_rules']},
                     ensure_ascii=False))
    return 0 if report['all_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
