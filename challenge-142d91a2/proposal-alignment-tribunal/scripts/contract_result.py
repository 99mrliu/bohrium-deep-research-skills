#!/usr/bin/env python3
"""contract_result.py -- result.json 契约纪律工具（本 bundle 独立实现）。

两个子命令：
  init  CASE_JSON RESULT_OUT   读 case.json，播种有效 partial 骨架：
                               case_id、output_contract 全字段（初值 null）、
                               status:"partial"、sources、uncertainty、change_records。
  final CASE_JSON RESULT_JSON  收尾校验：契约字段缺项强制 status:"partial" 并在
                               uncertainty 点名；verification_report.gate_pass 为
                               false 同样强制 partial（对齐门未过不得宣称 ok）；
                               字段齐备且无阻断才允许 status:"ok"。

退出码：init 恒 0；final 通过 0、被强制 partial 1。
"""
import argparse
import datetime
import json
import os
import sys


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_contract_fields(case):
    contract = case.get('output_contract') or {}
    if isinstance(contract, dict):
        return list(contract.keys())
    return list(contract or [])


def cmd_init(case_path, result_out):
    with open(case_path, encoding='utf-8') as f:
        case = json.load(f)
    fields = load_contract_fields(case)
    result = {
        'case_id': case.get('case_id', 'unknown'),
        'status': 'partial',
        'generated_by': 'proposal-alignment-tribunal (alignment-gated proposal pipeline)',
        'seeded_at': utcnow(),
        'sources': [],
        'uncertainty': ['骨架已播种；契约字段待填充，对齐裁定未执行'],
        'change_records': [{'ts': utcnow(), 'event': 'init',
                            'detail': '按 output_contract 播种 %d 个字段' % len(fields)}],
    }
    for k in fields:
        result[k] = None
    os.makedirs(os.path.dirname(os.path.abspath(result_out)), exist_ok=True)
    with open(result_out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'case_id': result['case_id'], 'contract_fields': fields,
                      'status': 'partial'}, ensure_ascii=False))
    return 0


def cmd_final(case_path, result_path):
    with open(case_path, encoding='utf-8') as f:
        case = json.load(f)
    with open(result_path, encoding='utf-8') as f:
        result = json.load(f)
    fields = load_contract_fields(case)

    missing = [k for k in fields
               if result.get(k) is None or result.get(k) == '' or
               result.get(k) == [] or result.get(k) == {}]
    blockers = []
    vr = result.get('verification_report')
    if isinstance(vr, dict) and vr.get('gate_pass') is False:
        fails = vr.get('fails') or []
        blockers.append(
            'verification_report.gate_pass=false：对齐门未过（%d 项 fail：%s）'
            % (vr.get('fail_count', len(fails)),
               '；'.join('%s[%s] %s' % (x.get('rule'), x.get('target'), x.get('detail'))
                         for x in fails) or '详见报告'))

    uncertainty = result.setdefault('uncertainty', [])
    for k in missing:
        note = '契约字段缺项：%s' % k
        if note not in uncertainty:
            uncertainty.append(note)
    for b in blockers:
        if b not in uncertainty:
            uncertainty.append(b)

    ok = not missing and not blockers
    result['status'] = 'ok' if ok else 'partial'
    result.setdefault('change_records', []).append({
        'ts': utcnow(), 'event': 'final',
        'detail': '契约校验通过，status=ok' if ok else
                  '强制 partial：缺项 %s；阻断 %s' % (missing or '无', blockers or '无')})
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': result['status'], 'missing_fields': missing,
                      'blockers': len(blockers)}, ensure_ascii=False))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description='result.json 契约 init/final 纪律工具')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_init = sub.add_parser('init', help='播种有效 partial 骨架')
    p_init.add_argument('case_json')
    p_init.add_argument('result_out')
    p_fin = sub.add_parser('final', help='收尾校验并定 status')
    p_fin.add_argument('case_json')
    p_fin.add_argument('result_json')
    args = ap.parse_args()

    if args.cmd == 'init':
        return cmd_init(args.case_json, args.result_out)
    return cmd_final(args.case_json, args.result_json)


if __name__ == '__main__':
    sys.exit(main())
