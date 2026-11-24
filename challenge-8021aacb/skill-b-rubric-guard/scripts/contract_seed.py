#!/usr/bin/env python3
"""contract_seed.py -- 从 case.json 播种 result.json 与六维诊断骨架。

与诊断内容无关: 只保证结构完整——case_id、output_contract 全字段、
六维 finding 容器与 clearance 容器预先就位, 让「缺维」在任何时候都可见。

用法:
    python3 contract_seed.py CASE_JSON RESULT_OUT DIAG_SKELETON_OUT
"""
import datetime
import json
import os
import sys

DIMENSIONS = ['研究问题', '章节结构', '论证链', '段落关系', '重复内容', '结论边界']


def seed(case_path, result_out, diag_out):
    with open(case_path, encoding='utf-8') as f:
        case = json.load(f)
    case_id = case.get('case_id', 'unknown')
    contract = case.get('output_contract') or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])

    result = {'case_id': case_id, 'status': 'partial',
              'generated_by': 'skill-b-rubric-guard (six-dimension rubric pipeline)',
              'seeded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'uncertainty': ['骨架已播种; 诊断内容待填充'],
              'sources': [], 'change_record': []}
    for k in fields:
        result.setdefault(k, None)
    os.makedirs(os.path.dirname(os.path.abspath(result_out)), exist_ok=True)
    with open(result_out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    diag = {'case_id': case_id, 'findings': [],
            'dimension_clearance': {d: None for d in DIMENSIONS},
            'rubric_version': 'taxonomy_six.md v1 (bundle skill-b)'}
    with open(diag_out, 'w', encoding='utf-8') as f:
        json.dump(diag, f, ensure_ascii=False, indent=2)
    print(json.dumps({'case_id': case_id, 'contract_fields': fields,
                      'dimensions_seeded': DIMENSIONS}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: contract_seed.py CASE_JSON RESULT_OUT DIAG_SKELETON_OUT')
    seed(*sys.argv[1:4])
