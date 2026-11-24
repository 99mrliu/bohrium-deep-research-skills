#!/usr/bin/env python3
"""交付终验器：在提交前对 /app/output 做契约验收。

只依赖标准库。独立于组装过程再查一遍，模拟评审视角：result.json
是否合法、case_id 是否与 case.json 一致、契约键是否齐全、值是否
非空、result.json 中引用的文件是否真实存在、是否存在至少一个可编辑
交付物。

用法：
    python3 validate_output.py OUTPUT_DIR --case CASE_JSON [--report OUT_MD]

退出码：0 = 全部通过（允许 partial 但须 limits 非空）；
        1 = 存在 FAIL 项；2 = 用法/IO 错误。
"""
import argparse
import json
import os
import re
import sys

FILE_REF = re.compile(
    r'^(?:/app/output/)?[\w./ -]+\.(?:md|json|txt|csv|docx|pdf|png)$')


def iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for val in node.values():
            yield from iter_strings(val)
    elif isinstance(node, list):
        for item in node:
            yield from iter_strings(item)


def check(cond, item, detail, rows, fails):
    rows.append('| %s | %s | %s |' % (item, 'PASS' if cond else 'FAIL',
                                       detail.replace('|', '/')))
    if not cond:
        fails.append(item)
    return cond


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output_dir')
    ap.add_argument('--case', required=True)
    ap.add_argument('--report', default=None)
    args = ap.parse_args()

    rows = ['| 检查项 | 结果 | 说明 |', '|---|---|---|']
    fails = []

    result_path = os.path.join(args.output_dir, 'result.json')
    if not check(os.path.exists(result_path), 'result.json 存在',
                 result_path, rows, fails):
        result = None
    else:
        try:
            with open(result_path, encoding='utf-8') as fh:
                result = json.load(fh)
            check(True, 'result.json 可解析', 'JSON 合法', rows, fails)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            check(False, 'result.json 可解析', str(exc), rows, fails)
            result = None

    contract_keys, case_id = [], None
    with open(args.case, encoding='utf-8') as fh:
        case = json.load(fh)
    for key in ('output_contract', 'outputContract', 'contract'):
        if isinstance(case.get(key), dict):
            contract_keys = list(case[key])
            break
    for key in ('case_id', 'caseId', 'id'):
        if isinstance(case.get(key), str):
            case_id = case[key]
            break

    if result is not None:
        if case_id is not None:
            check(result.get('case_id') == case_id, 'case_id 一致',
                  'case.json=%r result.json=%r'
                  % (case_id, result.get('case_id')), rows, fails)
        for key in contract_keys:
            present = key in result
            check(present, '契约键存在: %s' % key,
                  '缺失' if not present else '存在', rows, fails)
            if present:
                val = result[key]
                empty = val is None or (isinstance(val, str)
                                        and not val.strip())
                check(not empty or result.get('status') != 'complete',
                      '契约键非空: %s' % key,
                      ('空值且 status!=complete，合规' if empty
                       else '非空') if (not empty
                                      or result.get('status')
                                      != 'complete')
                      else '空值但 status=complete', rows, fails)
        if result.get('status') == 'partial':
            limits = result.get('limits') or ''
            check(bool(str(limits).strip()), 'partial 有 limits 说明',
                  'status=partial 时 limits 必须非空', rows, fails)
        # 整值即路径的引用必须存在（字段值整体是一个文件路径时才视为
        # 引用；正文内容中提到的文件名不算引用）。sources（指向 /input
        # 原始材料）与 assembly（组装的元数据）不参与本检查。
        missing_refs = set()
        ref_strings = [s for key, val in result.items()
                       if key not in ('sources', 'assembly')
                       for s in iter_strings(val)]
        for text in ref_strings:
            candidate = text.strip()
            if not FILE_REF.match(candidate):
                continue
            rel = candidate[len('/app/output/'):] if candidate.startswith(
                '/app/output/') else candidate
            if not (os.path.exists(os.path.join(args.output_dir, rel))
                    or os.path.exists(candidate)):
                missing_refs.add(candidate)
        check(not missing_refs, '引用文件存在',
              '缺失: ' + ', '.join(sorted(missing_refs))
              if missing_refs else '全部存在', rows, fails)

    deliverables = [n for n in os.listdir(args.output_dir)
                    if os.path.splitext(n)[1] in
                    ('.md', '.docx', '.tex', '.json', '.csv')
                    and n != 'result.json'] \
        if os.path.isdir(args.output_dir) else []
    check(bool(deliverables), '存在可编辑交付物',
          ', '.join(deliverables[:8]) or '无', rows, fails)

    report = ['# 交付终验报告', ''] + rows + ['', '结论：%s。'
             % ('全部通过' if not fails else '存在 FAIL 项：' + '、'.join(
                 fails)), '']
    text = '\n'.join(report)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write(text)
    print(text)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
