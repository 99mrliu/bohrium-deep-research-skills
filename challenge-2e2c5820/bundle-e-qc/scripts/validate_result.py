#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_result.py — 校验 result.json 是否满足 case.json 的输出契约（质控门 G1/G2 的机器部分）。

用法:
    python3 validate_result.py <case.json> <result.json>

检查项:
    1. result 为 JSON 对象；case_id 与 case.json 一致；
    2. 每个契约字段均存在；非 null 时 JSON 类型与期望一致（数组元素类型也校验）；
    3. status 取值属于 {complete, partial, failed}；
    4. status=partial/failed ⇒ uncertainty 必须为非空数组（诚实说明缺什么）；
    5. status=complete ⇒ 不允许任何契约字段为 null；
    6. sources / uncertainty / change_record 必须存在且为数组。

退出码: 0 通过；2 存在违规（逐项打印）；参数/文件错误同样以非零退出并打印消息。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_contract import find_contract, extract_fields, load_json  # noqa: E402

STATUS_VOCAB = ("complete", "partial", "failed")


def check_type(value, expected):
    if expected in (None, "any"):
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True  # 未知类型：不阻断，交由人工复核


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验 result.json 对 case.json 输出契约的符合性")
    ap.add_argument("case_json")
    ap.add_argument("result_json")
    args = ap.parse_args(argv)

    for p in (args.case_json, args.result_json):
        if not os.path.isfile(p):
            print("错误：文件不存在: %s" % p, file=sys.stderr)
            return 2

    case = load_json(args.case_json)
    contract, ckey = find_contract(case)
    if contract is None:
        print("错误：case.json 中未找到 output_contract", file=sys.stderr)
        return 2
    fields = extract_fields(contract)

    try:
        result = load_json(args.result_json)
    except Exception as e:  # noqa: BLE001
        print("违规：result.json 不是合法 JSON：%s" % e)
        return 2
    violations = []
    if not isinstance(result, dict):
        print("违规：result.json 顶层必须是 JSON 对象")
        return 2

    # 1) case_id 一致
    case_id = case.get("case_id") or case.get("id")
    if case_id is not None:
        if result.get("case_id") != case_id:
            violations.append("case_id 不一致：case.json=%r, result.json=%r"
                              % (case_id, result.get("case_id")))
    elif "case_id" not in result:
        violations.append("缺少 case_id 字段")

    # 2) 契约字段存在性与类型
    for fd in fields:
        name, t = fd["field"], fd["expected_type"]
        if name not in result:
            violations.append("缺少契约字段: %s（期望类型 %s）" % (name, t))
            continue
        v = result[name]
        if v is None:
            continue  # null 的合法性由状态规则（第 5 条）裁决
        if not check_type(v, t):
            violations.append("字段 %s 类型不符：期望 %s，实际 %s"
                              % (name, t, type(v).__name__))
        elif t == "array" and fd.get("items_type") not in (None, "any"):
            for i, el in enumerate(v):
                if not check_type(el, fd["items_type"]):
                    violations.append("字段 %s 第 %d 个元素类型不符：期望 %s，实际 %s"
                                      % (name, i, fd["items_type"], type(el).__name__))

    # 3) status 词表
    status = result.get("status")
    if status not in STATUS_VOCAB:
        violations.append("status 取值非法：%r（允许 %s）" % (status, "/".join(STATUS_VOCAB)))

    # 4) partial/failed ⇒ uncertainty 非空
    unc = result.get("uncertainty")
    if status in ("partial", "failed"):
        if not isinstance(unc, list) or not unc:
            violations.append("status=%s 但 uncertainty 为空：必须诚实说明缺口/限制" % status)

    # 5) complete ⇒ 无 null 契约字段
    if status == "complete":
        for fd in fields:
            if fd["field"] in result and result[fd["field"]] is None:
                violations.append("status=complete 但契约字段 %s 仍为 null" % fd["field"])

    # 6) 固定过程字段
    for name in ("sources", "uncertainty", "change_record"):
        if name not in result:
            violations.append("缺少固定字段: %s" % name)
        elif not isinstance(result[name], list):
            violations.append("固定字段 %s 必须是数组，实际 %s" % (name, type(result[name]).__name__))

    if violations:
        print("契约校验未通过，共 %d 项违规：" % len(violations))
        for i, v in enumerate(violations, 1):
            print("  违规[%d]: %s" % (i, v))
        return 2
    print("契约校验通过：%d 个契约字段齐全且类型匹配；case_id 一致；status=%s 规则满足。"
          % (len(fields), status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
