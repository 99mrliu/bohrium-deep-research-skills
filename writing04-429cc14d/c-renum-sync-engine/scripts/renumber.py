#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renumber.py — 编号重算与同步施加（确定性 · 仅标准库 · 无网络）

子命令：
  plan   依据 ops.json 把编辑操作施加到「原始稿件坐标」，重算 original->new 映射，
         渲染编辑后文本，写出 label_map.json（不落盘最终产物）。
         plan 内部会重新扫描稿件以保证坐标新鲜；若同时提供 --occurrences，
         会与重扫结果比对，不一致即报错（提示先重跑 cite_scan）。
  apply  读入 label_map.json，用相同输入完整复算一遍并逐字段比对；
         全部校验通过才原子写出 edited_manuscript.txt / edited_references.txt /
         label_map.json。任何不一致 -> 不写任何文件，退出码 1。

支持的操作（ops.json，坐标一律指向原始稿件）：
  delete_marker     {"op":"delete_marker","reading_order":N}
  insert_marker     {"op":"insert_marker","line":L,"col":C,"labels":["4","6"]}
                    或用 "after_text":"..." 代替 col（插入到该行该子串之后）
  merge_paragraphs  {"op":"merge_paragraphs","para_a":A,"para_b":B}
  move_section      {"op":"move_section","heading":"正则","after_heading":"正则"}
  merge_entries     {"op":"merge_entries","keep":"3","drop":"7"}

编号规则（顺序编码制）：按编辑后全局真实阅读序（含图注/表注/脚注/附录，
同一序列）的首现顺序赋 1..N；重复出现共享编号；多编号标记排序后做区间
折叠（连续 >=3 折叠为 a-b）。未引用条目追加 【未引用·保留】 并以 [*] 列于末尾。
著者-出版年制：文末列表按 (作者, 年, 题名) 字母序重排；同作者同年按题名
排序赋 a/b 后缀并回改正文标记。

退出码：0 成功；1 apply 校验失败；2 输入/操作错误（PlanError）。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cite_scan
from cite_scan import (scan_manuscript_text, parse_references_text, build_labels,
                       render_range_body, RETAIN_TAG)

FORMAT_VERSION = '1.0'
COMPARE_KEYS = ['format_version', 'style', 'ops', 'mappings', 'reference_order',
                'dangling_removed', 'uncited_retained',
                'edited_manuscript_text', 'edited_references_text']


class PlanError(Exception):
    """操作或输入数据层面的错误（exit 2）。"""


# ---------------- 文本级编辑原语 ----------------

def _tidy_after_delete(s):
    """删除标记后的空白规整：压缩连续空白、去掉标点前多余空格。"""
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = re.sub(r' +([.,;:!?])', r'\1', s)
    return s


def _paragraph_blocks(lines):
    """返回 [(start,end)]（含端点，0 基行号），段落 = 空行分隔的非空行块。"""
    blocks = []
    start = None
    for i, ln in enumerate(lines):
        if ln.strip():
            if start is None:
                start = i
        else:
            if start is not None:
                blocks.append((start, i - 1))
                start = None
    if start is not None:
        blocks.append((start, len(lines) - 1))
    return blocks


def _op_merge_paragraphs(lines, a, b):
    blocks = _paragraph_blocks(lines)
    if not (0 <= a < len(blocks) and 0 <= b < len(blocks)):
        raise PlanError('merge_paragraphs: 段落索引越界（共 %d 段，请求 %d/%d）'
                        % (len(blocks), a, b))
    if a == b:
        raise PlanError('merge_paragraphs: para_a 与 para_b 相同')
    if a > b:
        a, b = b, a
    (sa, ea), (sb, eb) = blocks[a], blocks[b]
    merged = ' '.join(l.strip() for l in lines[sa:ea + 1]) + \
             ' ' + ' '.join(l.strip() for l in lines[sb:eb + 1])
    return lines[:sa] + [merged] + lines[ea + 1:sb] + lines[eb + 1:]


def _heading_level(line):
    m = re.match(r'^\s*(#+)\s', line)
    if m:
        return len(m.group(1))
    s = line.strip()
    if re.match(r'^\d+\.\s+\S', s):
        return 2
    if re.match(r'^(附录|Appendix)\b', s, re.IGNORECASE):
        return 2
    return None


