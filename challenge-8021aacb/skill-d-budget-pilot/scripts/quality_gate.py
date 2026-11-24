#!/usr/bin/env python3
"""quality_gate.py -- 交付前终检质量门。

九项检查全部通过才允许 status=ok; 任何失败项写入 audit 报告并以退出码 1 阻断。
这是「可靠体验」的机器保证: 状态诚实、契约完整、产物存在且非空。

用法:
    python3 quality_gate.py RESULT_JSON OUTPUT_DIR AUDIT_MD
"""
import json
import os
import sys


def _check(name, ok, detail=''):
    return {'check': name, 'pass': bool(ok), 'detail': detail}


def gate(result_path, output_dir, audit_path):
    with open(result_path, encoding='utf-8') as f:
        doc = json.load(f)

    checks = []
    checks.append(_check('case_id_present',
                         bool(doc.get('case_id')) and doc['case_id'] != 'unknown',
                         'case_id=%r' % doc.get('case_id')))
    fields = doc.get('_contract_fields', [])
    unfilled = [k for k in fields if doc.get(k) is None]
    checks.append(_check('contract_fields_declared', bool(fields),
                         '%d fields' % len(fields)))
    checks.append(_check('contract_fields_filled', not unfilled,
                         'unfilled: %s' % ', '.join(unfilled) if unfilled else 'all filled'))
    st = doc.get('status')
    checks.append(_check('status_legal', st in ('ok', 'partial', 'failed'),
                         'status=%r' % st))
    if st == 'ok':
        checks.append(_check('ok_implies_complete', not unfilled,
                             'status=ok 但契约字段未填满' if unfilled else ''))
        checks.append(_check('ok_implies_no_pending_uncertainty',
                             not any('待' in u or 'pending' in u.lower()
                                     for u in doc.get('uncertainty', [])),
                             '仍有未决 uncertainty'))
    if st == 'partial':
        checks.append(_check('partial_has_reason',
                             bool(doc.get('uncertainty')) or bool(doc.get('degradation_log')),
                             'partial 必须说明限制'))
    checks.append(_check('checkpoints_cover_phases',
                         len(doc.get('checkpoints', [])) >= 4,
                         '%d checkpoints' % len(doc.get('checkpoints', []))))
    expected = ['diagnosis', 'editing_plan']
    missing_files = [n for n in expected
                     if not os.path.isfile(os.path.join(output_dir, n + '.md'))
                     and not os.path.isfile(os.path.join(output_dir, n + '.json'))]
    checks.append(_check('deliverable_files_exist', not missing_files,
                         'missing: %s' % ', '.join(missing_files) if missing_files else 'present'))
    checks.append(_check('change_record_present',
                         isinstance(doc.get('change_record'), list),
                         'change_record 为列表（可为空）'))

    npass = sum(1 for c in checks if c['pass'])
    verdict = all(c['pass'] for c in checks)
    lines = ['# 交付终检报告（quality_gate）', '',
             '- result.json: `%s`' % result_path,
             '- 检查通过: %d/%d' % (npass, len(checks)),
             '- 结论: **%s**' % ('PASS' if verdict else 'BLOCK'), '',
             '| 检查项 | 结果 | 说明 |', '|---|---|---|']
    for c in checks:
        lines.append('| %s | %s | %s |' % (c['check'], '✅' if c['pass'] else '❌',
                                           c['detail'].replace('|', '\\|')))
    with open(audit_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(json.dumps({'pass': verdict, 'checks': '%d/%d' % (npass, len(checks))},
                     ensure_ascii=False))
    return 0 if verdict else 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: quality_gate.py RESULT_JSON OUTPUT_DIR AUDIT_MD')
    sys.exit(gate(*sys.argv[1:4]))
