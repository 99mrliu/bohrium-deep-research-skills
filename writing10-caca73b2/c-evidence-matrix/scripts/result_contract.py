#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_contract.py — result.json 契约骨架生成与校验（仅标准库，Python >= 3.9）。

子命令：
  init   读取 case.json，生成 result.json 骨架：case_id 原样照抄、
         output_contract 全部键就位、status="partial"、sources/uncertainty 就位。
  check  校验 result.json：JSON 可解析、case_id 与 case.json 一致、
         output_contract 全部键存在且非空或已说明、status 属于合法枚举。
         全部通过打印 PASS 并退出 0，否则打印 FAIL 并退出 1。

用法示例：
  python3 result_contract.py init  --case /input/case.json --out /app/output/result.json
  python3 result_contract.py check --case /input/case.json --result /app/output/result.json
"""
import argparse
import json
import sys

STATUS_ENUM = ("partial", "complete", "failed")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def contract_keys(case):
    """从 case.json 提取 output_contract 键名列表。兼容列表与字典两种形态。"""
    oc = case.get("output_contract")
    if oc is None:
        return []
    if isinstance(oc, dict):
        if isinstance(oc.get("keys"), (list, tuple)):
            return [str(k) for k in oc["keys"]]
        return [str(k) for k in oc.keys()]
    if isinstance(oc, (list, tuple)):
        return [str(k) for k in oc]
    return []


def is_nonempty(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return True


def cmd_init(args):
    try:
        case = load_json(args.case)
    except Exception as e:
        print("FAIL: 无法读取 case.json: %s" % e, file=sys.stderr)
        return 1
    if "case_id" not in case:
        print("FAIL: case.json 缺少 case_id", file=sys.stderr)
        return 1
    keys = contract_keys(case)
    if not keys:
        print("FAIL: case.json 缺少 output_contract 或其内容为空", file=sys.stderr)
        return 1
    result = {
        "case_id": case["case_id"],  # 原样照抄，不改写
        "status": "partial",
        "sources": [],
        "uncertainty": ["init 骨架：各交付键尚未填写，属诚实 partial"],
    }
    notes = {}
    for k in keys:
        result[k] = None
        notes[k] = "待填写（init 骨架）"
    result["_notes"] = notes
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("init OK: %s (case_id=%s, 契约键 %d 个: %s)"
          % (args.out, case["case_id"], len(keys), ", ".join(keys)))
    return 0


def cmd_check(args):
    lines = []
    errors = []
    try:
        result = load_json(args.result)
        lines.append("[OK] result.json 为合法 JSON")
    except Exception as e:
        print("[ERR] result.json 无法解析为 JSON: %s" % e)
        print("FAIL")
        return 1

    case = {}
    keys = []
    if args.case:
        try:
            case = load_json(args.case)
            keys = contract_keys(case)
            lines.append("[OK] case.json 可解析，契约键 %d 个" % len(keys))
        except Exception as e:
            errors.append("case.json 无法解析: %s" % e)

    # case_id 原样一致
    if "case_id" not in result:
        errors.append("result.json 缺少 case_id")
    elif args.case and result.get("case_id") != case.get("case_id"):
        errors.append("case_id 与 case.json 不一致: result=%r case=%r"
                      % (result.get("case_id"), case.get("case_id")))
    else:
        lines.append("[OK] case_id 一致: %s" % result.get("case_id"))

    # status 枚举
    if result.get("status") not in STATUS_ENUM:
        errors.append("status 非法: %r（允许值: %s）"
                      % (result.get("status"), "/".join(STATUS_ENUM)))
    else:
        lines.append("[OK] status 合法: %s" % result["status"])

    # sources / uncertainty 为列表
    for top in ("sources", "uncertainty"):
        if top not in result:
            errors.append("缺少顶层键: %s" % top)
        elif not isinstance(result[top], list):
            errors.append("%s 必须是列表，实际为 %s" % (top, type(result[top]).__name__))
        else:
            lines.append("[OK] %s 为列表（%d 条）" % (top, len(result[top])))

    # output_contract 全部键：存在且非空，或经 _notes 说明
    notes = result.get("_notes", {})
    if not isinstance(notes, dict):
        notes = {}
    missing, empty, explained = [], [], []
    for k in keys:
        if k not in result:
            missing.append(k)
        elif is_nonempty(result[k]):
            pass
        elif isinstance(notes.get(k), str) and notes[k].strip():
            explained.append(k)
        else:
            empty.append(k)
    if missing:
        errors.append("缺少契约键: %s" % ", ".join(missing))
    if empty:
        errors.append("契约键为空且未在 _notes 中说明: %s" % ", ".join(empty))
    if not missing and not empty:
        msg = "[OK] 契约键齐全且非空或已说明（%d/%d）" % (len(keys), len(keys))
        if explained:
            msg += "；其中经说明暂空: %s" % ", ".join(explained)
        lines.append(msg)

    for ln in lines:
        print(ln)
    for er in errors:
        print("[ERR] %s" % er)
    if errors:
        print("FAIL")
        return 1
    print("PASS")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="result.json 契约工具：init 生成骨架，check 校验完整性。")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="从 case.json 生成 result.json 骨架")
    pi.add_argument("--case", required=True, help="case.json 路径")
    pi.add_argument("--out", required=True, help="输出 result.json 路径")
    pi.set_defaults(func=cmd_init)

    pc = sub.add_parser("check", help="校验 result.json 是否满足契约")
    pc.add_argument("--case", required=True, help="case.json 路径（用于比对 case_id 与契约键）")
    pc.add_argument("--result", required=True, help="待校验的 result.json 路径")
    pc.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
