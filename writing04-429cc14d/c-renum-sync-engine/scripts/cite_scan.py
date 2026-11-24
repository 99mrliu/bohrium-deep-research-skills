#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cite_scan.py — 引用标记扫描器（确定性 · 仅标准库 · 无网络）

把「稿件 + 文末文献列表」扫描成引用图的原始素材：

  occurrences.jsonl  每行一个标记出现：reading_order / 区域 / 行列 / 原标签 / 展开引用集
  labels.json        原标签 -> 稳定 id（sid-001…，按全局首现顺序赋号）、
                     文末列表条目、悬空标记清单、未引用条目清单

识别区域：正文 body、图注 figure_caption、表注 table_caption、
脚注 footnote（[^x]: 定义行或「注：」段）、附录 appendix（"附录/Appendix" 标题之后）。

识别标记：
  数字型    [3] [1-3] [2,5] [1,3-5]（排除脚注定义 [^x]）
  数字上标  ^[3]^ ^[1-3]^（本 bundle 的上标约定写法）
  著者-年   (Smith, 2020) / (Smith & Jones, 2020a) / （张三，2021）

用法：
  python3 cite_scan.py --manuscript FILE --references FILE --out DIR
退出码：0 成功；2 输入/参数错误。
"""
import argparse
import json
import os
import re
import sys

# ---------------- 标记正则 ----------------
NUMERIC_BODY = r'\d+(?:\s*(?:,|，|--|-|–|—)\s*\d+)*'
# 数字型方括号标记（排除脚注 [^x]）
NUMERIC_BRACKET_RE = re.compile(r'\[(?!\^)(?P<body>' + NUMERIC_BODY + r')\]')
# 数字上标约定：^[3] ^[1-3]^
NUMERIC_SUPER_RE = re.compile(r'\^\[(?P<body>' + NUMERIC_BODY + r')\]\^')
# 著者-年（西文半角括号）
AY_LATIN_RE = re.compile(
    r'\((?P<authors>[A-Z][A-Za-z\'\-]+(?:(?:\s+and\s+|\s*&\s*|,\s*)[A-Z][A-Za-z\'\-]+)*),\s*'
    r'(?P<year>\d{4})(?P<suffix>[a-z]?)\)')
# 著者-年（中文全角括号）
AY_CJK_RE = re.compile(r'（(?P<authors>[^（）\d，,]{1,40})，\s*(?P<year>\d{4})(?P<suffix>[a-z]?)）')
# renumber.py 在 plan 阶段使用的内部占位符（正常稿件中不应出现）
PLACEHOLDER_RE = re.compile(r'⟦(?P<body>[0-9,，\s]+)⟧')

# ---------------- 区域识别 ----------------
CAPTION_RE = re.compile(r'^\s*(图|表|Figure|Table)\s*\d+')
FIGURE_RE = re.compile(r'^\s*(图|Figure)\s*\d+', re.IGNORECASE)
FOOTNOTE_DEF_RE = re.compile(r'^\s*\[\^.+?\]:')
NOTE_RE = re.compile(r'^\s*注\s*[：:]')
APPENDIX_HEADING_RE = re.compile(r'^\s*(#+\s*)?(附录|Appendix)\b', re.IGNORECASE)
MD_HEADING_RE = re.compile(r'^\s*#+\s')

# ---------------- 文末列表条目 ----------------
REF_NUMERIC_RE = re.compile(r'^\s*\[(?P<label>\d+|\*)\]\s*(?P<text>.*?)\s*$')
REF_AY_RE = re.compile(
    r'^\s*(?P<authors>[^()\n]{1,120}?)\s*\((?P<year>\d{4})(?P<suffix>[a-z]?)\)\.?\s*(?P<text>.*?)\s*$')

RETAIN_TAG = '【未引用·保留】'  # 未引用但按任务要求保留的条目的标注


def expand_marker_body(body):
    """把标记体展开成原标签列表：'1-3'->['1','2','3']，'2,5'->['2','5']。
    非法区间（起点>终点）保留两端原样，交给 sync_verify 的 V4 判违规。"""
    refs = []
    for part in re.split(r'[,，]', body):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(\d+)\s*(?:--|-|–|—)\s*(\d+)$', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                refs.extend(str(i) for i in range(a, b + 1))
            else:
                refs.extend([str(a), str(b)])
        elif part.isdigit():
            refs.append(str(int(part)))
    return refs


def render_range_body(nums):
    """把编号集合渲染成区间折叠体：[1,2,3]->'1-3'，[1,2]->'1,2'，[1,3]->'1,3'。
    规则：连续长度 >=3 折叠为 a-b；长度为 2 不折叠。"""
    nums = sorted(set(int(n) for n in nums))
    if not nums:
        return ''
    parts = []

    def flush(a, b):
        if b - a >= 2:
            parts.append('%d-%d' % (a, b))
        elif b - a == 1:
            parts.extend([str(a), str(b)])
        else:
            parts.append(str(a))

    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        flush(start, prev)
        start = prev = n
    flush(start, prev)
    return ','.join(parts)


def ay_surname(authors):
    """从著者串取第一作者姓：'Smith, J. A.'->'Smith'；'Smith & Jones'->'Smith'；'张三'->'张三'。"""
    first = re.split(r',\s*&|\s+and\s+|\s*&\s*', authors.strip())[0]
    first = first.split(',')[0].strip()
    return first.split()[-1] if first.split() else first


def ay_key(authors, year, suffix):
    return '%s %s%s' % (ay_surname(authors), year, suffix)


def classify_regions(lines):
    """逐行打区域标签。附录标题之后直到下一个非附录 Markdown 标题均为 appendix。"""
    regions = []
    in_appendix = False
    for ln in lines:
        if APPENDIX_HEADING_RE.match(ln):
            in_appendix = True
        elif MD_HEADING_RE.match(ln):
            in_appendix = False
        if not ln.strip():
            regions.append('blank')
        elif in_appendix:
            regions.append('appendix')
        elif FOOTNOTE_DEF_RE.match(ln) or NOTE_RE.match(ln):
            regions.append('footnote')
        elif CAPTION_RE.match(ln):
            regions.append('figure_caption' if FIGURE_RE.match(ln) else 'table_caption')
        else:
            regions.append('body')
    return regions


def find_markers_in_line(line, include_placeholders=False):
    """返回 [(col, raw, style, body, refs)]，按列升序。"""
    found = []
    for m in NUMERIC_BRACKET_RE.finditer(line):
        # 跳过上标约定 ^[n]^ 的内部（避免与 NUMERIC_SUPER_RE 重复计数）
        if m.start() > 0 and line[m.start() - 1] == '^' and m.end() < len(line) and line[m.end()] == '^':
            continue
        found.append((m.start(), m.group(0), 'numeric-bracket',
                      m.group('body'), expand_marker_body(m.group('body'))))
    for m in NUMERIC_SUPER_RE.finditer(line):
        found.append((m.start(), m.group(0), 'numeric-superscript',
                      m.group('body'), expand_marker_body(m.group('body'))))
    for m in AY_LATIN_RE.finditer(line):
        found.append((m.start(), m.group(0), 'author-year', m.group(0)[1:-1],
                      [ay_key(m.group('authors'), m.group('year'), m.group('suffix'))]))
    for m in AY_CJK_RE.finditer(line):
        found.append((m.start(), m.group(0), 'author-year-cjk', m.group(0)[1:-1],
                      [ay_key(m.group('authors'), m.group('year'), m.group('suffix'))]))
    if include_placeholders:
        for m in PLACEHOLDER_RE.finditer(line):
            refs = [p.strip() for p in re.split(r'[,，]', m.group('body')) if p.strip()]
            found.append((m.start(), m.group(0), 'placeholder', m.group('body'), refs))
    found.sort(key=lambda t: (t[0], t[1]))
    return found


def scan_manuscript_text(text, include_placeholders=False):
    """扫描稿件全文，返回 (occurrences, meta)。
    occurrences 按真实阅读序（行升序、行内列升序）编 reading_order（自 1）。"""
    lines = text.split('\n')
    regions = classify_regions(lines)
    para_of_line = []
    pidx = -1
    prev_blank = True
    for ln in lines:
        if ln.strip():
            if prev_blank:
                pidx += 1
            para_of_line.append(pidx)
            prev_blank = False
        else:
            para_of_line.append(-1)
            prev_blank = True
    occurrences = []
    ro = 0
    for i, (line, region) in enumerate(zip(lines, regions), start=1):
        if region == 'blank':
            continue
        for (col, raw, style, body, refs) in find_markers_in_line(line, include_placeholders):
            ro += 1
            occurrences.append({
                'reading_order': ro,
                'region': region,
                'line': i,
                'col': col,
                'raw': raw,
                'style': style,
                'body': body,
                'refs': refs,
                'para': para_of_line[i - 1],
            })
    region_counts = {}
    for occ in occurrences:
        region_counts[occ['region']] = region_counts.get(occ['region'], 0) + 1
    meta = {'line_count': len(lines), 'region_counts': region_counts, 'regions': regions}
    return occurrences, meta


def parse_references_text(text):
    """解析文末文献列表。返回条目列表：
    数字型 {'kind':'numeric','label','text','line'}
    著者-年 {'kind':'author-year','label'(=key),'authors','surname','year','suffix','text','line',
             'authors_sort','title_sort'}
    无法解析的非空行记入返回值的 'unparsed'（由调用方另行询问）。"""
    entries = []
    unparsed = []
    for i, ln in enumerate(text.split('\n'), start=1):
        if not ln.strip():
            continue
        m = REF_NUMERIC_RE.match(ln)
        if m:
            label = m.group('label')
            entries.append({'kind': 'numeric',
                            'label': str(int(label)) if label.isdigit() else '*',
                            'text': m.group('text'), 'line': i})
            continue
        m = REF_AY_RE.match(ln)
        if m:
            authors = m.group('authors').strip()
            surname = ay_surname(authors)
            key = '%s %s%s' % (surname, m.group('year'), m.group('suffix'))
            title = m.group('text').split('.')[0].strip()
            entries.append({'kind': 'author-year', 'label': key,
                            'authors': authors, 'surname': surname,
                            'year': m.group('year'), 'suffix': m.group('suffix'),
                            'text': m.group('text'), 'line': i,
                            'authors_sort': re.sub(r'\s+', ' ', authors.lower()),
                            'title_sort': re.sub(r'\s+', ' ', title.lower())})
            continue
        unparsed.append({'line': i, 'text': ln.strip()})
    return entries, unparsed


def build_labels(occurrences, entries):
    """原标签 -> 稳定 id。sid 按全局首现顺序赋 sid-001…；
    从未被引用的列表条目按列表顺序续赋。返回 labels.json 的主体。"""
    label_set = []
    seen = set()
    for e in entries:
        if e['label'] not in seen:
            seen.add(e['label'])
            label_set.append(e['label'])
    cited_order = []
    cited = set()
    dangling = []
    for occ in occurrences:
        for r in occ['refs']:
            if r in seen:
                if r not in cited:
                    cited.add(r)
                    cited_order.append(r)
            else:
                if r not in dangling:
                    dangling.append(r)
    labels = {}
    sid_of = {}
    for k, lab in enumerate(cited_order + [l for l in label_set if l not in cited], start=1):
        sid = 'sid-%03d' % k
        labels[lab] = sid
        sid_of[sid] = lab
    uncited = [e['label'] for e in entries if e['label'] not in cited]
    n_num = sum(1 for o in occurrences if o['style'].startswith('numeric'))
    n_ay = sum(1 for o in occurrences if o['style'].startswith('author-year'))
    style_hint = 'numeric' if n_num and not n_ay else ('author-year' if n_ay and not n_num
                                                       else ('mixed' if n_num and n_ay else 'none'))
    return {
        'style_hint': style_hint,
        'labels': labels,
        'sid_to_label': sid_of,
        'entries': [{'sid': labels[e['label']], 'original_label': e['label'],
                     'kind': e['kind'], 'text': e['text'], 'ref_line': e['line']}
                    for e in entries if e['label'] in labels],
        'dangling': dangling,
        'uncited': uncited,
        'occurrence_count': len(occurrences),
        'reference_count': len(entries),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='引用标记扫描器（确定性，仅标准库）')
    ap.add_argument('--manuscript', required=True, help='稿件文本文件')
    ap.add_argument('--references', required=True, help='文末文献列表文件（每行一条）')
    ap.add_argument('--out', required=True, help='输出目录（occurrences.jsonl + labels.json）')
    args = ap.parse_args(argv)

    try:
        with open(args.manuscript, 'r', encoding='utf-8') as f:
            mtext = f.read()
        with open(args.references, 'r', encoding='utf-8') as f:
            rtext = f.read()
    except OSError as e:
        print('cite_scan: 读取输入失败: %s' % e, file=sys.stderr)
        return 2

    occurrences, meta = scan_manuscript_text(mtext)
    entries, unparsed = parse_references_text(rtext)
    labels = build_labels(occurrences, entries)
    labels['manuscript'] = os.path.basename(args.manuscript)
    labels['references'] = os.path.basename(args.references)
    labels['region_counts'] = meta['region_counts']
    labels['unparsed_reference_lines'] = unparsed

    os.makedirs(args.out, exist_ok=True)
    occ_path = os.path.join(args.out, 'occurrences.jsonl')
    lab_path = os.path.join(args.out, 'labels.json')
    with open(occ_path, 'w', encoding='utf-8') as f:
        for occ in occurrences:
            f.write(json.dumps(occ, ensure_ascii=False) + '\n')
    with open(lab_path, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(json.dumps({
        'occurrences': len(occurrences),
        'references': len(entries),
        'dangling': labels['dangling'],
        'uncited': labels['uncited'],
        'style_hint': labels['style_hint'],
        'region_counts': meta['region_counts'],
        'out': [occ_path, lab_path],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
