#!/usr/bin/env python3
"""result_kit.py -- 契约驱动的 result.json 骨架与收尾工具。

契约来源只有 /input/case.json: output_contract 的每个字段都原样落到
result.json, 绝不凭题目名称猜字段。

用法:
    python3 result_kit.py init  CASE_JSON OUT_JSON [--note NOTE]
    python3 result_kit.py final CASE_JSON OUT_JSON --status ok|partial|failed \
        [--findings N] [--verified PCT] [--note NOTE]
"""
import argparse
import datetime
import json
import os


def load_contract(case_path):
    with open(case_path, encoding='utf-8') as f:
        case = json.load(f)
    contract = case.get('output_contract') or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])
    return case.get('case_id', 'unknown'), fields


def skeleton(case_path, note):
    case_id, fields = load_contract(case_path)
    doc = {'case_id': case_id, 'status': 'partial',
           'generated_by': 'skill-a-anchor-provenance (anchor fidelity pipeline)',
           'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'note': note,
           'uncertainty': ['result.json 尚在构建; 本文件为诚实的 partial 结果'],
           'sources': [], 'change_record': []}
    for k in fields:
        doc.setdefault(k, None)
    return doc, fields


def cmd_init(args):
    doc, fields = skeleton(args.case, args.note)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(json.dumps({'case_id': doc['case_id'], 'contract_fields': fields},
                     ensure_ascii=False))


def cmd_final(args):
    with open(args.out, encoding='utf-8') as f:
        doc = json.load(f)
    case_id, fields = load_contract(args.case)
    doc['case_id'] = case_id
    for k in fields:  # 契约字段缺失时补 null 并记录, 不留空档
        if k not in doc:
            doc[k] = None
            doc.setdefault('uncertainty', []).append('contract field %s not produced' % k)
    doc['status'] = args.status
    doc['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if args.note:
        doc['note'] = args.note
    missing = [k for k in fields if doc.get(k) is None]
    doc['contract_check'] = {'fields': fields, 'unfilled': missing,
                             'complete': not missing}
    if args.verified is not None:
        doc['quote_verification'] = {'verified_fraction': args.verified,
                                     'findings': args.findings}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': doc['status'], 'contract_complete': not missing,
                      'unfilled': missing}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('case')
    p.add_argument('out')
    p.add_argument('--note', default='input inventory done; extraction pending')
    p = sub.add_parser('final')
    p.add_argument('case')
    p.add_argument('out')
    p.add_argument('--status', choices=['ok', 'partial', 'failed'], required=True)
    p.add_argument('--findings', type=int, default=None)
    p.add_argument('--verified', type=float, default=None)
    p.add_argument('--note', default='')
    args = ap.parse_args()
    {'init': cmd_init, 'final': cmd_final}[args.cmd](args)


if __name__ == '__main__':
    main()