def _find_section(lines, pattern):
    rx = re.compile(pattern)
    hits = [i for i, ln in enumerate(lines) if _heading_level(ln) is not None and rx.search(ln)]
    if not hits:
        raise PlanError('move_section: 未找到标题 %r' % pattern)
    if len(hits) > 1:
        raise PlanError('move_section: 标题 %r 匹配到 %d 处，无法唯一确定' % (pattern, len(hits)))
    s = hits[0]
    lvl = _heading_level(lines[s])
    e = len(lines)
    for j in range(s + 1, len(lines)):
        lv = _heading_level(lines[j])
        if lv is not None and lv <= lvl:
            e = j
            break
    while e - 1 > s and not lines[e - 1].strip():
        e -= 1
    return s, e


def _op_move_section(lines, heading, after_heading):
    s, e = _find_section(lines, heading)
    s2, e2 = _find_section(lines, after_heading)
    if s2 <= s < e2 or s <= s2 < e:
        raise PlanError('move_section: 源章节与目标章节重叠')
    block = lines[s:e]
    rest = lines[:s] + lines[e:]
    insert_at = e2 - len(block) if s2 > s else e2
    return rest[:insert_at] + block + rest[insert_at:]


def _collapse_blanks(lines):
    out = []
    blank = 0
    for ln in lines:
        if ln.strip():
            blank = 0
            out.append(ln)
        else:
            blank += 1
            if blank <= 1:
                out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


# ---------------- 著者-年辅助 ----------------

def _ay_assign_suffixes(entries):
    """同作者同年条目按题名排序赋 a/b 后缀；单条无后缀。就地写 new_suffix。"""
    groups = {}
    for e in entries:
        groups.setdefault((e['authors_sort'], e['year']), []).append(e)
    for key in sorted(groups):
        es = sorted(groups[key], key=lambda e: e['title_sort'])
        for i, e in enumerate(es):
            e['new_suffix'] = chr(ord('a') + i) if len(es) > 1 else ''
    return entries


# ---------------- 核心：compute_plan ----------------

