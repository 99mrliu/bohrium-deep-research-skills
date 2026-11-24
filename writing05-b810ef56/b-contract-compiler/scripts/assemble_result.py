#!/usr/bin/env python3
"""result.json 组装器：从部件目录确定性组装契约完备的 result.json。

只依赖标准库。原则：只组装真实存在的部件，绝不凭空生成内容；
契约键缺件时强制 status=partial 并在 missing 字段逐项列出。

用法：
    python3 assemble_result.py CONTRACT_JSON PARTS_DIR OUT_RESULT_JSON

CONTRACT_JSON   contract_inspect.py 的输出
PARTS_DIR       部件目录，命名约定：
                  <contract_key>.md / .json / .txt  -> 对应契约键
                  status.txt        complete|partial|failed（单行）
                  uncertainty.md    不确定性说明
                  change_log.md     修改记录
                  limits.md         边界与缺口
                  sources.json      来源清单（数组或对象）
                缺少 status.txt 时按缺件情况自动判定。
OUT_RESULT_JSON 输出路径（通常 /app/output/result.json）

部件值为文件内容（.json 部件解析为对象，其余为字符串）。契约键没有
对应部件文件时填入 null 并记入 missing；required 键缺件会把
complete 降级为 partial。

退出码：0 = 组装完成（含 partial）；2 = 用法/IO 错误。
"""
import argparse
import json
import os
import sys

RESERVED = {'status.txt', 'uncertainty.md', 'change_log.md',
            'limits.md', 'sources.json'}


def read_part(path):
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    if path.endswith('.json'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('contract_json')
    ap.add_argument('parts_dir')
    ap.add_argument('out_result_json')
    args = ap.parse_args()

    with open(args.contract_json, encoding='utf-8') as fh:
        contract = json.load(fh)

    parts = {}
    if os.path.isdir(args.parts_dir):
        for name in sorted(os.listdir(args.parts_dir)):
            path = os.path.join(args.parts_dir, name)
            if os.path.isfile(path) and not name.startswith('.'):
                parts[name] = read_part(path)

    result = {'case_id': contract['case_id']}
    missing = []
    for spec in contract['contract_keys']:
        key = spec['key']
        value, found = None, False
        for ext in ('.json', '.md', '.txt'):
            name = key + ext
            if name in parts:
                value, found = parts[name], True
                break
        if not found:
            missing.append({'key': key, 'required': spec['required']})
        result[key] = value

    for meta, name in (('uncertainty', 'uncertainty.md'),
                       ('change_log', 'change_log.md'),
                       ('limits', 'limits.md'),
                       ('sources', 'sources.json')):
        if name in parts:
            result[meta] = parts[name]

    hard_missing = [m['key'] for m in missing if m['required']]
    declared = parts.get('status.txt', '').strip().lower()
    if declared not in ('complete', 'partial', 'failed'):
        declared = 'partial' if (missing or not parts) else 'complete'
    if hard_missing and declared == 'complete':
        declared = 'partial'
    result['status'] = declared
    result['missing'] = missing
    result['assembly'] = {
        'contract_field': contract.get('contract_field'),
        'parts_used': sorted(parts),
        'note': '由 assemble_result.py 确定性组装；null 值表示该契约键'
                '无对应部件文件，非内容省略。'}

    with open(args.out_result_json, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps({'status': declared,
                      'missing': missing,
                      'keys': sorted(result)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
