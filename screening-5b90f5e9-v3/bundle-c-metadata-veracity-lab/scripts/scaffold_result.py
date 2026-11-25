#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 尽早落 result.json 骨架

运行时合同要求"尽早落骨架"：读取 case.json，取出 case_id 与
output_contract 的全部字段名，写出 /app/output/result.json：
  * case_id 必填；合同字段一律先填 null
  * status="partial"，附 uncertainty 说明骨架待填充
  * 自带 sources / uncertainty / change_records 三个基础键

幂等与保守：result.json 已存在时只做"增量补键"，绝不覆盖已有非 null 值；
--force 才整体重建。

退出码：0 成功；2 运行/IO 错误（case.json 不存在/不可解析）；
3 合同不满足（缺 case_id 或 output_contract）。
"""
import argparse
import json
import os
import sys

BASE_KEYS = ("case_id", "status", "sources", "uncertainty", "change_records")


def contract_fields(contract):
    """从 output_contract 提取字段名；兼容 dict / list / 嵌套 fields。"""
    if isinstance(contract, dict):
        for key in ("required_fields", "fields"):
            if isinstance(contract.get(key), list):
                items = contract[key]
                return [it["name"] if isinstance(it, dict) and "name" in it
                        else str(it) for it in items]
        return [str(k) for k in contract]
    if isinstance(contract, list):
        return [it["name"] if isinstance(it, dict) and "name" in it
                else str(it) for it in contract]
    return []


def scaffold(case_path, output_dir, force=False):
    with open(case_path, "r", encoding="utf-8") as fh:
        case = json.load(fh)
    case_id = case.get("case_id")
    contract = case.get("output_contract")
    if not case_id:
        print("ERROR: case.json 缺 case_id（合同不满足）", file=sys.stderr)
        return 3
    if contract is None:
        print("ERROR: case.json 缺 output_contract（合同不满足）",
              file=sys.stderr)
        return 3
    fields = contract_fields(contract)
    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, "result.json")

    if os.path.exists(result_path) and not force:
        # 增量补键：保留已有非 null 值
        with open(result_path, "r", encoding="utf-8") as fh:
            result = json.load(fh)
        added = []
        if "case_id" not in result:
            result["case_id"] = case_id
            added.append("case_id")
        for key in ("sources", "uncertainty", "change_records"):
            result.setdefault(key, [])
        result.setdefault("status", "partial")
        for field in fields:
            if field not in result:
                result[field] = None
                added.append(field)
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        print("OK: result.json 已存在，增量补键 %s（未覆盖已有值）"
              % (added or "无"))
        return 0

    result = {
        "case_id": case_id,
        "status": "partial",
        "sources": [],
        "uncertainty": ["result.json 骨架已建立；合同字段暂为 null，"
                        "待 metadata-veracity-lab 流程逐步回填。"],
        "change_records": [],
    }
    for field in fields:
        if field not in result:
            result[field] = None
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("OK: 骨架已落盘 %s；case_id=%s；合同字段 %d 个 -> %s"
          % (result_path, case_id, len(fields), fields))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="尽早落 result.json 骨架")
    parser.add_argument("--case", default="/input/case.json",
                        help="case.json 路径，默认 /input/case.json")
    parser.add_argument("--output", default="/app/output", help="交付目录")
    parser.add_argument("--force", action="store_true",
                        help="整体重建骨架（默认增量补键）")
    args = parser.parse_args(argv)
    try:
        return scaffold(args.case, args.output, force=args.force)
    except FileNotFoundError as exc:
        print("ERROR: case.json 不存在: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # 顶层兜底
        print("ERROR: 未预期异常: %r" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
