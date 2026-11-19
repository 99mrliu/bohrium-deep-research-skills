#!/usr/bin/env python3
"""evidence-ledger-pdf: phase 1 entrypoint.

Parses every PDF under the input dir into per-page plain text, builds a
page/offset corpus index, and writes a partial result.json. Stdlib only.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdfindex


def load_case(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    corpus_dir = os.path.join(args.work, 'corpus_pages')
    os.makedirs(corpus_dir, exist_ok=True)

    t0 = time.time()
    case = load_case(args.case)
    case_id = case.get('case_id') or case.get('id') or 'unknown-case'

    index, parse_errors, tool = pdfindex.build_index(args.input_dir, corpus_dir)
    total_pages = sum(len(d['pages']) for d in index['documents'])
    total_chars = sum(p['char_end'] - p['char_start']
                      for d in index['documents'] for p in d['pages'])

    # empty ledger / claim register scaffolding
    write_json(os.path.join(args.out, 'corpus_index.json'), index)
    write_json(os.path.join(args.out, 'parse_report.json'), {
        'case_id': case_id, 'parser': tool,
        'documents': len(index['documents']), 'pages': total_pages,
        'chars': total_chars, 'parse_errors': parse_errors,
        'note': 'PDF 加密/损坏/为空如实记录于此，绝不做假解析'})

    ledger_path = os.path.join(args.out, 'evidence_ledger.json')
    if not os.path.exists(ledger_path):
        write_json(ledger_path, {'case_id': case_id, 'next_id': 1,
                                 'evidence': []})
    claims_path = os.path.join(args.out, 'claim_register.json')
    if not os.path.exists(claims_path):
        write_json(claims_path, {'case_id': case_id, 'next_id': 1,
                                 'claims': []})

    blocked = []
    if not index['documents']:
        blocked.append('input 目录未发现可解析的 PDF 材料，无法建立证据回链')
    warnings = []
    if parse_errors:
        warnings.append('%d 个文档解析异常，见 parse_report.json' %
                        len(parse_errors))

    with open(os.path.join(args.out, 'synthesis.md'), 'w',
              encoding='utf-8') as f:
        f.write('# 证据综合（%s）\n\n' % case_id)
        f.write('> 规则：每条结论句内联 ⟦EV-xxxx⟧ 锚点；引用未通过核验的结论'
                '只进"无法确定"段。\n\n## 结论\n\n（待填）\n\n'
                '## 冲突证据（引用均已核验的冲突对）\n\n（待填）\n\n'
                '## 研究空白（每句须附阅读范围依据）\n\n（待填）\n\n'
                '## 无法确定\n\n（待填）\n')

    result = {
        'case_id': case_id,
        'status': 'blocked' if blocked else 'partial',
        'research_output': None,
        'sources': [{'doc_id': d['doc_id'], 'path': d['path'],
                     'pages': len(d['pages']), 'sha256': d['sha256']}
                    for d in index['documents']],
        'uncertainty': warnings + blocked +
        (['phase1 仅完成 PDF 解析与语料索引，证据与结论尚未回填']
         if not blocked else []),
        'six_aspects': {
            '问题拆解': '由 Agent 依据 task.md 在 ledger add 时以 --sq 标注',
            '检索覆盖': '材料范围=corpus_index.json 所列文档；超出范围的结论须标 unknown',
            '证据回链': 'verify.py 回链率与 backlink_report.json（当前 0 条结论）',
            '冲突证据': 'synthesis.md 冲突段：仅收录引用已核验的冲突对',
            '综合结论': 'synthesis.md（⟦EV-xxxx⟧ 内联锚点）',
            '研究空白': '每句空白判断须附阅读范围依据'},
        'schema_version': 'evledger-b/1.0'}
    oc = case.get('output_contract') or case.get('outputContract') or {}
    keys = oc if isinstance(oc, list) else (
        list(oc.keys()) if isinstance(oc, dict) else [])
    for k in keys:
        result.setdefault(k, None)
    write_json(os.path.join(args.out, 'result.json'), result)

    write_json(os.path.join(args.out, 'run_manifest.json'), {
        'case_id': case_id, 'skill': 'evidence-ledger-pdf/1.0',
        'python': sys.version.split()[0],
        'parser': tool, 'phase1_seconds': round(time.time() - t0, 3),
        'run_steps': ['parse_pdfs', 'corpus_index', 'ledger_scaffold',
                      'partial_result']})
    print(json.dumps({'ok': not blocked, 'pdfs': len(index['documents']),
                      'pages': total_pages, 'tool': tool,
                      'parse_errors': len(parse_errors)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
