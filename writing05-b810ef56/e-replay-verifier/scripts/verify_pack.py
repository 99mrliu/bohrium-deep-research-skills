#!/usr/bin/env python3
"""独立复核器：第三方一条命令重验交付包的全部可核验承诺。

只依赖标准库，不调用任何模型。复核视角是"不信任交付过程"：
manifest 说什么就重算什么——文件哈希重算、摘录逐字重查、数字
重新命中、文献条目字段完整性、result.json 契约键与 case_id。

用法：
    python3 verify_pack.py --output-dir OUTPUT_DIR \
        --sources SOURCES_DIR --manifest MANIFEST_JSON \
        --report REPORT_MD

SOURCES_DIR   原始来源的提取文本目录（<source>.txt），由复核方
              自己从原始材料提取，不用交付方提供的文本。

检查类：HASH / QUOTE / NUMBER / REF / CONTRACT。
退出码：0 = 全部 PASS；1 = 存在 FAIL；2 = 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import sys
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFKC', text)
    return ' '.join(text.split())


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--sources', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    with open(args.manifest, encoding='utf-8') as fh:
        manifest = json.load(fh)

    rows = ['| 类别 | 条目 | 结果 | 说明 |', '|---|---|---|---|']
    fails = []

    def check(category, item, cond, detail):
        rows.append('| %s | %s | %s | %s |' % (
            category, item, 'PASS' if cond else 'FAIL',
            str(detail).replace('|', '/')[:200]))
        if not cond:
            fails.append('%s:%s' % (category, item))

    source_cache = {}

    def source_text(stem):
        if stem not in source_cache:
            path = os.path.join(args.sources, stem + '.txt')
            if os.path.exists(path):
                with open(path, encoding='utf-8',
                          errors='replace') as fh:
                    source_cache[stem] = fh.read()
            else:
                source_cache[stem] = None
        return source_cache[stem]

    for art in manifest.get('artifacts', []):
        path = os.path.join(args.output_dir, art['path'])
        if not os.path.exists(path):
            check('HASH', art['path'], False, '文件缺失')
            continue
        digest = sha256_of(path)
        check('HASH', art['path'], digest == art['sha256'],
              '哈希一致' if digest == art['sha256']
              else '哈希不符（文件在打包后被改动）')

    for q in manifest.get('quotes', []):
        text = source_text(q.get('source', ''))
        if text is None:
            check('QUOTE', q.get('id'), False,
                  '来源文本缺失: %s' % q.get('source'))
            continue
        hit = normalize(q.get('quote', '')) in normalize(
            text.replace('\f', ' '))
        check('QUOTE', q.get('id'), hit,
              '逐字命中' if hit else '未命中（摘录与原文不符）')

    for n in manifest.get('numbers', []):
        text = source_text(n.get('source', ''))
        if text is None:
            check('NUMBER', n.get('id'), False,
                  '来源文本缺失: %s' % n.get('source'))
            continue
        hit = str(n.get('value', '')) in normalize(text)
        check('NUMBER', n.get('id'), hit,
              '数字 %s 命中' % n.get('value') if hit
              else '数字 %s 未在来源中出现' % n.get('value'))

    for r in manifest.get('refs', []):
        ok = bool(str(r.get('title', '')).strip()) and (
            str(r.get('authors', '')).strip() or r.get('year'))
        check('REF', '[%s]' % r.get('n'), ok,
              '著录字段齐备' if ok else '缺 title 或 authors/year')

    result_path = os.path.join(args.output_dir, 'result.json')
    if not os.path.exists(result_path):
        check('CONTRACT', 'result.json', False, '缺失')
    else:
        try:
            with open(result_path, encoding='utf-8') as fh:
                result = json.load(fh)
            check('CONTRACT', 'result.json 可解析', True, 'JSON 合法')
            if manifest.get('case_id') is not None:
                check('CONTRACT', 'case_id',
                      result.get('case_id') == manifest['case_id'],
                      '%r' % result.get('case_id'))
            for key in manifest.get('contract_keys', []):
                check('CONTRACT', '键: %s' % key, key in result,
                      '存在' if key in result else '缺失')
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            check('CONTRACT', 'result.json 可解析', False, str(exc))

    passed = sum(1 for r in rows[2:] if '| PASS |' in r)
    lines = ['# 独立复核报告', '',
             '复核口径：不信任交付过程，manifest 的全部承诺逐项重算。',
             '',
             '通过 %d 项，失败 %d 项。' % (passed, len(fails)), ''] + rows
    lines += ['', '结论：%s。' % ('全部承诺复核通过'
              if not fails else '未通过项：' + '、'.join(fails)), '']
    with open(args.report, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    print(json.dumps({'passed': passed, 'failed': len(fails),
                      'fails': fails}, ensure_ascii=False))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
