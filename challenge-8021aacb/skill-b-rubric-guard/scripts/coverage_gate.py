#!/usr/bin/env python3
"""coverage_gate.py -- 六维覆盖门 + 空话检测 + finding 字段 lint。

三件事:
1. 覆盖门: 六维每维必须有 finding, 或有带「检查方式」的 clearance 记录; 缺维 = gate fail。
2. 字段 lint: 每条 finding 必须有 dimension/location/quote/defect_class/action/severity。
3. 空话检测: action 或 rationale 命中 GENERIC_PHRASES(放之四海而皆准的写作原则)即标出,
   要求改写为可执行编辑动作。

用法:
    python3 coverage_gate.py DIAGNOSIS_JSON OUT_JSON
退出码: gate 通过 0, 未通过 1 (CI 可阻断)。
"""
import json
import sys

DIMENSIONS = ['研究问题', '章节结构', '论证链', '段落关系', '重复内容', '结论边界']
REQUIRED = ['dimension', 'location', 'quote', 'defect_class', 'action', 'severity']
GENERIC_PHRASES = [
    '建议作者注意', '建议加强', '建议完善', '建议进一步', '可以更加清晰',
    '逻辑可以更严密', '建议润色', '表达可以更', '建议优化结构', '增强可读性',
    '建议修改', '注意连贯', '加强论证',
]


def gate(diag_path, out_path):
    with open(diag_path, encoding='utf-8') as f:
        diag = json.load(f)
    findings = diag.get('findings', [])
    clearance = diag.get('dimension_clearance', {})

    problems = []
    covered = set()
    for d in DIMENSIONS:
        n = sum(1 for x in findings if x.get('dimension') == d)
        cl = clearance.get(d)
        if n:
            covered.add(d)
        elif isinstance(cl, dict) and cl.get('how_checked'):
            covered.add(d)
        else:
            problems.append({'kind': 'missing_dimension', 'dimension': d,
                             'detail': '既无 finding 也无带 how_checked 的 clearance'})

    for i, x in enumerate(findings):
        fid = x.get('id', 'F%03d' % (i + 1))
        for k in REQUIRED:
            if not x.get(k):
                problems.append({'kind': 'missing_field', 'id': fid, 'field': k})
        for fld in ('action', 'rationale'):
            v = x.get(fld) or ''
            for ph in GENERIC_PHRASES:
                if ph in v:
                    problems.append({'kind': 'generic_advice', 'id': fid,
                                     'field': fld, 'phrase': ph,
                                     'detail': '空话须改写为移动/合并/拆分/收窄/删重/补过渡类动作'})
        if x.get('dimension') and x['dimension'] not in DIMENSIONS:
            problems.append({'kind': 'bad_dimension', 'id': fid,
                             'value': x['dimension']})

    report = {'diagnosis': diag_path,
              'dimensions_covered': sorted(covered),
              'dimensions_missing': [d for d in DIMENSIONS if d not in covered],
              'problem_count': len(problems),
              'gate_pass': not problems,
              'problems': problems}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'gate_pass': report['gate_pass'],
                      'problems': len(problems),
                      'missing': report['dimensions_missing']}, ensure_ascii=False))
    return 0 if report['gate_pass'] else 1


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: coverage_gate.py DIAGNOSIS_JSON OUT_JSON')
    sys.exit(gate(*sys.argv[1:3]))
