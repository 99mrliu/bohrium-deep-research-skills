#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
route_case.py — 取证路由（bundle A: pdf-intake-forensics）

读取 forensics.json + probe.json + case.json，产出:
    routing_plan.json   机器可读路由计划（strategy / ocr_pages / handoff_reason）
    intake_summary.md   人读摘要
    result.json         契约感知交付物（含 case_id、output_contract 声明字段、
                        status / sources / uncertainty / change_record）

路由策略:
    direct_text  全部页均有可用文字层且未截尾 -> 直接文本解析
    mixed_ocr    部分页需 OCR（none/sparse/乱码页列入 ocr_pages）
    full_ocr     全部页需 OCR
    handoff      本 Skill 无法处理（加密 / 非 PDF / 结构不可恢复 / 无文字引擎），交人工或专用工具

退出码: 0=success 2=partial（截尾/降级/契约字段无法填充等） 3=failed（不可路由）
"""
import argparse
import datetime
import json
import os
import sys

EXIT_OK = 0
EXIT_PARTIAL = 2
EXIT_FAIL = 3

STRATEGIES = ('direct_text', 'mixed_ocr', 'full_ocr', 'handoff')


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def load_json(path, what):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def decide(forensics, probe):
    """返回 (strategy, ocr_pages, handoff_reason, issues)。"""
    issues = []
    ocr_pages = []
    handoff_reason = None

    if forensics.get('status') == 'failed':
        return 'handoff', [], 'not_a_pdf_or_unreadable: %s' % forensics.get('failure_reason'), issues
    if forensics.get('encrypted'):
        return 'handoff', [], 'encrypted_pdf: 存在 /Encrypt，须先解密', issues
    if probe.get('status') == 'failed':
        return 'handoff', [], 'no_text_engine: %s' % probe.get('failure_reason'), issues
    if forensics.get('xref', {}).get('truncated'):
        issues.append('truncated_input: 文件疑似截尾，以下路由仅覆盖已恢复部分')
    if forensics.get('page_count', 0) == 0:
        return 'handoff', [], 'structure_unrecoverable: 未扫描到任何页面对象', issues

    pages = probe.get('pages', [])
    for p in pages:
        if p['classification'] != 'text' or p.get('garbled'):
            ocr_pages.append(p['page'])
    if not pages:
        return 'handoff', [], 'no_pages_probed: 引擎未返回任何页', issues
    if len(ocr_pages) == len(pages):
        strategy = 'full_ocr'
    elif ocr_pages:
        strategy = 'mixed_ocr'
    else:
        strategy = 'direct_text'
    return strategy, ocr_pages, handoff_reason, issues


def fill_contract_fields(case, forensics, probe, strategy, ocr_pages, summary_line):
    """output_contract 字段填充器；未识别字段返回 (None, 原因)。"""
    fillers = {
        'pdf_file': lambda: os.path.basename(forensics.get('pdf_path', '')),
        'pdf_path': lambda: forensics.get('pdf_path'),
        'page_count': lambda: forensics.get('page_count'),
        'routing_strategy': lambda: strategy,
        'ocr_pages': lambda: ocr_pages,
        'intake_notes': lambda: summary_line,
    }

    def fill(name):
        fn = fillers.get(name)
        if fn is None:
            return None, 'contract_field_unknown: 无填充器，置空'
        value = fn()
        if value is None:
            return None, 'contract_field_unfillable: 上游数据缺失，置空'
        return value, None
    return fill


def build_summary(case_id, forensics, probe, strategy, ocr_pages, handoff_reason, issues):
    lines = []
    lines.append('# Intake Summary — %s' % case_id)
    lines.append('')
    lines.append('- PDF: `%s`' % forensics.get('pdf_path'))
    lines.append('- 文件大小: %s 字节；PDF 版本: %s；线性化: %s；加密: %s'
                 % (forensics.get('file_size_bytes'), forensics.get('pdf_version'),
                    forensics.get('linearized'), forensics.get('encrypted')))
    lines.append('- 取证状态: %s；探测状态: %s（引擎: %s）'
                 % (forensics.get('status'), probe.get('status'), probe.get('engine')))
    lines.append('- 页数: forensics=%s / probe=%s'
                 % (forensics.get('page_count'), probe.get('page_count')))
    meta = forensics.get('metadata') or {}
    if meta:
        lines.append('- 元数据: %s' % '; '.join('%s=%s' % kv for kv in meta.items()))
    lines.append('')
    lines.append('## 每页判定')
    lines.append('')
    lines.append('| 页 | 分类 | 非空白字符 | 乱码 | 文本字节(标准库) | 图像数 | 字体 |')
    lines.append('|---|---|---|---|---|---|---|')
    fxp = {p['object']: p for p in forensics.get('pages', [])}
    fx_by_idx = forensics.get('pages', [])
    for p in probe.get('pages', []):
        i = p['page'] - 1
        fx = fx_by_idx[i] if 0 <= i < len(fx_by_idx) else {}
        fonts = ', '.join((f.get('base_font') or '?') +
                          ('' if f.get('has_tounicode') else '(无ToUnicode)')
                          for f in fx.get('fonts', [])) or '—'
        lines.append('| %d | %s | %s | %s | %s | %s | %s |'
                     % (p['page'], p['classification'], p.get('chars'), p.get('garbled'),
                        fx.get('text_showing_bytes', '—'), fx.get('image_count', '—'), fonts))
    lines.append('')
    lines.append('## 路由结论')
    lines.append('')
    lines.append('- **strategy: %s**' % strategy)
    lines.append('- ocr_pages: %s' % (ocr_pages if ocr_pages else '[]'))
    if handoff_reason:
        lines.append('- handoff_reason: %s' % handoff_reason)
    nxt = {
        'direct_text': '下游可直接做文本解析（阅读顺序/表格/章节等，超出本 Skill 范围）。',
        'mixed_ocr': 'ocr_pages 所列页需 OCR 后处理（交 d-scan-ocr-trust 方向），其余页直接文本解析。',
        'full_ocr': '全文无可用文字层，整体走 OCR 管线（交 d-scan-ocr-trust 方向）。',
        'handoff': '本 Skill 无法处理，按 handoff_reason 交人工或专用工具，禁止强行解析。',
    }[strategy]
    lines.append('- 下一步: %s' % nxt)
    if issues:
        lines.append('')
        lines.append('## 风险与问题')
        lines.append('')
        for it in issues:
            lines.append('- %s' % it)
    for it in forensics.get('issues', []):
        lines.append('- [forensics] %s' % it)
    for it in probe.get('engine_notes', []):
        lines.append('- [probe] %s' % it)
    lines.append('')
    return '\n'.join(lines)


def run(case_path, forensics_path, probe_path, outdir, pdf_override=None, case_id_override=None):
    case = load_json(case_path, 'case.json')
    forensics = load_json(forensics_path, 'forensics.json')
    probe = load_json(probe_path, 'probe.json')
    case_id = case_id_override or case.get('case_id', 'unknown-case')
    if pdf_override:
        case = dict(case, pdf=pdf_override)

    strategy, ocr_pages, handoff_reason, issues = decide(forensics, probe)
    truncated = bool(forensics.get('xref', {}).get('truncated'))
    degraded = forensics.get('status') == 'partial' or probe.get('status') == 'partial'

    plan = {
        'tool': 'route_case.py',
        'case_id': case_id,
        'generated_at': now(),
        'strategy': strategy,
        'ocr_pages': ocr_pages,
        'handoff_reason': handoff_reason,
        'page_count': forensics.get('page_count'),
        'truncated_input': truncated,
        'issues': issues,
        'inputs': {'case': os.path.abspath(case_path),
                   'forensics': os.path.abspath(forensics_path),
                   'probe': os.path.abspath(probe_path)},
    }

    summary_line = ('%s: %d 页, strategy=%s, ocr_pages=%s%s'
                    % (os.path.basename(forensics.get('pdf_path', case.get('pdf', '?'))),
                       forensics.get('page_count') or 0, strategy, ocr_pages,
                       '（输入截尾，结果部分）' if truncated else ''))
    summary_md = build_summary(case_id, forensics, probe, strategy, ocr_pages,
                               handoff_reason, issues)

    # ---- 契约感知 result.json ----
    uncertainty = list(issues)
    contract = case.get('output_contract', {})
    field_names = contract.get('fields', []) if isinstance(contract, dict) else list(contract or [])
    fill = fill_contract_fields(case, forensics, probe, strategy, ocr_pages, summary_line)
    result = {'case_id': case_id}
    unfillable = 0
    for name in field_names:
        value, why = fill(name)
        result[name] = value
        if why:
            unfillable += 1
            uncertainty.append('%s: %s' % (name, why))
    if strategy == 'handoff':
        uncertainty.append('handoff: %s' % handoff_reason)
    if unfillable or truncated or strategy == 'handoff' or degraded:
        status = 'partial'
    else:
        status = 'success'
    if forensics.get('status') == 'failed':
        status = 'failed'
    result.update({
        'status': status,
        'sources': [os.path.abspath(p) for p in (case.get('pdf'), forensics_path, probe_path) if p],
        'uncertainty': uncertainty,
        'change_record': [
            {'at': now(), 'actor': 'route_case.py',
             'action': 'read forensics.json + probe.json + case.json'},
            {'at': now(), 'actor': 'route_case.py',
             'action': 'decided strategy=%s ocr_pages=%s' % (strategy, ocr_pages)},
            {'at': now(), 'actor': 'route_case.py',
             'action': 'wrote routing_plan.json / intake_summary.md / result.json (status=%s)' % status},
        ],
    })

    os.makedirs(outdir, exist_ok=True)
    paths = {
        'routing_plan.json': json.dumps(plan, ensure_ascii=False, indent=2) + '\n',
        'intake_summary.md': summary_md,
        'result.json': json.dumps(result, ensure_ascii=False, indent=2) + '\n',
    }
    for name, text in paths.items():
        with open(os.path.join(outdir, name), 'w', encoding='utf-8') as fh:
            fh.write(text)
    sys.stderr.write('route_case: strategy=%s status=%s -> %s\n' % (strategy, status, outdir))
    if status == 'failed':
        return EXIT_FAIL
    return EXIT_PARTIAL if status == 'partial' else EXIT_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description='取证路由：forensics+probe+case -> routing plan')
    ap.add_argument('--case', required=True, help='case.json')
    ap.add_argument('--forensics', required=True, help='forensics.json')
    ap.add_argument('--probe', required=True, help='probe.json')
    ap.add_argument('--outdir', required=True, help='输出目录（routing_plan.json/intake_summary.md/result.json）')
    ap.add_argument('--pdf', help='可选：覆盖 case.json 中的 pdf 路径（用于同契约多样本）')
    ap.add_argument('--case-id', help='可选：覆盖 case_id（用于同契约多样本）')
    args = ap.parse_args(argv)
    for p, what in ((args.case, 'case.json'), (args.forensics, 'forensics.json'), (args.probe, 'probe.json')):
        if not os.path.isfile(p):
            sys.stderr.write('ERROR: %s 不存在: %s\n' % (what, p))
            return EXIT_FAIL
    return run(args.case, args.forensics, args.probe, args.outdir, args.pdf, args.case_id)


if __name__ == '__main__':
    sys.exit(main())
