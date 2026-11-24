#!/usr/bin/env python3
"""材料取证与来源登记（material forensics & source registry）。

只依赖 Python 标准库；PDF 文本层提取优先调用系统 pdftotext（poppler），
不可用时对该文件降级为 UNUSABLE 并如实记录，绝不假装已读取。

用法：
    python3 material_forensics.py INPUT_DIR WORK_DIR [--case CASE_JSON]

产物（全部写入 WORK_DIR）：
    sources_registry.json   每个输入文件一条登记记录（sha256/大小/处置）
    text/<stem>.txt         提取出的全文（\f 分页）
    text/<stem>.pages.json  页码 -> 字符偏移索引（供后续定位引用）
    material_report.md      人读取证报告：清单、处置、可用性结论

退出码：0 = 至少一个可用来源；1 = 零可用来源（后续写作不得进行）；
        2 = 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

TEXT_EXTS = {'.txt', '.md', '.markdown', '.csv', '.tsv', '.json',
             '.xml', '.html', '.htm', '.tex', '.bib'}
CASE_BASENAMES = {'case.json', 'task.md'}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def garble_ratio(text):
    """替换字符/异常控制字符占比，用于识别乱码或失败解码。"""
    if not text:
        return 1.0
    bad = sum(1 for ch in text
              if ch == '�' or (unicodedata.category(ch) == 'Cc'
                               and ch not in '\t\n\r\f'))
    return bad / len(text)


def extract_pdf(path, out_txt):
    """调用 pdftotext 提取；返回 (status, reason, pages, chars)。"""
    exe = shutil.which('pdftotext')
    if not exe:
        return 'UNUSABLE', 'pdftotext 不可用，无法读取 PDF 文本层', 0, 0
    proc = subprocess.run([exe, '-layout', path, out_txt],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not os.path.exists(out_txt):
        return 'UNUSABLE', 'pdftotext 失败: ' + (proc.stderr.strip()[:200]
                                                 or '未知错误'), 0, 0
    with open(out_txt, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    pages = text.count('\f') + (1 if text.strip() else 0)
    chars = len(text.strip())
    if chars < 100:
        return 'DEGRADED', ('文本层近乎为空（%d 字符），疑似扫描件；'
                            '需要 OCR 或人工录入' % chars), pages, chars
    ratio = garble_ratio(text)
    if ratio > 0.01:
        return 'DEGRADED', ('乱码/控制字符占比 %.2f%%，提取质量存疑'
                            % (ratio * 100)), pages, chars
    return 'OK', '', pages, chars


def write_page_index(text, out_json):
    """生成 页码 -> [起始偏移, 结束偏移) 索引。"""
    pages = text.split('\f')
    index, pos = [], 0
    for i, page in enumerate(pages, 1):
        index.append({'page': i, 'start': pos, 'end': pos + len(page)})
        pos += len(page) + 1
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)


def harvest_case_declarations(case_path):
    """从 case.json 递归收集声明过的文件名/URL/标题线索（尽力而为）。"""
    declared = []
    if not case_path or not os.path.exists(case_path):
        return declared
    try:
        with open(case_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception:
        return declared

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if isinstance(val, str) and (
                        key.lower() in ('file', 'filename', 'path', 'url',
                                        'pdf', 'source', 'title', 'name')
                        or re.search(r'\.\w{2,4}$', val)):
                    declared.append({'key': key, 'value': val[:300]})
                else:
                    walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(data)
    return declared


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input_dir')
    ap.add_argument('work_dir')
    ap.add_argument('--case', default=None, help='case.json 路径（可选）')
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print('输入目录不存在: %s' % args.input_dir, file=sys.stderr)
        return 2
    text_dir = os.path.join(args.work_dir, 'text')
    os.makedirs(text_dir, exist_ok=True)

    registry = []
    for root, dirs, files in os.walk(args.input_dir):
        dirs.sort()
        for name in sorted(files):
            if name.startswith('.'):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, args.input_dir)
            ext = os.path.splitext(name)[1].lower()
            rec = {'file': rel, 'bytes': os.path.getsize(path),
                   'sha256': sha256_of(path), 'format': ext.lstrip('.'),
                   'role': ('case-metadata'
                            if name in CASE_BASENAMES else 'material'),
                   'status': 'OK', 'reason': '',
                   'text_path': None, 'pages': 0, 'chars': 0}
            if rec['role'] == 'case-metadata':
                registry.append(rec)
                continue
            stem = re.sub(r'[^\w.-]+', '_', os.path.splitext(rel)[0])
            if ext == '.pdf':
                out_txt = os.path.join(text_dir, stem + '.txt')
                status, reason, pages, chars = extract_pdf(path, out_txt)
                rec.update(status=status, reason=reason, pages=pages,
                           chars=chars)
                if status != 'UNUSABLE' and chars:
                    rec['text_path'] = os.path.relpath(out_txt,
                                                       args.work_dir)
                    with open(out_txt, encoding='utf-8',
                              errors='replace') as fh:
                        write_page_index(fh.read(), os.path.join(
                            text_dir, stem + '.pages.json'))
            elif ext in TEXT_EXTS:
                out_txt = os.path.join(text_dir, stem + '.txt')
                with open(path, encoding='utf-8',
                          errors='replace') as fh:
                    text = fh.read()
                with open(out_txt, 'w', encoding='utf-8') as fh:
                    fh.write(text)
                rec.update(text_path=os.path.relpath(out_txt,
                                                     args.work_dir),
                           chars=len(text.strip()), pages=1)
                write_page_index(text, os.path.join(text_dir,
                                                    stem + '.pages.json'))
                if garble_ratio(text) > 0.01:
                    rec.update(status='DEGRADED', reason='文本含异常字符，'
                                                         '疑似编码损坏')
            else:
                rec.update(status='UNUSABLE',
                           reason='无可用提取器（格式 %s）' % ext)
            registry.append(rec)

    declared = harvest_case_declarations(
        args.case or os.path.join(args.input_dir, 'case.json'))
    materials = [r for r in registry if r['role'] == 'material']
    usable = [r for r in materials if r['status'] == 'OK']
    degraded = [r for r in materials if r['status'] == 'DEGRADED']

    summary = {'input_dir': os.path.abspath(args.input_dir),
               'files_total': len(registry),
               'materials_total': len(materials),
               'usable': len(usable), 'degraded': len(degraded),
               'unusable': len(materials) - len(usable) - len(degraded),
               'declared_hints': declared}
    with open(os.path.join(args.work_dir, 'sources_registry.json'), 'w',
              encoding='utf-8') as fh:
        json.dump({'summary': summary, 'records': registry}, fh,
                  ensure_ascii=False, indent=1)

    lines = ['# 材料取证报告', '',
             '| 文件 | 大小(B) | 格式 | 处置 | 页数 | 字符数 | 说明 |',
             '|---|---|---|---|---|---|---|']
    for r in registry:
        lines.append('| %s | %d | %s | %s | %s | %s | %s |' % (
            r['file'], r['bytes'], r['format'], r['status'],
            r['pages'] or '-', r['chars'] or '-',
            r['reason'].replace('|', '/')))
    lines += ['', '## 结论', '',
              '- 可用来源（OK）：%d；降级（DEGRADED）：%d；'
              '不可用（UNUSABLE）：%d。'
              % (len(usable), len(degraded),
                 len(materials) - len(usable) - len(degraded)),
              '- DEGRADED 来源只能支撑带〔材料质量受限〕标注的表述；'
              'UNUSABLE 来源不得支撑任何事实句。',
              '- case.json 中声明的线索见 sources_registry.json 的 '
              'declared_hints；声明而缺失、存在而未声明都应在 '
              'result.json 的 limits 中说明。']
    with open(os.path.join(args.work_dir, 'material_report.md'), 'w',
              encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')

    print(json.dumps(summary, ensure_ascii=False))
    return 0 if usable else 1


if __name__ == '__main__':
    sys.exit(main())
