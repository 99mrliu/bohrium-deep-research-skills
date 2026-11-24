#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_lint — result.json vs case.json 契约强制（重心脚本 3）。

检查项（任一违例 exit 1，逐条打印违例码）：
  MISSING_FIELD             output_contract.required_fields 中的字段在 result.json 缺失或为 null
  INVALID_STATUS            status 不在枚举 (complete, partial, failed)
  CASE_ID_MISMATCH          result.case_id 与 case.json 不一致
  DANGLING_REFERENCE        interpretation/limitations/uncertainty/exceptions 中的 [HT:..]/[ES:..]/
                            [CI:..]/[SRC:..]/[STAGE:..]/[DEC-xxx] 引用不在 evidence_index 中
  PARTIAL_WITHOUT_EXCEPTIONS  status=partial 但 exceptions 为空（诚实 partial 结构要求）
  EXCEPTION_SHAPE           exceptions 条目缺 code/message
  SKELETON_SHIPPED          交付的仍是 _skeleton 骨架（未 finalize）

用法：python3 contract_lint.py [--case /input/case.json] [--result /app/output/result.json]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_e as st

REF_RE = re.compile(r"\[((?:HT|ES|CI|SRC|STAGE):[^\[\]]+|DEC-\d+)\]")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_strings(obj):
    out = []

    def rec(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(obj)
    return out


def main():
    ap = argparse.ArgumentParser(description="result.json 契约 lint")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--result", default="/app/output/result.json")
    args = ap.parse_args()
    violations = []

    if not os.path.isfile(args.case):
        violations.append("CASE_FILE_MISSING: %s" % args.case)
        case = {}
    else:
        case = load_json(args.case)
    if not os.path.isfile(args.result):
        print("RESULT_FILE_MISSING: %s" % args.result)
        return 1
    try:
        result = load_json(args.result)
    except json.JSONDecodeError as e:
        print("RESULT_UNPARSEABLE: %s" % e)
        return 1

    required = case.get("output_contract", {}).get("required_fields", [])
    for f in required:
        if f not in result or result[f] is None:
            violations.append("MISSING_FIELD: %s" % f)

    status = result.get("status")
    if status not in st.STATUS_ENUM:
        violations.append("INVALID_STATUS: %r 不在枚举 %s" % (status, list(st.STATUS_ENUM)))

    cid_case = case.get("case_id")
    cid_res = result.get("case_id")
    if cid_case is not None and cid_res != cid_case:
        violations.append("CASE_ID_MISMATCH: case.json=%r result.json=%r" % (cid_case, cid_res))

    if result.get("_skeleton"):
        violations.append("SKELETON_SHIPPED: 交付物仍是契约骨架（_skeleton=true），必须跑完 pipeline/finalize")

    if status == "partial":
        if not result.get("exceptions"):
            violations.append("PARTIAL_WITHOUT_EXCEPTIONS: status=partial 但 exceptions 为空（诚实 partial 要求记录原因）")
    for i, e in enumerate(result.get("exceptions", []) or []):
        if not isinstance(e, dict) or not e.get("code") or not e.get("message"):
            violations.append("EXCEPTION_SHAPE: exceptions[%d] 缺 code/message" % i)

    evidence = set(result.get("evidence_index", []) or [])
    scan_fields = {k: result.get(k) for k in
                   ("interpretation", "limitations", "uncertainty", "exceptions", "decisions")}
    for field, content in scan_fields.items():
        for s in collect_strings(content):
            for m in REF_RE.finditer(s):
                ref = m.group(1)
                if ref not in evidence:
                    violations.append("DANGLING_REFERENCE: %s 中的 [%s] 不在 evidence_index" % (field, ref))

    if violations:
        for v in violations:
            print(v)
        print("CONTRACT_LINT FAIL: %d 项违例" % len(violations))
        return 1
    print("CONTRACT_LINT PASS: %d 个契约字段齐全，status=%s，引用闭合" % (len(required), status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