def compute_plan(manuscript_text, references_text, ops, style='numeric-bracket'):
    """确定性重算。返回 label_map dict；出错抛 PlanError。"""
    entries, unparsed = parse_references_text(references_text)
    label_set = {e['label'] for e in entries}
    occ0, _ = scan_manuscript_text(manuscript_text)
    sid_of = build_labels(occ0, entries)['labels']

    lines = manuscript_text.split('\n')

    deletes, inserts, structural = [], [], []
    merge_map = {}
    notes = []
    for op in ops:
        kind = op.get('op')
        if kind == 'delete_marker':
            ro = int(op['reading_order'])
            match = [o for o in occ0 if o['reading_order'] == ro]
            if not match:
                raise PlanError('delete_marker: reading_order=%d 不存在（共 %d 个标记）'
                                % (ro, len(occ0)))
            deletes.append(match[0])
        elif kind == 'insert_marker':
            if 'line' not in op or not op.get('labels'):
                raise PlanError('insert_marker: 需要 line 与 labels')
            if 'col' not in op and 'after_text' not in op:
                raise PlanError('insert_marker: 需要 col 或 after_text')
            inserts.append(op)
        elif kind == 'merge_entries':
            keep, drop = str(op['keep']), str(op['drop'])
            for x in (keep, drop):
                if x not in label_set:
                    raise PlanError('merge_entries: 条目 [%s] 不在文献列表中' % x)
            if keep == drop:
                raise PlanError('merge_entries: keep 与 drop 相同')
            merge_map[drop] = keep
            notes.append('条目 [%s] 合并入 [%s]，正文引用随之改指' % (drop, keep))
        elif kind in ('merge_paragraphs', 'move_section'):
            structural.append(op)
        else:
            raise PlanError('未知操作类型: %r' % kind)

    # ---- 阶段一：标记级编辑（全部基于原始坐标；行内从右到左施加，避免坐标漂移）----
    edits_by_line = {}
    deleted_info = []
    del_lines = set()
    for occ in deletes:
        edits_by_line.setdefault(occ['line'], []).append(
            (occ['col'], occ['col'] + len(occ['raw']), '', occ['raw']))
        del_lines.add(occ['line'])
        deleted_info.append({'reading_order': occ['reading_order'], 'raw': occ['raw'],
                             'region': occ['region'], 'line': occ['line']})
    for ins in inserts:
        ln = int(ins['line'])
        if not (1 <= ln <= len(lines)):
            raise PlanError('insert_marker: line=%d 越界（共 %d 行）' % (ln, len(lines)))
        if 'after_text' in ins:
            at = str(ins['after_text'])
            pos = lines[ln - 1].find(at)
            if pos < 0:
                raise PlanError('insert_marker: 第 %d 行未找到 after_text=%r' % (ln, at))
            col = pos + len(at)
        else:
            col = int(ins['col'])
            if not (0 <= col <= len(lines[ln - 1])):
                raise PlanError('insert_marker: 第 %d 行 col=%d 越界' % (ln, col))
        token = '⟦' + ','.join(str(x) for x in ins['labels']) + '⟧'
        edits_by_line.setdefault(ln, []).append((col, col, token, None))
    for ln in sorted(edits_by_line):
        text = lines[ln - 1]
        for (c1, c2, repl, expected) in sorted(edits_by_line[ln],
                                               key=lambda e: (e[0], e[1]), reverse=True):
            if c1 > len(text) or c2 > len(text):
                raise PlanError('第 %d 行坐标越界（行长 %d，请求 %d-%d）' % (ln, len(text), c1, c2))
            if expected is not None and text[c1:c2] != expected:
                raise PlanError('第 %d 行第 %d 列期望 %r 实际 %r；请先重跑 cite_scan'
                                % (ln, c1, expected, text[c1:c2]))
            if repl and c1 == c2 and c1 > 0 and not text[c1 - 1].isspace():
                repl = ' ' + repl
            text = text[:c1] + repl + text[c2:]
        if ln in del_lines:
            text = _tidy_after_delete(text)
        lines[ln - 1] = text

    # ---- 阶段二：结构级编辑 ----
    for op in structural:
        if op['op'] == 'merge_paragraphs':
            lines = _op_merge_paragraphs(lines, int(op['para_a']), int(op['para_b']))
            notes.append('合并段落 %d 与 %d' % (int(op['para_a']), int(op['para_b'])))
        else:
            lines = _op_move_section(lines, op['heading'], op['after_heading'])
            notes.append('章节 %r 移动到 %r 之后' % (op['heading'], op['after_heading']))
    lines = _collapse_blanks(lines)
    working = '\n'.join(lines)

    # ---- 阶段三：对编辑后文本重扫（含占位符），得到最终真实阅读序 ----
    occs, _ = scan_manuscript_text(working, include_placeholders=True)

    # ---- 阶段四：合并改指 + 悬空检查 ----
    dangling = []
    for occ in occs:
        resolved = []
        for r in occ['refs']:
            r2 = merge_map.get(r, r)
            if r2 not in label_set:
                dangling.append({'reading_order': occ['reading_order'], 'label': r,
                                 'line': occ['line'], 'col': occ['col']})
            resolved.append(r2)
        occ['resolved'] = resolved
    if dangling:
        raise PlanError('存在未处理的悬空标记（原标签不在文献列表中），'
                        '请先用 delete_marker 显式删除: '
                        + json.dumps(dangling, ensure_ascii=False))

    # ---- 阶段五：赋号 + 渲染标记 ----
    if style in ('numeric-bracket', 'numeric-superscript'):
        new_of = {}
        order = []
        for occ in occs:
            for r in occ['resolved']:
                if r not in new_of:
                    new_of[r] = str(len(new_of) + 1)
                    order.append(r)
        for occ in occs:
            nums = [int(new_of[r]) for r in occ['resolved']]
            body = render_range_body(nums)
            occ['new_raw'] = ('[%s]' % body) if style == 'numeric-bracket' else ('^[%s]^' % body)
        reference_order = order
    elif style == 'author-year':
        ay_entries = [e for e in entries if e['kind'] == 'author-year']
        _ay_assign_suffixes(ay_entries)
        key_of = {e['label']: e for e in ay_entries}
        new_of = {}
        for e in ay_entries:
            new_of[e['label']] = '%s %s%s' % (e['surname'], e['year'], e['new_suffix'])
        for occ in occs:
            r = occ['resolved'][0]
            e = key_of[r]
            occ['new_raw'] = re.sub(re.escape(e['year']) + r'[a-z]?(?=[)）])',
                                    e['year'] + e['new_suffix'], occ['raw'], count=1)
        order = [e['label'] for e in sorted(
            ay_entries, key=lambda e: (e['authors_sort'], e['year'], e['title_sort']))
            if e['label'] not in merge_map]
        reference_order = order
    else:
        raise PlanError('未知样式: %r' % style)

    # ---- 阶段六：替换标记文本（编辑后坐标，行内从右到左）----
    repl_by_line = {}
    for occ in occs:
        repl_by_line.setdefault(occ['line'], []).append(
            (occ['col'], occ['col'] + len(occ['raw']), occ['new_raw'], occ['raw']))
    for ln in sorted(repl_by_line):
        text = lines[ln - 1]
        for (c1, c2, repl, expected) in sorted(repl_by_line[ln],
                                               key=lambda e: (e[0], e[1]), reverse=True):
            if text[c1:c2] != expected:
                raise PlanError('内部一致性错误: 第 %d 行第 %d 列期望 %r 实际 %r'
                                % (ln, c1, expected, text[c1:c2]))
            text = text[:c1] + repl + text[c2:]
        lines[ln - 1] = text
    final_manuscript = '\n'.join(lines) + '\n'

    # ---- 阶段七：重排/渲染文末文献列表 ----
    by_label = {}
    for e in entries:
        by_label.setdefault(e['label'], e)
    ref_lines = []
    if style in ('numeric-bracket', 'numeric-superscript'):
        for orig in reference_order:
            e = by_label[orig]
            merged_src = sorted([d for d, k in merge_map.items() if k == orig],
                                key=lambda x: (len(x), x))
            note = ''
            if merged_src:
                note = '（合并原条目 %s）' % ', '.join('[%s]' % d for d in merged_src)
            ref_lines.append('[%s] %s%s' % (new_of[orig], e['text'], note))
        uncited = []
        for e in entries:
            lab = e['label']
            if lab in new_of or lab in merge_map or lab == '*':
                if lab == '*':
                    t = e['text'] if RETAIN_TAG in e['text'] else e['text'] + RETAIN_TAG
                    ref_lines.append('[*] %s' % t)
                continue
            uncited.append(lab)
            t = e['text'] if RETAIN_TAG in e['text'] else e['text'] + RETAIN_TAG
            ref_lines.append('[*] %s' % t)
    else:  # author-year
        key_of = {e['label']: e for e in entries if e['kind'] == 'author-year'}
        cited_set = set()
        for occ in occs:
            cited_set.update(occ['resolved'])
        uncited = []
        for lab in reference_order:
            e = key_of[lab]
            merged_src = sorted([d for d, k in merge_map.items() if k == lab])
            note = ''
            if merged_src:
                note = '（合并原条目 %s）' % ', '.join(merged_src)
            line = '%s (%s%s). %s' % (e['authors'], e['year'], e['new_suffix'], e['text'])
            if lab not in cited_set:
                uncited.append(lab)
                if RETAIN_TAG not in line:
                    line += RETAIN_TAG
            ref_lines.append(line + note)

    edited_references_text = '\n'.join(ref_lines) + '\n'

    # ---- 汇总映射 ----
    mappings = []
    for orig, sid in sorted(sid_of.items(), key=lambda kv: kv[1]):
        if orig in merge_map:
            mappings.append({'sid': sid, 'original_label': orig,
                             'new_label': new_of.get(merge_map[orig]),
                             'status': 'merged_away', 'merged_into': merge_map[orig]})
        elif orig in new_of:
            status = 'uncited_retained' if orig in uncited else 'cited'
            mappings.append({'sid': sid, 'original_label': orig,
                             'new_label': new_of[orig], 'status': status})
        else:
            mappings.append({'sid': sid, 'original_label': orig,
                             'new_label': None, 'status': 'uncited_retained'})

    return {
        'format_version': FORMAT_VERSION,
        'style': style,
        'ops': ops,
        'mappings': mappings,
        'reference_order': [sid_of[o] for o in reference_order if o in sid_of],
        'dangling_removed': deleted_info,
        'uncited_retained': uncited,
        'edited_manuscript_text': final_manuscript,
        'edited_references_text': edited_references_text,
        'notes': notes,
    }


