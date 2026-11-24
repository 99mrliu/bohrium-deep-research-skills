#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_validate.py — 交付前机器校验（bundle E / contract-forge-audit）。

依据 contract_scaffold.py 生成的 contract_schema.json 校验成品 result.json：
  * 每个 required 字段存在且不是 "PENDING::<field>" 哨兵；
    例外：status 为 partial/failed 且该字段在 pending_reasons 中给出非空人工理由；
  * 字段类型符合契约声明（string/array/object/number/integer/boolean/any，可用 | 并列）；
  * case_id 与 schema（及可选 case.json）一致；
  * status ∈ {complete, partial, failed}；
  * status=complete 时必须零 pending（且无残留哨兵、pending_reasons 为空）；
  * 声明了 item_required_keys 的 findings 数组逐条检查必备键。

输出 validation_report.json；存在违例时以非零码退出。
仅依赖 Python 标准库。
"""
import argparse
import json
import os
import sys

VALID_STATUS = ("complete", "partial", "failed")
TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "any": lambda v: True,
}


def load_json(path, what):
    if not os.path.isfile(path):
        print("contract_validate: ERROR: %s 不存在: %s" % (what, path), file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print("contract_validate: ERROR: %s 读取/解析失败: %s (%s)" % (what, path, e),
              file=sys.stderr)
        sys.exit(2)


def is_pending(value, field):
    return isinstance(value, str) and (
        value.startswith("PENDING::") or value == "PENDING::%s" % field)


def type_ok(value, declared):
    for t in str(declared).split("|"):
        check = TYPE_CHECKS.get(t.strip().lower())
        if check is not None and check(value):
            return True
    return False


def validate(result, schema, case=None):
    violations = []
    warnings = []
    fields = schema.get("fields", {}) or {}
    pending_reasons = result.get("pending_reasons")
    if pending_reasons is None:
        pending_reasons = {}
    if not isinstance(pending_reasons, dict):
        violations.append("pending_reasons 必须是对象 {字段名: 人工理由}")
        pending_reasons = {}

    # case_id
    schema_case_id = schema.get("case_id")
    rid = result.get("case_id")
    if schema_case_id and schema_case_id != "UNKNOWN_CASE_ID" and rid != schema_case_id:
        violations.append("case_id 不匹配: result=%r, 契约=%r" % (rid, schema_case_id))
    if case is not None:
        cid = case.get("case_id") or case.get("caseId") or case.get("id")
        if cid and rid != cid:
            violations.append("case_id 与 case.json 不一致: result=%r, case=%r" % (rid, cid))

    # status
    status = result.get("status")
    if status not in VALID_STATUS:
        violations.append("status 必须是 complete/partial/failed 之一，实际为 %r" % (status,))

    pending_fields = []
    # 契约字段
    for name, spec in fields.items():
        required = spec.get("required", True)
        if name not in result:
            if required:
                violations.append("缺少 required 字段: %s" % name)
            continue
        value = result[name]
        if is_pending(value, name):
            reason = pending_reasons.get(name)
            if status in ("partial", "failed") and isinstance(reason, str) and reason.strip():
                pending_fields.append(name)
                warnings.append("字段 %s 仍为 PENDING，已登记理由: %s" % (name, reason))
            else:
                violations.append(
                    "字段 %s 仍是 PENDING 哨兵；仅当 status=partial/failed 且在 "
                    "pending_reasons 中登记非空理由时才允许。" % name)
            continue
        if not type_ok(value, spec.get("type", "any")):
            violations.append("字段 %s 类型不符: 声明 %r，实际 %s"
                              % (name, spec.get("type"), type(value).__name__))
            continue
        # findings 数组逐条键检查
        item_keys = spec.get("item_required_keys")
        if item_keys and isinstance(value, list):
            for i, item in enumerate(value):
                if not isinstance(item, dict):
                    violations.append("字段 %s 第 %d 项不是对象" % (name, i))
                    continue
                for k in item_keys:
                    if k not in item:
                        violations.append("字段 %s 第 %d 项缺少必备键 %r" % (name, i, k))

    # 非契约字段中的残留哨兵（status/pending_reasons 除外）
    for name, value in result.items():
        if name in fields or name in ("status", "pending_reasons"):
            continue
        if isinstance(value, str) and value.startswith("PENDING::"):
            pending_fields.append(name)
            if status == "complete":
                violations.append("status=complete 但字段 %s 仍为 PENDING 哨兵" % name)

    if status == "complete":
        if pending_fields:
            violations.append("status=complete 但仍有 pending 字段: %s"
                              % ", ".join(sorted(set(pending_fields))))
        if pending_reasons:
            violations.append("status=complete 时 pending_reasons 必须为空，实际: %s"
                              % ", ".join(sorted(pending_reasons)))
    else:
        for name in pending_reasons:
            if name not in result:
                warnings.append("pending_reasons 中的字段 %s 在 result.json 中不存在" % name)

    return violations, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按 contract_schema.json 校验 result.json；违例时输出报告并以非零码退出。")
    ap.add_argument("--result", default="result.json", help="result.json 路径")
    ap.add_argument("--schema", default="contract_schema.json",
                    help="contract_schema.json 路径")
    ap.add_argument("--case", default=None,
                    help="可选：原始 case.json，用于交叉核对 case_id")
    ap.add_argument("--report", default="validation_report.json",
                    help="校验报告输出路径（默认 validation_report.json）")
    args = ap.parse_args(argv)

    result = load_json(args.result, "result.json")
    schema = load_json(args.schema, "contract_schema.json")
    if not isinstance(result, dict):
        print("contract_validate: ERROR: result.json 顶层必须是 JSON 对象", file=sys.stderr)
        sys.exit(2)
    case = load_json(args.case, "case.json") if args.case else None

    violations, warnings = validate(result, schema, case)
    report = {
        "tool": "contract-forge-audit/contract_validate.py",
        "result_file": os.path.abspath(args.result),
        "schema_file": os.path.abspath(args.schema),
        "case_id": result.get("case_id"),
        "status": result.get("status"),
        "schema_fallback": bool(schema.get("fallback")),
        "ok": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "warnings": warnings,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for w in warnings:
        print("contract_validate: WARNING: %s" % w, file=sys.stderr)
    if violations:
        for v in violations:
            print("contract_validate: VIOLATION: %s" % v, file=sys.stderr)
        print("contract_validate: FAILED (%d 项违例)，报告见 %s"
              % (len(violations), args.report), file=sys.stderr)
        return 1
    print("contract_validate: OK (0 项违例, %d 条警告)，报告见 %s"
          % (len(warnings), args.report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
