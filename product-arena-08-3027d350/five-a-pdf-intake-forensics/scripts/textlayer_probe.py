#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
textlayer_probe.py — 每页文字层判定（bundle A: pdf-intake-forensics）

引擎链（自动降级，缺失时如实记录 engine 与降级原因）:
    pymupdf  ->  pdftotext  ->  标准库计数（复用 pdf_forensics.py 的 Tj/TJ 字节计数）

每页分类:
    text    非空白字符数 >= TEXT_MIN_CHARS 且未判定为乱码
    sparse  NONE_MAX_CHARS < 字符数 < TEXT_MIN_CHARS（零星文字：页眉/水印/偶发 OCR 残渣）
    none    字符数 <= NONE_MAX_CHARS（扫描页，无可用文字层）

乱码检测（metrics 逐页记录）:
    U+FFFD 替换符、(cid:NN) 模式、控制字符、可疑高字节占比；
    garbage_ratio = (fffd + cid_hits + control_chars) / max(chars, 1) > GARBAGE_RATIO_THRESHOLD
    或出现任意 (cid:NN) 命中即判 garbled=true。

用法:
    python3 textlayer_probe.py <file.pdf> [--forensics forensics.json] [-o probe.json]

退出码: 0=成功 2=部分（降级到标准库计数 / 引擎报错但有产出） 3=失败（所有引擎均无产出）
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

EXIT_OK = 0
EXIT_PARTIAL = 2
EXIT_FAIL = 3

# ---- 阈值常量（与 SKILL.md「方法要点」保持一致，改动须同步） ----
NONE_MAX_CHARS = 10            # 非空白字符数 <= 此值判为 none（扫描页）
TEXT_MIN_CHARS = 100           # 非空白字符数 >= 此值判为 text
GARBAGE_RATIO_THRESHOLD = 0.05 # 乱码占比超过此值判 garbled
CID_RE = re.compile(r'\(cid:\d+\)')
SAMPLE_LEN = 80                # 每页文本样例截取长度


def non_ws_chars(text):
    return sum(1 for c in text if not c.isspace())


def garbage_metrics(text):
    chars = non_ws_chars(text)
    fffd = text.count('�')
    cid = len(CID_RE.findall(text))
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t\f')
    high = sum(1 for c in text if not c.isspace() and ord(c) > 126)
    ratio = (fffd + cid + ctrl) / max(chars, 1)
    return {
        'fffd_count': fffd,
        'cid_hits': cid,
        'control_chars': ctrl,
        'high_byte_count': high,
        'high_byte_ratio': round(high / max(chars, 1), 4),
        'garbage_ratio': round(ratio, 4),
        'garbled': bool(chars > 0 and (ratio > GARBAGE_RATIO_THRESHOLD or cid > 0)),
    }


def classify(chars, garbled):
    if chars <= NONE_MAX_CHARS:
        return 'none'
    if chars < TEXT_MIN_CHARS:
        return 'sparse'
    return 'text'


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------

def try_pymupdf(path):
    mod = None
    try:
        import pymupdf as mod  # noqa: N811
    except ImportError:
        try:
            import fitz as mod  # noqa: N811
        except ImportError:
            return None, 'pymupdf_not_installed'
    try:
        doc = mod.open(path)
    except Exception as e:
        return None, 'pymupdf_open_failed: %s: %s' % (type(e).__name__, e)
    texts = []
    try:
        for page in doc:
            texts.append(page.get_text('text'))
    except Exception as e:
        doc.close()
        return None, 'pymupdf_read_failed: %s: %s' % (type(e).__name__, e)
    doc.close()
    return texts, None


def try_pdftotext(path):
    exe = shutil.which('pdftotext')
    if not exe:
        return None, 'pdftotext_not_installed'
    r = subprocess.run([exe, '-enc', 'UTF-8', path, '-'], capture_output=True, timeout=120)
    text = r.stdout.decode('utf-8', errors='replace')
    note = None
    if r.returncode != 0:
        note = 'pdftotext_exit_%d: %s' % (r.returncode, ' / '.join(
            r.stderr.decode('utf-8', errors='replace').splitlines()).strip()[:200])
    pages = text.split('\f')
    if pages and pages[-1].strip() == '':
        pages = pages[:-1]
    if not pages and r.returncode != 0:
        return None, note or 'pdftotext_no_output'
    return (pages, note), None


