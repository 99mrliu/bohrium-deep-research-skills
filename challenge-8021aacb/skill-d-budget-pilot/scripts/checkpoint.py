#!/usr/bin/env python3
"""checkpoint.py -- 检查点协议: 每个阶段出口更新 result.json, 保证随时可交付。

用法:
    python3 checkpoint.py init CASE_JSON RESULT_JSON
    python3 checkpoint.py mark RESULT_JSON --phase PHASE --note NOTE \
        [--requests-used N] [--seconds-used N] [--degraded REASON]
    python3 checkpoint.py status RESULT_JSON

状态机: partial -> (ok | partial | failed)。只允许 failed 由系统原因给出;
degraded 记录进入 result.degradation_log, 与 uncertainty 分列。
"""
import argparse
import datetime
import json
import os

PHASE_ORDER = ['contract_and_inventory', 'extraction', 'diagnosis_core',
               'verification', 'deliverables', 'finalize']


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _save(path, doc):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # 原子写: 任何时刻磁盘上都是有效 JSON


def cmd_init(a):
    case = _load(a.case)
    contract = case.get('output_contract') or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])
    doc = {'case_id': case.get('case_id', 'unknown'), 'status': 'partial',
           'generated_by': 'skill-d-budget-pilot (budgeted orchestration)',
           'created_at': _now(), 'checkpoints': [],
           'degradation_log': [], 'uncertainty': ['初始化完成; 诊断未开始'],
           'sources': [], 'change_record': []}
    for k in fields:
        doc.setdefault(k, None)
    doc['_contract_fields'] = fields
    _save(a.result, doc)
    print(json.dumps({'case_id': doc['case_id'], 'contract_fields': fields},
                     ensure_ascii=False))


def cmd_mark(a):
    doc = _load(a.result)
    done = [c['phase'] for c in doc.get('checkpoints', [])]
    if a.phase in PHASE_ORDER:
        expected = PHASE_ORDER[len([p for p in PHASE_ORDER if p in done])]
        if a.phase != expected:
            doc.setdefault('uncertainty', []).append(
                'checkpoint out-of-order: expected %s got %s' % (expected, a.phase))
    doc.setdefault('checkpoints', []).append(
        {'phase': a.phase, 'at': _now(), 'note': a.note,
         'requests_used': a.requests_used, 'seconds_used': a.seconds_used})
    if a.degraded:
        doc.setdefault('degradation_log', []).append(
            {'phase': a.phase, 'at': _now(), 'reason': a.degraded})
    doc['updated_at'] = _now()
    _save(a.result, doc)
    print(json.dumps({'checkpoints': len(doc['checkpoints']),
                      'degraded': len(doc.get('degradation_log', []))}, ensure_ascii=False))


def cmd_status(a):
    doc = _load(a.result)
    fields = doc.get('_contract_fields', [])
    unfilled = [k for k in fields if doc.get(k) is None]
    print(json.dumps({'status': doc.get('status'),
                      'checkpoints': [c['phase'] for c in doc.get('checkpoints', [])],
                      'contract_unfilled': unfilled,
                      'degradations': len(doc.get('degradation_log', []))},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('case')
    p.add_argument('result')
    p = sub.add_parser('mark')
    p.add_argument('result')
    p.add_argument('--phase', required=True)
    p.add_argument('--note', default='')
    p.add_argument('--requests-used', type=int, default=None)
    p.add_argument('--seconds-used', type=int, default=None)
    p.add_argument('--degraded', default=None)
    p = sub.add_parser('status')
    p.add_argument('result')
    a = ap.parse_args()
    {'init': cmd_init, 'mark': cmd_mark, 'status': cmd_status}[a.cmd](a)


if __name__ == '__main__':
    main()
