#!/usr/bin/env python3
"""anchor_extract.py -- 上游证据锚定：把 /input 下的稿件材料抽成带稳定锚点的段落库。

用法:
    python3 anchor_extract.py INPUT_DIR OUT_DIR

产物 (OUT_DIR):
    anchor_map.jsonl   每行 {"anchor","source","para_index","char_start","char_end","text"}
    manifest.json      抽取清单与 QC: 每个来源文件的段落数、可疑乱码率、截断迹象、不可读文件

设计原则: 只抽取真实存在的文本, 绝不猜测内容; 不可读的文件记入 manifest.unreadable,
由调用方在 result.json 的 uncertainty 中如实标注。
"""
import json
import os
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

TEXT_EXT = {'.md', '.txt', '.tex', '.markdown'}
SKIP_NAMES = {'case.json', 'task.md'}


def _garble_ratio(text):
    """估计乱码率: 替换字符/控制字符/孤立高位字节占非空白字符的比例。"""
    if not text.strip():
        return 0.0
    bad = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        o = ord(ch)
        if ch == '�' or (o < 32 and ch not in '\t') or (0xF0000 <= o <= 0xFFFFD):
            bad += 1
    return bad / max(total, 1)


def _split_paragraphs(text):
    """按空行切段; 保留段内换行。返回 [(char_start, para_text)]。"""
    paras = []
    pos = 0
    for chunk in re.split(r'(\n[ \t]*\n)', text):
        if re.fullmatch(r'\n[ \t]*\n', chunk or ''):
            pos += len(chunk)
            continue
        if chunk and chunk.strip():
            lead = len(chunk) - len(chunk.lstrip('\n'))
            t = chunk.strip('\n')
            start = pos + lead
            paras.append((start, t))
        pos += len(chunk or '')
    return paras


def _read_pdf(path):
    try:
        p = subprocess.run(['pdftotext', '-layout', path, '-'],
                           capture_output=True, timeout=120)
        if p.returncode == 0 and p.stdout:
            return p.stdout.decode('utf-8', errors='replace'), None
        return None, 'pdftotext rc=%s: %s' % (p.returncode, p.stderr.decode('utf-8', 'replace')[:200])
    except FileNotFoundError:
        return None, 'pdftotext not installed'
    except subprocess.TimeoutExpired:
        return None, 'pdftotext timeout'


def _read_docx(path):
    """容错解包 docx (zip+xml); 失败则返回原因。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml')
        root = ET.fromstring(xml)
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        paras = []
        for p in root.iter(ns + 'p'):
            t = ''.join(node.text or '' for node in p.iter(ns + 't'))
            if t.strip():
                paras.append(t)
        return '\n\n'.join(paras), None
    except Exception as e:  # noqa: BLE001 - 任何解包失败都如实上报
        return None, 'docx unpack failed: %s' % type(e).__name__


def extract(input_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    sources = []
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path) or name in SKIP_NAMES:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in TEXT_EXT or ext in {'.pdf', '.docx'}:
            sources.append((name, path, ext))

    manifest = {'input_dir': os.path.abspath(input_dir), 'sources': [],
                'unreadable': [], 'total_paragraphs': 0}
    records = []
    for sidx, (name, path, ext) in enumerate(sources, start=1):
        src_id = 'S%d' % sidx
        text, err = None, None
        if ext in TEXT_EXT:
            try:
                with open(path, encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError as e:
                err = 'utf-8 decode failed: %s' % e
        elif ext == '.pdf':
            text, err = _read_pdf(path)
        elif ext == '.docx':
            text, err = _read_docx(path)
        if err or text is None:
            manifest['unreadable'].append({'source': src_id, 'file': name, 'reason': err})
            continue
        paras = _split_paragraphs(text)
        gr = _garble_ratio(text)
        tail = text[-200:] if text else ''
        trunc_suspect = bool(text) and not re.search(r'[.。!？?）)\]】]$|references|参考文献',
                                                     tail.strip(), re.I) and len(paras) > 3
        entry = {'source': src_id, 'file': name, 'ext': ext,
                 'bytes': os.path.getsize(path), 'paragraphs': len(paras),
                 'garble_ratio': round(gr, 4),
                 'garble_suspect': gr > 0.01,
                 'truncation_suspect': trunc_suspect}
        manifest['sources'].append(entry)
        manifest['total_paragraphs'] += len(paras)
        for pidx, (cstart, ptext) in enumerate(paras, start=1):
            records.append({'anchor': '%s-P%03d' % (src_id, pidx),
                            'source': src_id, 'file': name,
                            'para_index': pidx,
                            'char_start': cstart,
                            'char_end': cstart + len(ptext),
                            'text': ptext})

    with open(os.path.join(out_dir, 'anchor_map.jsonl'), 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(json.dumps({'sources': len(manifest['sources']),
                      'unreadable': len(manifest['unreadable']),
                      'paragraphs': manifest['total_paragraphs']}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: anchor_extract.py INPUT_DIR OUT_DIR')
    extract(sys.argv[1], sys.argv[2])
