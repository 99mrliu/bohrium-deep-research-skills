#!/usr/bin/env python3
"""引文定位器：给定一段原文摘录，在登记过的提取文本中逐字定位并回填页码。

只依赖标准库。规范化规则：NFKC + 折叠连续空白（与取证脚本产出的文本
配合使用；规则集中在 normalize()，便于维护和复核）。

用法：
    python3 locate_quote.py WORK_DIR QUOTE_FILE [--source STEM]

    WORK_DIR     material_forensics.py 的工作目录（含 text/ 子目录）
    QUOTE_FILE   存有待定位摘录的 UTF-8 文本文件
    --source     只在指定 <stem>.txt 中查找（默认全部来源）

输出（stdout，JSON）：每次调用一条结果
    {"quote_sha256": ..., "matches": [{"source": ..., "page": ...,
     "start": ..., "end": ...}], "found": true/false}

退出码：0 = 至少一处命中；1 = 未命中（该摘录不得作为逐字证据使用）。
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFKC', text)
    return ' '.join(text.split())


def load_pages(stem, text_dir):
    path = os.path.join(text_dir, stem + '.pages.json')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def page_of(pages, offset):
    for entry in pages:
        if entry['start'] <= offset < entry['end']:
            return entry['page']
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('work_dir')
    ap.add_argument('quote_file')
    ap.add_argument('--source', default=None)
    args = ap.parse_args()

    text_dir = os.path.join(args.work_dir, 'text')
    if not os.path.isdir(text_dir):
        print('未找到提取文本目录: %s' % text_dir, file=sys.stderr)
        return 2
    with open(args.quote_file, encoding='utf-8') as fh:
        needle = normalize(fh.read())
    digest = hashlib.sha256(needle.encode('utf-8')).hexdigest()

    if args.source:
        candidates = [os.path.join(text_dir, args.source + '.txt')]
    else:
        candidates = sorted(glob.glob(os.path.join(text_dir, '*.txt')))

    matches = []
    for path in candidates:
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding='utf-8', errors='replace') as fh:
            raw = fh.read()
        hay = normalize(raw.replace('\f', ' '))
        start = hay.find(needle)
        if start < 0:
            continue
        # 在含 \f 的原文上近似定位页码：按规范化后偏移比例不可靠，
        # 因此用页索引逐页规范化重查，保证页码真实。
        pages = load_pages(stem, text_dir)
        page = None
        raw_pages = raw.split('\f')
        for i, chunk in enumerate(raw_pages, 1):
            if needle in normalize(chunk):
                page = i
                break
        matches.append({'source': stem, 'page': page,
                        'start': start, 'end': start + len(needle)})
    result = {'quote_sha256': digest, 'matches': matches,
              'found': bool(matches)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if matches else 1


if __name__ == '__main__':
    sys.exit(main())
