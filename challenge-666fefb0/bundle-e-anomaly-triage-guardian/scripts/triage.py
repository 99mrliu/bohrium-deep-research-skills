#!/usr/bin/env python3
"""triage.py — anomaly taxonomy, quarantine planning, health report.

Every input file gets exactly one triage class with detection evidence, a
disposition and a recovery suggestion. Problem files are NOT dropped: they are
copied to _quarantine/<class>/ under the original name so nothing is lost and
everything is inspectable. The pipeline never blocks on a single file.
"""
import json
import os

from inventory import read_json, write_json

TAXONOMY = {
    'ok': {'disposition': 'archive', 'recovery': None},
    'duplicate_bytes': {'disposition': 'archive_dup',
                        'recovery': '字节级重复；保留组内一份，其余入 _archive_dups/，不删除'},
    'sidecar': {'disposition': 'sidecar_admin', 'recovery': None},
    'encrypted_pdf': {'disposition': 'quarantine',
                      'recovery': '提供密码后用 pdftotext -upw 解密抽取，再重新 triage'},
    'corrupt_pdf': {'disposition': 'quarantine',
                    'recovery': '重新下载/修复文件（如 qpdf --repair），再重新 triage'},
    'no_text_layer': {'disposition': 'quarantine',
                      'recovery': '扫描件需 OCR（如 ocrmypdf），OCR 后重新 triage'},
    'permission_denied': {'disposition': 'quarantine',
                          'recovery': '修复读权限（chmod/chown）后重新 triage'},
    'read_error': {'disposition': 'quarantine', 'recovery': '检查文件系统/介质后重新 triage'},
    'empty_file': {'disposition': 'quarantine', 'recovery': '零字节文件；确认来源并重新获取'},
    'garbled_encoding': {'disposition': 'quarantine',
                         'recovery': '以原始编码（如 GBK/Big5）转码为 UTF-8 后重新 triage'},
    'unknown_binary': {'disposition': 'quarantine', 'recovery': '确认文件类型与配套读取工具'},
    'extract_unavailable': {'disposition': 'quarantine',
                            'recovery': '运行环境缺少 pdftotext；安装 poppler 后重新 triage'},
}


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def replacement_ratio(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read(20000)
    except OSError:
        return 0.0
    if not text:
        return 0.0
    return text.count('�') / len(text)


def classify(rec, dup_fids, work_dir):
    """One file -> (class, evidence)."""
    fid = rec['fid']
    if fid in dup_fids:
        return 'duplicate_bytes', f"SHA-256 与 {dup_fids[fid]} 相同（字节级重复下载）"
    if not rec.get('readable'):
        return rec.get('extract_status') or 'read_error', f"不可读: {rec.get('err')}"
    if rec.get('size') == 0:
        return 'empty_file', 'size=0'
    status = rec.get('extract_status')
    err = (rec.get('err') or '').lower()
    if status == 'extract_error':
        if 'password' in err or 'encrypt' in err:
            return 'encrypted_pdf', f"pdftotext: {rec.get('err', '')[:120]}"
        return 'corrupt_pdf', f"pdftotext 失败: {(rec.get('err') or '')[:120] or '无错误输出'}"
    if status in ('no_text_layer', 'permission_denied', 'read_error', 'extract_unavailable'):
        return status, f"extract_status={status}"
    if status == 'binary_no_extract':
        return 'unknown_binary', f"kind={rec.get('kind')}"
    ext_path = os.path.join(work_dir, 'extracted', f'{fid}.txt')
    if os.path.isfile(ext_path) and rec.get('kind') == 'text':
        ratio = replacement_ratio(ext_path)
        if ratio > 0.01:
            return 'garbled_encoding', f"U+FFFD 占比 {ratio:.1%}（疑似非 UTF-8 编码）"
    if rec['rel'].lower().endswith(('.md', '.csv', '.json', '.bib', '.txt', '.ris', '.yml', '.yaml')):
        return 'sidecar', '旁挂说明/元数据/数据文件'
    return 'ok', f"抽取正常（{len(rec.get('head_text') or '')} 字符预览）"


def run_triage(work_dir, out_dir):
    files = load_jsonl(os.path.join(work_dir, 'files.jsonl'))
    aliases = read_json(os.path.join(work_dir, 'aliases.json')) \
        if os.path.isfile(os.path.join(work_dir, 'aliases.json')) else []
    dup_fids = {}
    for g in aliases:
        for fid in g['fids'][1:]:
            dup_fids[fid] = g['fids'][0]

    records = []
    for rec in files:
        cls, evidence = classify(rec, dup_fids, work_dir)
        tax = TAXONOMY.get(cls, TAXONOMY['unknown_binary'])
        records.append({'fid': rec['fid'], 'rel': rec['rel'], 'triage_class': cls,
                        'evidence': evidence, 'disposition': tax['disposition'],
                        'recovery': tax['recovery']})
    with open(os.path.join(work_dir, 'triage.jsonl'), 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    counts = {}
    for r in records:
        counts[r['triage_class']] = counts.get(r['triage_class'], 0) + 1
    report = ['# 异常分诊报告（triage report）', '',
              f"文件总数 {len(records)}；分类分布: "
              + ', '.join(f'{k}={v}' for k, v in sorted(counts.items())), '',
              '| fid | 文件 | 分诊类别 | 处置 | 检测证据 | 恢复建议 |',
              '|---|---|---|---|---|---|']
    for r in records:
        report.append('| {} | `{}` | {} | {} | {} | {} |'.format(
            r['fid'], r['rel'], r['triage_class'], r['disposition'],
            r['evidence'].replace('|', '/'), (r['recovery'] or '—').replace('|', '/')))
    with open(os.path.join(out_dir, 'triage_report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    write_json(os.path.join(work_dir, 'triage_summary.json'),
               {'total': len(records), 'class_counts': counts})
    return records, counts
