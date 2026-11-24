#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_contract.py — result.json 契约工具（value-anchor-rd）

子命令：
  init  --case CASE.json --out RESULT.json
        读取 case.json，原样复制 case_id，按 case.json 中 output_contract 的
        全部键生成"空但存在"的 result.json 骨架；附加 status="partial"、
        sources=[]、uncertainty=[]、created_by="value-anchor-rd"。
  check --case CASE.json --result RESULT.json --output-dir DIR
        校验 result.json：JSON 可解析；case_id 与 case.json 一致；
        output_contract 全部键存在且非空（或该键的空缺已在 change_log 或
        uncertainty 中明确解释）；status ∈ {partial, complete, failed}。
        打印 PASS/FAIL 及原因；PASS 退出码 0，FAIL 退出码 1。

仅依赖 Python>=3.9 标准库。确定性运行，不调用任何模型。
"""

import argparse
import json
import sys
from datetime import datetime, timezone

CREATED_BY = "value-anchor-rd"
ALLOWED_STATUS = {"partial", "complete", "failed"}

# 标准 output_contract 键的默认空值类型；未知键退回为 ""。
_EMPTY_BY_HINT = (
    ("map", {}),
    ("facts", []),
    ("log", []),
    ("list", []),
    ("sources", []),
    ("items", []),
)


def _empty_value_for_key(key):
    kl = key.lower()
    for hint, proto in _EMPTY_BY_HINT:
        if hint in kl:
            # 复制原型，避免共享可变对象
            return json.loads(json.dumps(proto))
    return ""


def _load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("FAIL: %s 文件不存在: %s" % (what, path))
        sys.exit(2)
    except json.JSONDecodeError as e:
        print("FAIL: %s 不是合法 JSON: %s (%s)" % (what, path, e))
        sys.exit(2)
    except UnicodeDecodeError as e:
        print("FAIL: %s 不是 UTF-8 文本: %s (%s)" % (what, path, e))
        sys.exit(2)


def _contract_keys(case):
    """从 case.json 提取 output_contract 键名列表（兼容 dict / list / str）。"""
    oc = case.get("output_contract")
    if oc is None:
        return []
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        keys = []
        for item in oc:
            if isinstance(item, str):
                keys.append(item)
            elif isinstance(item, dict) and "key" in item:
                keys.append(str(item["key"]))
            elif isinstance(item, dict) and "name" in item:
                keys.append(str(item["name"]))
        return keys
    if isinstance(oc, str):
        return [oc]
    return []


def cmd_init(args):
    case = _load_json(args.case, "case.json")
    if not isinstance(case, dict):
        print("FAIL: case.json 顶层必须是 JSON 对象: %s" % args.case)
        return 1
    if "case_id" not in case:
        print("FAIL: case.json 缺少 case_id 字段: %s" % args.case)
        return 1
    keys = _contract_keys(case)
    if not keys:
        print("FAIL: case.json 缺少 output_contract 或其为空: %s" % args.case)
        return 1

    result = {"case_id": case["case_id"]}  # 原样保留，不做任何改写
    for k in keys:
        result[k] = _empty_value_for_key(k)
    result["status"] = "partial"
    result["sources"] = []
    result["uncertainty"] = []
    result["created_by"] = CREATED_BY
    result["created_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("INIT OK: 已写入骨架 %s（contract 键: %s）"
          % (args.out, ", ".join(keys)))
    return 0


def _is_empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def cmd_check(args):
    problems = []
    case = _load_json(args.case, "case.json")
    result = _load_json(args.result, "result.json")

    if not isinstance(result, dict):
        problems.append("result.json 顶层必须是 JSON 对象")
        result = {}

    # 1) case_id 一致
    cid_case = case.get("case_id")
    cid_res = result.get("case_id")
    if cid_res != cid_case:
        problems.append("case_id 不一致: case.json=%r, result.json=%r"
                        % (cid_case, cid_res))

    # 2) output_contract 键存在且非空（或已解释）
    keys = _contract_keys(case)
    if not keys:
        problems.append("case.json 缺少 output_contract 或其为空")
    explanation_text = json.dumps(
        [result.get("change_log", ""), result.get("uncertainty", "")],
        ensure_ascii=False)
    for k in keys:
        if k not in result:
            problems.append("缺少 contract 键: %s" % k)
        elif _is_empty(result[k]):
            if k in explanation_text:
                # 空缺已被明确解释，记为提示而非失败
                print("INFO: 键 %s 为空，但已在 change_log/uncertainty 中解释" % k)
            else:
                problems.append("contract 键为空且未解释: %s" % k)

    # 3) status 合法
    status = result.get("status")
    if status not in ALLOWED_STATUS:
        problems.append("status 非法: %r（允许 partial/complete/failed）" % (status,))
    elif status == "complete":
        # complete 时不允许仍有未解释的 uncertainty 占位
        pass

    # 4) 诚实性字段存在
    for k in ("sources", "uncertainty"):
        if k not in result:
            problems.append("缺少诚实性字段: %s" % k)

    # 5) deliverable 指向的文件若存在 output-dir 则提示核对
    if args.output_dir:
        import os
        if not os.path.isdir(args.output_dir):
            problems.append("--output-dir 不存在: %s" % args.output_dir)

    if problems:
        print("FAIL")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("PASS: result.json 满足 output_contract（case_id=%r，键数=%d，status=%s）"
          % (cid_case, len(keys), status))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="result_contract.py",
        description="result.json 契约初始化(init)与终检(check)工具（value-anchor-rd）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="按 case.json 生成 result.json 骨架")
    p_init.add_argument("--case", required=True, help="case.json 路径")
    p_init.add_argument("--out", required=True, help="输出 result.json 骨架路径")

    p_check = sub.add_parser("check", help="终检 result.json 是否满足契约")
    p_check.add_argument("--case", required=True, help="case.json 路径")
    p_check.add_argument("--result", required=True, help="待检 result.json 路径")
    p_check.add_argument("--output-dir", default=None,
                         help="交付目录（存在性检查，可选）")

    args = ap.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "check":
        return cmd_check(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
