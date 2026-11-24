#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_validate.py — 输出契约校验（门禁 1/4）。

校验待检 result.json：
1. 含 case_id，且与 case.json 的 case_id 一致；
2. 含 case.json output_contract 列出的全部字段（缺字段即 fail 并逐个列出）；
3. 字段类型符合内置期望类型表（未知字段仅要求存在且非 null）；
4. 非空约束：字符串字段不得为空白串；容器字段允许为空但会记录 info；
5. status 字段（若在契约中）取值限于 complete/partial/failed。

用法：
    python3 contract_validate.py --case case.json --result result.json [--out report.json]

退出码：0=pass，2=warn，1=fail。仅标准库；永不访问网络。
"""
import argparse
import sys
from pathlib import Path

from qa_lib import QaError, check, dump_json, load_json, make_report

# 内置期望类型表：output_contract 中常见字段 → Python 类型。
# 契约中出现表外字段时，只校验"存在且非 null"。
EXPECTED_TYPES = {
    "case_id": str,
    "status": str,
    "window": dict,
    "new_items": list,
    "sources": list,
    "uncertainty": list,
    "change_records": list,
    "metrics": dict,
    "qa": dict,
    "qa_summary": dict,
    "result": dict,
}

_STATUS_VALUES = {"complete", "partial", "failed"}


def _is_blank(value):
    return isinstance(value, str) and not value.strip()


def validate(case, result):
    checks = []

    # 0. case.json 本身必须声明 output_contract
    contract = case.get("output_contract")
    if not isinstance(contract, list) or not contract:
        checks.append(check(
            "contract.declared", "fail",
            "case.json 缺少非空数组 output_contract，无法执行契约校验"))
        return checks
    checks.append(check(
        "contract.declared", "pass",
        f"case.json output_contract 共 {len(contract)} 个字段: {contract}"))

    # 1. case_id 强制存在且与 case 一致
    rid = result.get("case_id")
    cid = case.get("case_id")
    if rid is None or _is_blank(rid if isinstance(rid, str) else ""):
        checks.append(check("case_id.present", "fail", "result.json 缺少非空 case_id"))
    elif cid is not None and rid != cid:
        checks.append(check(
            "case_id.match", "fail",
            f"result.case_id={rid!r} 与 case.case_id={cid!r} 不一致"))
    else:
        checks.append(check("case_id.match", "pass", f"case_id 一致: {rid!r}"))

    # 2. 逐字段契约校验
    for field in contract:
        if field not in result:
            checks.append(check(
                f"field.{field}", "fail",
                f"缺失契约字段: {field!r}（output_contract 要求）"))
            continue
        value = result[field]
        if value is None:
            checks.append(check(f"field.{field}", "fail", f"契约字段 {field!r} 为 null"))
            continue
        if _is_blank(value):
            checks.append(check(
                f"field.{field}", "fail", f"契约字段 {field!r} 为空白字符串"))
            continue
        expected = EXPECTED_TYPES.get(field)
        if expected is not None and not isinstance(value, expected):
            checks.append(check(
                f"field.{field}", "fail",
                f"契约字段 {field!r} 类型错误: 期望 {expected.__name__}，"
                f"实际 {type(value).__name__}"))
            continue
        if field == "status" and isinstance(value, str) \
                and value not in _STATUS_VALUES:
            checks.append(check(
                f"field.{field}", "fail",
                f"status 取值 {value!r} 非法（限 {sorted(_STATUS_VALUES)}）"))
            continue
        if isinstance(value, (list, dict)) and len(value) == 0:
            checks.append(check(
                f"field.{field}", "pass",
                f"契约字段 {field!r} 存在但为空容器（合法，注意下游消费者）",
                severity="info"))
        else:
            checks.append(check(f"field.{field}", "pass", f"契约字段 {field!r} 合规"))

    # 3. 评测契约建议字段（sources / uncertainty / change_records）缺失时告警
    for field in ("sources", "uncertainty", "change_records"):
        if field not in contract and field not in result:
            checks.append(check(
                f"advisory.{field}", "warn",
                f"建议字段 {field!r} 既不在 output_contract 也不在 result.json 中"))

    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description="输出契约校验（tracking-qa-harness 门禁 1/4）")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--result", required=True, help="待检 result.json 路径")
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    try:
        case = load_json(args.case)
        result = load_json(args.result)
        checks = validate(case, result)
    except QaError as exc:
        checks = [check("tool.error", "fail", f"工具自身错误: {exc}")]

    report = make_report("contract_validate", checks)
    if args.out:
        dump_json(report, args.out)
    print(f"[contract_validate] status={report['status']} "
          f"errors={report['summary']['errors']} warnings={report['summary']['warnings']}")
    for c in checks:
        if c["status"] != "pass":
            print(f"  - [{c['status']}] {c['id']}: {c['message']}")
    return {"pass": 0, "warn": 2, "fail": 1}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
