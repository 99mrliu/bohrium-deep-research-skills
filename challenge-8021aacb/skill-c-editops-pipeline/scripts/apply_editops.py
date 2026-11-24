#!/usr/bin/env python3
"""apply_editops.py -- 编辑操作模拟应用器: 让作者在动笔前看到改后骨架。

按给定顺序应用 ops 于块库, 产出:
  revised_skeleton.md  修订后的稿件骨架 (标题 + 段落, 含修订标记)
  change_log.json      每条 op 的应用结果 (applied / skipped + 原因)

模拟器是保守的: 无法安全应用的 op 记 skipped, 绝不静默改错文本。

用法:
    python3 apply_editops.py BLOCKS_JSONL OPS_JSON OUT_DIR
"""
import json
import os
import sys


def load_blocks(path):
    blocks = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                blocks.append(json.loads(line))
    return blocks


def _find(blocks, bid):
    for i, b in enumerate(blocks):
        if b['id'] == bid:
            return i
    return None


def apply(blocks_path, ops_path, out_dir):
    blocks = load_blocks(blocks_path)
    with open(ops_path, encoding='utf-8') as f:
        doc = json.load(f)
    ops = doc.get('ops', doc if isinstance(doc, list) else [])
    os.makedirs(out_dir, exist_ok=True)

    log = []
    for op in ops:
        oid = op.get('id', '?')
        kind = op.get('op')
        entry = {'id': oid, 'op': kind, 'status': 'applied'}
        try:
            if kind == 'move':
                i = _find(blocks, op['target'])
                j = _find(blocks, op['after'])
                if i is None or j is None:
                    raise ValueError('block not found')
                b = blocks.pop(i)
                j = _find(blocks, op['after'])
                blocks.insert(j + 1, b)
            elif kind == 'merge':
                i = _find(blocks, op['target'])
                j = _find(blocks, op['into'])
                if i is None or j is None:
                    raise ValueError('block not found')
                blocks[j]['text'] = blocks[j]['text'].rstrip() + ' ' + blocks[i]['text'].strip()
                blocks[i]['_deleted'] = True
            elif kind == 'delete_duplicate':
                i = _find(blocks, op['target'])
                j = _find(blocks, op['duplicate_of'])
                if i is None or j is None:
                    raise ValueError('block not found')
                if ' '.join(blocks[i]['text'].split()) != ' '.join(blocks[j]['text'].split()):
                    raise ValueError('target is not verbatim duplicate of duplicate_of; refused')
                blocks[i]['_deleted'] = True
            elif kind == 'narrow':
                i = _find(blocks, op['target'])
                if i is None:
                    raise ValueError('block not found')
                if op['quote'] not in blocks[i]['text']:
                    raise ValueError('quote not verbatim in target')
                blocks[i]['text'] = blocks[i]['text'].replace(op['quote'], op['replacement'], 1)
            elif kind == 'split':
                i = _find(blocks, op['target'])
                if i is None or op['at_quote'] not in blocks[i]['text']:
                    raise ValueError('at_quote not in target')
                head, tail = blocks[i]['text'].split(op['at_quote'], 1)
                blocks[i]['text'] = head.rstrip()
                newb = dict(blocks[i])
                newb['id'] = blocks[i]['id'] + 'b'
                newb['text'] = (op['at_quote'] + tail).strip()
                blocks.insert(i + 1, newb)
            elif kind == 'insert_transition':
                j = _find(blocks, op['before'])
                if j is None:
                    raise ValueError('before block not found')
                blocks.insert(j, {'id': op['id'] + '-T', 'kind': 'inserted',
                                  'level': None, 'text': op['sentence']})
            elif kind == 'add_limitation':
                j = _find(blocks, op['after'])
                if j is None:
                    raise ValueError('after block not found')
                blocks.insert(j + 1, {'id': op['id'] + '-L', 'kind': 'inserted',
                                      'level': None, 'text': op['sentence']})
            elif kind == 'reorder_section':
                # 移动标题块及其后续直到下一同级标题的所有块
                i = _find(blocks, op['target'])
                j = _find(blocks, op['after'])
                if i is None or j is None or blocks[i]['kind'] != 'heading':
                    raise ValueError('target must be an existing heading block')
                lvl = blocks[i]['level'] or 1
                k = i + 1
                while k < len(blocks) and not (
                        blocks[k]['kind'] == 'heading' and (blocks[k]['level'] or 1) <= lvl):
                    k += 1
                section = blocks[i:k]
                del blocks[i:k]
                j = _find(blocks, op['after'])
                blocks[j + 1:j + 1] = section
            else:
                raise ValueError('unknown op ' + str(kind))
        except Exception as e:  # noqa: BLE001 - 失败 op 如实记录
            entry['status'] = 'skipped'
            entry['reason'] = str(e)
        log.append(entry)

    blocks = [b for b in blocks if not b.get('_deleted')]
    lines = []
    for b in blocks:
        prefix = ''
        if b['kind'] == 'heading':
            prefix = '#' * (b['level'] or 1) + ' '
        elif b['kind'] == 'inserted':
            prefix = '> [新增] '
        lines.append(prefix + re_sub_heading(b['text'], b['kind']))
        lines.append('')
    with open(os.path.join(out_dir, 'revised_skeleton.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    n_applied = sum(1 for e in log if e['status'] == 'applied')
    with open(os.path.join(out_dir, 'change_log.json'), 'w', encoding='utf-8') as f:
        json.dump({'total': len(log), 'applied': n_applied,
                   'skipped': len(log) - n_applied, 'log': log}, f,
                  ensure_ascii=False, indent=2)
    print(json.dumps({'ops': len(log), 'applied': n_applied,
                      'skipped': len(log) - n_applied}, ensure_ascii=False))


def re_sub_heading(text, kind):
    if kind == 'heading':
        t = text.lstrip('#').strip()
        return t
    return text


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: apply_editops.py BLOCKS_JSONL OPS_JSON OUT_DIR')
    apply(*sys.argv[1:4])