# ---------------- CLI ----------------

def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _auto_style(mtext, rtext):
    occs, _ = scan_manuscript_text(mtext)
    entries, _ = parse_references_text(rtext)
    if any(e['kind'] == 'author-year' for e in entries) and not any(
            o['style'].startswith('numeric') for o in occs):
        return 'author-year'
    return 'numeric-bracket'


def cmd_plan(args):
    try:
        mtext = _read(args.manuscript)
        rtext = _read(args.references)
        ops = json.loads(_read(args.ops))['ops']
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print('renumber plan: 读取输入失败: %s' % e, file=sys.stderr)
        return 2
    style = args.style or _auto_style(mtext, rtext)

    if args.occurrences:
        try:
            provided = [json.loads(x) for x in _read(args.occurrences).splitlines() if x.strip()]
        except (OSError, json.JSONDecodeError) as e:
            print('renumber plan: occurrences 读取失败: %s' % e, file=sys.stderr)
            return 2
        fresh, _ = scan_manuscript_text(mtext)
        if provided != fresh:
            print('renumber plan: 提供的 occurrences 与稿件重扫不一致，请先重跑 cite_scan',
                  file=sys.stderr)
            return 2

    try:
        lm = compute_plan(mtext, rtext, ops, style)
    except PlanError as e:
        print('renumber plan: %s' % e, file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, 'label_map.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(lm, f, ensure_ascii=False, indent=2)
        f.write('\n')
    summary = {
        'style': style,
        'mappings': [{'original': m['original_label'], 'new': m['new_label'],
                      'status': m['status']} for m in lm['mappings']],
        'uncited_retained': lm['uncited_retained'],
        'dangling_removed': lm['dangling_removed'],
        'out': out_path,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_apply(args):
    try:
        mtext = _read(args.manuscript)
        rtext = _read(args.references)
        lm = json.loads(_read(args.label_map))
    except (OSError, json.JSONDecodeError) as e:
        print('renumber apply: 读取输入失败: %s' % e, file=sys.stderr)
        return 2
    style = args.style or lm.get('style')
    if lm.get('style') and style != lm['style']:
        print('renumber apply: --style=%s 与 label_map.style=%s 不一致' % (style, lm['style']),
              file=sys.stderr)
        return 1

    # 复算校验：用相同输入 + label_map 中的 ops 完整重算，逐字段比对
    try:
        repro = compute_plan(mtext, rtext, lm.get('ops', []), style)
    except PlanError as e:
        print('renumber apply: 复算失败: %s' % e, file=sys.stderr)
        return 1
    diff = [k for k in COMPARE_KEYS
            if json.dumps(repro.get(k), sort_keys=True, ensure_ascii=False)
            != json.dumps(lm.get(k), sort_keys=True, ensure_ascii=False)]
    if diff:
        print('renumber apply: label_map 与输入复算不一致（字段: %s）；'
              'label_map 可能已过期或被篡改，请重跑 plan' % ', '.join(diff), file=sys.stderr)
        return 1
    if '⟦' in lm['edited_manuscript_text'] or '⟦' in lm['edited_references_text']:
        print('renumber apply: 渲染结果中残留占位符，拒绝落盘', file=sys.stderr)
        return 1

    # 全部校验通过：原子写出三个产物（临时文件 + os.replace）
    os.makedirs(args.out, exist_ok=True)
    payloads = {
        'edited_manuscript.txt': lm['edited_manuscript_text'],
        'edited_references.txt': lm['edited_references_text'],
        'label_map.json': json.dumps(lm, ensure_ascii=False, indent=2) + '\n',
    }
    for name, content in payloads.items():
        tmp = os.path.join(args.out, '.tmp-%s' % name)
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, os.path.join(args.out, name))
    print(json.dumps({'applied': True, 'out': sorted(
        os.path.join(args.out, n) for n in payloads)}, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='编号重算与同步施加（确定性，仅标准库）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('plan', help='按 ops 重算 original->new 映射并渲染编辑后文本')
    p.add_argument('--manuscript', required=True)
    p.add_argument('--references', required=True)
    p.add_argument('--ops', required=True, help='ops.json（{"ops":[...]}）')
    p.add_argument('--occurrences', default=None, help='可选：cite_scan 产物，用于一致性校验')
    p.add_argument('--style', default=None,
                   choices=['numeric-bracket', 'numeric-superscript', 'author-year'])
    p.add_argument('--out', required=True)
    p.set_defaults(func=cmd_plan)

    a = sub.add_parser('apply', help='复算校验 label_map，全部通过才原子落盘')
    a.add_argument('--manuscript', required=True)
    a.add_argument('--references', required=True)
    a.add_argument('--label_map', required=True)
    a.add_argument('--style', default=None,
                   choices=['numeric-bracket', 'numeric-superscript', 'author-year'])
    a.add_argument('--out', required=True)
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