def try_stdlib_count(path):
    """末档引擎：只有每页 Tj/TJ 字节计数，无真实文本（无法做乱码检测）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import pdf_forensics
    except ImportError as e:
        return None, 'stdlib_count_import_failed: %s' % e
    try:
        report, _code = pdf_forensics.analyze(path)
    except Exception as e:
        return None, 'stdlib_count_failed: %s: %s' % (type(e).__name__, e)
    if report.get('status') == 'failed':
        return None, 'stdlib_count_failed: %s' % report.get('failure_reason')
    counts = [p['text_showing_bytes'] for p in report.get('pages', [])]
    return counts, 'counts_are_bytes_not_unicode_chars'


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def probe(path, forensics_path=None):
    notes = []
    engine_notes = []
    texts = None       # list[str] | None
    counts = None      # list[int] | None（标准库末档）
    engine = None
    degraded = False

    texts, err = try_pymupdf(path)
    if texts is not None and len(texts) == 0:
        err = 'pymupdf_zero_pages: 打开成功但未重建出任何页（典型于截尾/坏 xref）'
        texts = None
    if texts is not None:
        engine = 'pymupdf'
    else:
        engine_notes.append('pymupdf: %s' % err)
        res, err2 = try_pdftotext(path)
        if res is not None and len(res[0]) == 0:
            err2 = 'pdftotext_zero_pages: 无输出（典型于截尾/坏 xref）'
            res = None
        if res is not None:
            texts, note = res
            engine = 'pdftotext'
            if note:
                engine_notes.append(note)
                degraded = True
        else:
            engine_notes.append('pdftotext: %s' % err2)
            counts, note = try_stdlib_count(path)
            if counts is not None:
                engine = 'stdlib_count'
                engine_notes.append('stdlib_count: %s' % note)
                degraded = True
            else:
                engine_notes.append('stdlib_count: %s' % note)

    if engine is None:
        return {
            'tool': 'textlayer_probe.py',
            'pdf_path': os.path.abspath(path),
            'generated_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'status': 'failed',
            'engine': None,
            'engine_notes': engine_notes,
            'failure_reason': 'no_text_engine: pymupdf/pdftotext/标准库三级引擎均无产出',
        }, EXIT_FAIL

    pages = []
    if texts is not None:
        for i, t in enumerate(texts):
            chars = non_ws_chars(t)
            gm = garbage_metrics(t)
            pages.append({
                'page': i + 1,
                'chars': chars,
                'classification': classify(chars, gm['garbled']),
                'garbled': gm['garbled'],
                'metrics': gm,
                'sample': t.strip()[:SAMPLE_LEN].replace('\n', ' '),
            })
    else:
        for i, c in enumerate(counts):
            pages.append({
                'page': i + 1,
                'chars': c,
                'classification': classify(c, False),
                'garbled': None,
                'metrics': None,
                'sample': '',
                'note': 'stdlib_count: 值为文本绘制字节数近似，未做乱码检测',
            })

    summary = {'text': 0, 'sparse': 0, 'none': 0, 'garbled_pages': 0}
    for p in pages:
        summary[p['classification']] += 1
        if p['garbled']:
            summary['garbled_pages'] += 1

    if forensics_path and os.path.isfile(forensics_path):
        try:
            with open(forensics_path, encoding='utf-8') as fh:
                fx = json.load(fh)
            if fx.get('page_count') is not None and fx['page_count'] != len(pages):
                notes.append('page_count_mismatch: forensics=%d probe=%d' % (fx['page_count'], len(pages)))
        except (json.JSONDecodeError, OSError) as e:
            notes.append('forensics_read_failed: %s' % e)

    status = 'partial' if (degraded or notes) else 'ok'
    return {
        'tool': 'textlayer_probe.py',
        'pdf_path': os.path.abspath(path),
        'generated_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'status': status,
        'engine': engine,
        'engine_notes': engine_notes,
        'thresholds': {
            'none_max_chars': NONE_MAX_CHARS,
            'text_min_chars': TEXT_MIN_CHARS,
            'garbage_ratio_threshold': GARBAGE_RATIO_THRESHOLD,
        },
        'page_count': len(pages),
        'pages': pages,
        'classification_summary': summary,
        'notes': notes,
    }, (EXIT_PARTIAL if status == 'partial' else EXIT_OK)


def main(argv=None):
    ap = argparse.ArgumentParser(description='每页文字层判定')
    ap.add_argument('pdf')
    ap.add_argument('--forensics', help='可选：forensics.json，用于页数交叉核对')
    ap.add_argument('-o', '--out', help='probe.json 输出路径（缺省打印到 stdout）')
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pdf):
        sys.stderr.write('ERROR: 文件不存在: %s\n' % args.pdf)
        return EXIT_FAIL
    report, code = probe(args.pdf, args.forensics)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        sys.stderr.write('probe.json -> %s (engine=%s, status=%s, exit=%d)\n'
                         % (args.out, report.get('engine'), report.get('status'), code))
    else:
        print(text)
    return code


if __name__ == '__main__':
    sys.exit(main())
