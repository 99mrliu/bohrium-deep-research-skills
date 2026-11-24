#!/usr/bin/env python3
"""outline_extract.py -- 把稿件抽成带块 ID 的段落库与大纲, 供编辑操作寻址。

块 ID 形式: B001, B002, ...; 标题块记 level。编辑操作只引用块 ID,
apply_editops.py 据此重排/合并/拆分, 产出修订稿骨架。

用法:
    python3 outline_extract.py MANUSCRIPT_MD OUT_DIR
产物: blocks.jsonl ({"id","kind","level","text"}) + outline.json
"""
import json
import os
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$|^([一二三四五六七八九十]+、\S.*)$|^(\d+(?:\.\d+)*)\s+(\S.{0,60})$')


def extract(ms_path, out_dir):
    with open(ms_path, encoding='utf-8') as f:
        text = f.read()
    os.makedirs(out_dir, exist_ok=True)

    blocks = []
    pos = 0
    for chunk in re.split(r'(\n[ \t]*\n)', text):
        if re.fullmatch(r'\n[ \t]*\n', chunk or ''):
            pos += len(chunk)
            continue
        t = (chunk or '').strip('\n')
        if t.strip():
            m = HEADING_RE.match(t.strip())
            kind, level = 'para', None
            if m:
                kind = 'heading'
                level = len(m.group(1)) if m.group(1) else 1
            blocks.append({'id': 'B%03d' % (len(blocks) + 1), 'kind': kind,
                           'level': level, 'char_start': pos + (len(chunk) - len(chunk.lstrip('\n'))),
                           'text': t})
        pos += len(chunk or '')

    with open(os.path.join(out_dir, 'blocks.jsonl'), 'w', encoding='utf-8') as f:
        for b in blocks:
            f.write(json.dumps(b, ensure_ascii=False) + '\n')

    outline = [{'id': b['id'], 'level': b['level'],
                'title': re.sub(r'^#+\s*', '', b['text'])[:60]}
               for b in blocks if b['kind'] == 'heading']
    meta = {'manuscript': os.path.abspath(ms_path), 'blocks': len(blocks),
            'headings': len(outline), 'outline': outline}
    with open(os.path.join(out_dir, 'outline.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps({'blocks': len(blocks), 'headings': len(outline)}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: outline_extract.py MANUSCRIPT_MD OUT_DIR')
    extract(*sys.argv[1:3])
