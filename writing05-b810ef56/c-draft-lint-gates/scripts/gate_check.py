#!/usr/bin/env python3
"""质量门禁裁决器：按门禁策略对 lint 报告做 PASS/FAIL 裁决。

只依赖标准库。把"哪些检查不通过就不许交付"从口头约定变成可执行
策略文件，裁决结果与修复顺序写入 gate_report.md。

用法：
    python3 gate_check.py --lint LINT_JSON --policy POLICY_JSON \
        --report GATE_MD

POLICY_JSON 结构（见 references/gate_policy.json 默认策略）：
    {"fail_on_severity": ["error"],
     "max_warnings": 10,
     "rule_overrides": {"UNMARKED-FACT": "ignore"},
     "waivers": [{"rule": "...", "line": 0, "reason": "..."}]}

waiver 用于经人工确认的例外：必须写理由，且只对精确规则+行号生效
（line=0 表示该规则全篇豁免）。

退出码：0 = 门禁 PASS；1 = 门禁 FAIL；2 = 用法/IO 错误。
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lint', required=True)
    ap.add_argument('--policy', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    with open(args.lint, encoding='utf-8') as fh:
        lint = json.load(fh)
    with open(args.policy, encoding='utf-8') as fh:
        policy = json.load(fh)

    fail_on = set(policy.get('fail_on_severity', ['error']))
    max_warnings = int(policy.get('max_warnings', 10))
    overrides = policy.get('rule_overrides', {})
    waivers = {(w['rule'], int(w.get('line', 0))): w.get('reason', '')
               for w in policy.get('waivers', [])}

    effective, waived = [], []
    for f in lint.get('findings', []):
        severity = overrides.get(f['rule'], f['severity'])
        if severity == 'ignore':
            continue
        key = (f['rule'], f['line'])
        if key in waivers or (f['rule'], 0) in waivers:
            waived.append(dict(f, waiver_reason=waivers.get(
                key, waivers.get((f['rule'], 0), ''))))
            continue
        effective.append(dict(f, severity=severity))

    blocking = [f for f in effective if f['severity'] in fail_on]
    warnings = [f for f in effective if f['severity'] == 'warning']
    gate_fail = bool(blocking) or len(warnings) > max_warnings

    lines = ['# 质量门禁裁决报告', '',
             '门禁结果：**%s**' % ('FAIL' if gate_fail else 'PASS'), '',
             '- 阻断项（%s）：%d' % ('/'.join(sorted(fail_on)),
                                     len(blocking)),
             '- 警告项：%d（上限 %d）' % (len(warnings), max_warnings),
             '- 人工豁免：%d' % len(waived), '',
             '## 阻断项（按行号排序，逐项修复后重跑 lint + 门禁）', '']
    if blocking:
        lines += ['| 规则 | 行 | 上下文 | 建议 |', '|---|---|---|---|']
        for f in sorted(blocking, key=lambda x: x['line']):
            lines.append('| %s | %s | %s | %s |' % (
                f['rule'], f['line'] or '-',
                f['context'].replace('|', '/'),
                f['advice'].replace('|', '/')))
    else:
        lines.append('（无）')
    if waived:
        lines += ['', '## 人工豁免（须有理由）', '',
                  '| 规则 | 行 | 理由 |', '|---|---|---|']
        for f in waived:
            lines.append('| %s | %s | %s |' % (
                f['rule'], f['line'] or '-', f['waiver_reason']))
    lines += ['', '裁决口径：%s。' % (
        '存在阻断项或警告超上限即 FAIL' if gate_fail else
        '无阻断项且警告未超上限')]
    with open(args.report, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')

    print(json.dumps({'gate': 'FAIL' if gate_fail else 'PASS',
                      'blocking': len(blocking),
                      'warnings': len(warnings),
                      'waived': len(waived)}, ensure_ascii=False))
    return 1 if gate_fail else 0


if __name__ == '__main__':
    sys.exit(main())
