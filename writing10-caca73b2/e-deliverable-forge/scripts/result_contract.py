#!/usr/bin/env python3
"""result_contract.py — 初始化并校验 result.json 是否满足 case.json 的 output_contract。

用法:
    python3 result_contract.py init  --case-json case.json --out result.json
    python3 result_contract.py check --case-json case.json --result result.json

约定:
  * case_id 原样照抄(逐字节一致)。
  * result.json 必须包含 output_contract 声明的全部键(值为 null 视为未填写)。
  * status 取值集合: success / partial / fail。
  * 另需诚实字段: sources (list) 与 uncertainty (string)。
  * check 子命令打印 PASS/FAIL 及逐项明细, 以退出码 0/1 表示。

仅使用 Python 标准库, 兼容 Python >= 3.9。
"""

import argparse
import json
import sys

STATUS_ENUM = ("success", "partial", "fail")
EXTRA_KEYS = ("status", "sources", "uncertainty")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.stderr.write("ERROR: file not found: %s\n" % path)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write("ERROR: invalid JSON in %s: %s\n" % (path, exc))
        sys.exit(2)


def contract_keys(case):
    """从 case.json 提取 output_contract 的键名列表。

    支持两种形态:
      * list[str]                      —— 直接为键名列表;
      * dict[str, str|dict]            —— 键为键名, 值为说明。
    """
    contract = case.get("output_contract")
    if contract is None:
        return []
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        return [str(k) for k in contract]
    sys.stderr.write("ERROR: output_contract must be a list or an object\n")
    sys.exit(2)


def cmd_init(args):
    case = load_json(args.case_json)
    case_id = case.get("case_id")
    if case_id is None:
        sys.stderr.write("ERROR: case.json has no case_id\n")
        sys.exit(2)
    keys = contract_keys(case)
    result = {"case_id": case_id}
    for key in keys:
        result[key] = None
    result["status"] = "fail"
    result["sources"] = []
    result["uncertainty"] = ""
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stdout.write(
        "init OK: wrote %s with case_id=%r and %d contract key(s): %s\n"
        % (args.out, case_id, len(keys), ", ".join(keys) if keys else "(none)")
    )
    return 0


def cmd_check(args):
    case = load_json(args.case_json)
    result = load_json(args.result)
    problems = []

    case_id = case.get("case_id")
    if result.get("case_id") != case_id:
        problems.append(
            "case_id mismatch: result has %r, case.json has %r (must be verbatim)"
            % (result.get("case_id"), case_id)
        )

    keys = contract_keys(case)
    for key in keys:
        if key not in result:
            problems.append("missing output_contract key: %s" % key)

    status = result.get("status")
    if status not in STATUS_ENUM:
        problems.append(
            "status must be one of %s, got %r" % ("/".join(STATUS_ENUM), status)
        )

    if not isinstance(result.get("sources"), list):
        problems.append("sources must be a list (may be empty, but must exist)")
    if not isinstance(result.get("uncertainty"), str):
        problems.append("uncertainty must be a string (may be empty, but must exist)")

    if problems:
        sys.stdout.write("FAIL\n")
        for item in problems:
            sys.stdout.write("  - %s\n" % item)
        return 1
    sys.stdout.write(
        "PASS: case_id verbatim; %d contract key(s) present; status=%s; "
        "sources/uncertainty present.\n" % (len(keys), status)
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="初始化并校验 result.json 是否满足 case.json 的 output_contract。"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="按 case.json 生成 result.json 骨架")
    p_init.add_argument("--case-json", required=True, help="case.json 路径")
    p_init.add_argument("--out", required=True, help="输出的 result.json 路径")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="校验 result.json 是否满足契约")
    p_check.add_argument("--case-json", required=True, help="case.json 路径")
    p_check.add_argument("--result", required=True, help="待校验的 result.json 路径")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
