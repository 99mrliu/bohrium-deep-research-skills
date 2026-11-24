#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_contract.py — result.json 契约脚手架与校验器（仅标准库）。

子命令：
  init   读取 case.json，写出 result.json 骨架：case_id 原样 + output_contract
         全部键 + status="partial" + sources/uncertainty。占位值用于尽早落盘
         诚实部分结果；占位/空值无法通过 check。
  check  校验 result.json：可解析、case_id 与 output_contract 全部键在位且非空、
         status 枚举合法、sources/uncertainty 在位。打印 PASS/FAIL，退出码 0/1。
"""
import argparse
import json
import sys

STATUS_ENUM = ("success", "partial", "failed")
TODO_PREFIX = "TODO"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        print("错误：无法读取 %s：%s" % (path, e), file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print("错误：%s 不是合法 JSON：%s" % (path, e), file=sys.stderr)
        sys.exit(2)


def contract_keys(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(k) for k in oc]
    return []


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return (not value.strip()) or value.strip().startswith(TODO_PREFIX)
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def cmd_init(args):
    case = load_json(args.case)
    case_id = case.get("case_id")
    if not case_id:
        print("错误：case.json 缺少 case_id", file=sys.stderr)
        return 2
    keys = contract_keys(case)
    if not keys:
        print("错误：case.json 缺少 output_contract 或其为空", file=sys.stderr)
        return 2
    skeleton = {"case_id": case_id}
    for k in keys:
        if k == "status":
            continue  # status 由本工具统一维护
        if k in ("preserved_facts", "change_log", "sources"):
            skeleton[k] = []
        elif k == "evidence_map":
            skeleton[k] = {}
        else:
            skeleton[k] = "%s: 待填写（%s）" % (TODO_PREFIX, k)
    skeleton["status"] = "partial"
    skeleton.setdefault("sources", [])
    skeleton["uncertainty"] = "%s: 待填写" % TODO_PREFIX
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print("错误：无法写入 %s：%s" % (args.out, e), file=sys.stderr)
        return 2
    print("已写出 result.json 骨架：%s（status=partial；占位值需填写后方可通过 check）" % args.out)
    print("契约键：%s" % ", ".join(keys))
    return 0


def cmd_check(args):
    case = load_json(args.case)
    result = load_json(args.result)
    problems = []

    case_id = case.get("case_id")
    if result.get("case_id") != case_id:
        problems.append("case_id 缺失或与 case.json 不一致（期望 %r，实际 %r）"
                        % (case_id, result.get("case_id")))

    for k in contract_keys(case):
        if k not in result:
            problems.append("缺少契约键：%s" % k)
        elif is_empty(result[k]):
            problems.append("契约键为空或仍为占位值：%s" % k)

    status = result.get("status")
    if status not in STATUS_ENUM:
        problems.append("status 非法：%r（允许：%s）" % (status, "/".join(STATUS_ENUM)))

    if "sources" not in result:
        problems.append("缺少 sources 键")
    elif not isinstance(result["sources"], list):
        problems.append("sources 应为列表")
    if is_empty(result.get("uncertainty")):
        problems.append("uncertainty 缺失、为空或仍为占位值")

    for p in problems:
        print("[FAIL] %s" % p)
    if not problems:
        print("[OK] case_id 一致；output_contract 全部 %d 键在位且非空；status=%s；sources/uncertainty 在位"
              % (len(contract_keys(case)), status))
    verdict = "FAIL" if problems else "PASS"
    print(verdict)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 契约脚手架与校验器。")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="从 case.json 生成 result.json 骨架")
    p_init.add_argument("--case", required=True, help="case.json 路径")
    p_init.add_argument("--out", required=True, help="result.json 输出路径")
    p_init.set_defaults(func=cmd_init)
    p_check = sub.add_parser("check", help="校验 result.json 是否满足契约")
    p_check.add_argument("--case", required=True, help="case.json 路径")
    p_check.add_argument("--result", required=True, help="result.json 路径")
    p_check.set_defaults(func=cmd_check)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
