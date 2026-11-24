#!/usr/bin/env python3
"""输出契约解析器：把 case.json 编译成可执行的交付清单。

只依赖标准库。在写作开始前运行，把"要交什么"固定下来，避免成稿后
才发现 result.json 缺键、键名拼错或 case_id 走样。

用法：
    python3 contract_inspect.py CASE_JSON OUT_CONTRACT_JSON [--task TASK_MD]

输出（OUT_CONTRACT_JSON）：
    {
      "case_id": "...",                  // 原样提取；缺失时为 "unknown"
      "case_id_field": "case_id",        // 实际使用的键名
      "contract_keys": [{"key": ..., "spec": ..., "required": true}],
      "extra_top_level_keys": [...],     // case.json 其他顶层键（背景信息）
      "warnings": [...]
    }

退出码：0 = 契约可用；1 = 契约缺失或为空（仍可写作，但 result.json
        只能按通用键交付，warnings 中说明）；2 = 用法/IO 错误。
"""
import argparse
import json
import os
import sys

CASE_ID_CANDIDATES = ('case_id', 'caseId', 'id', 'case')
CONTRACT_CANDIDATES = ('output_contract', 'outputContract', 'contract',
                       'outputs', 'deliverables')


def find_case_id(data):
    for key in CASE_ID_CANDIDATES:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val, key
    return 'unknown', None


def find_contract(data):
    for key in CONTRACT_CANDIDATES:
        val = data.get(key)
        if isinstance(val, dict) and val:
            return key, val
    return None, {}


def classify_spec(spec):
    """尽力从契约描述中推断该键是否必需与期望形态。"""
    text = spec if isinstance(spec, str) else json.dumps(
        spec, ensure_ascii=False)
    lowered = text.lower()
    required = not any(w in lowered for w in ('optional', '可选', '如有'))
    kind = 'text'
    if any(w in lowered for w in ('json', '结构化', 'structured')):
        kind = 'json'
    elif any(w in lowered for w in ('markdown', 'md', '稿件', '报告',
                                    '清单', '表')):
        kind = 'markdown'
    return required, kind, text[:500]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case_json')
    ap.add_argument('out_contract_json')
    ap.add_argument('--task', default=None)
    args = ap.parse_args()

    with open(args.case_json, encoding='utf-8') as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        print('case.json 顶层不是对象', file=sys.stderr)
        return 2

    case_id, id_field = find_case_id(data)
    ckey, contract = find_contract(data)
    warnings = []
    keys = []
    for key, spec in contract.items():
        required, kind, text = classify_spec(spec)
        keys.append({'key': key, 'spec': text, 'required': required,
                     'expected_kind': kind})
    if not keys:
        warnings.append('未找到 output_contract；result.json 只能按通用键'
                        '（deliverable/sources/uncertainty/change_log/'
                        'limits/status）交付，并须在 limits 说明契约缺失。')
    if id_field is None:
        warnings.append('case.json 中未找到 case_id 字段；result.json 将'
                        '使用 "unknown" 并在 limits 记录。')
    if args.task and os.path.exists(args.task):
        with open(args.task, encoding='utf-8') as fh:
            task_text = fh.read()
        if len(task_text.strip()) < 10:
            warnings.append('task.md 内容过短，体裁/受众约束可能缺失。')

    out = {'case_id': case_id, 'case_id_field': id_field,
           'contract_field': ckey, 'contract_keys': keys,
           'extra_top_level_keys': sorted(
               k for k in data if k not in (ckey, id_field)),
           'warnings': warnings}
    with open(args.out_contract_json, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps({'case_id': case_id,
                      'contract_keys': [k['key'] for k in keys],
                      'warnings': warnings}, ensure_ascii=False))
    return 0 if keys else 1


if __name__ == '__main__':
    sys.exit(main())
