#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 诚实的 partial 骨架生成器（先落盘，再迭代）。

用法：
  python3 scaffold_result.py --case /input/case.json --out /app/output \
      [--fill fill.json] [--status partial|ok|failed]

行为：
  - 读取 case.json，提取 case_id（缺失时记 UNKNOWN 并写入 uncertainty 警告）；
  - 镜像 output_contract 的【全部字段】为 null 占位（支持 dict / 含
    properties 的 dict / 字符串列表三种形态；缺失 output_contract 时
    产出空镜像并在 uncertainty 中告警）——对任意 case.json 形态防御性工作；
  - 顶层写入权威字段：case_id / status（默认 partial）/ sources /
    uncertainty / change_records；
  - --fill 给定时，将 fill.json 深度合并进骨架（dict 递归合并，其余覆盖）；
  - --out 为目录时写入 <out>/result.json；以 .json 结尾时视为文件路径。

退出码：0 成功；2 用法/输入错误。仅使用 Python 标准库。
"""
import argparse
import datetime
import json
import os
import sys


def find_case_id(case):
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id"):
            if isinstance(case.get(k), str) and case[k]:
                return case[k]
        for v in case.values():  # 再向下一层防御性查找
            if isinstance(v, dict):
                for k in ("case_id", "caseId", "id"):
                    if isinstance(v.get(k), str) and v[k]:
                        return v[k]
    return None


def contract_fields(contract):
    if isinstance(contract, dict):
        props = contract.get("properties")
        if isinstance(props, dict):
            return list(props.keys())
        return list(contract.keys())
    if isinstance(contract, list):
        return [x for x in contract if isinstance(x, str)]
    return []


def deep_merge(base, fill):
    if isinstance(base, dict) and isinstance(fill, dict):
        out = dict(base)
        for k, v in fill.items():
            out[k] = deep_merge(base[k], v) if k in base else v
        return out
    return fill


def main(argv=None):
    p = argparse.ArgumentParser(
        description="从 case.json 生成镜像 output_contract 的 result.json 骨架。")
    p.add_argument("--case", required=True, metavar="CASE_JSON")
    p.add_argument("--out", required=True, metavar="OUT_DIR_OR_JSON")
    p.add_argument("--fill", default=None, metavar="FILL_JSON",
                   help="可选：深度合并进骨架的 JSON。")
    p.add_argument("--status", default="partial",
                   choices=["partial", "ok", "failed"])
    args = p.parse_args(argv)

    if not os.path.exists(args.case):
        print("错误：case 文件不存在: %s" % args.case, file=sys.stderr)
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：case.json 读取失败: %s" % e, file=sys.stderr)
        return 2

    uncertainty = []
    case_id = find_case_id(case)
    if case_id is None:
        case_id = "UNKNOWN_CASE_ID"
        uncertainty.append("case.json 中未找到 case_id，已以 UNKNOWN_CASE_ID 占位。")

    contract = case.get("output_contract") if isinstance(case, dict) else None
    if contract is None:
        mirror = {}
        uncertainty.append("case.json 缺少 output_contract，已生成空镜像；"
                           "请人工确认本 case 要求的输出字段。")
        print("警告：case.json 缺少 output_contract，生成空镜像。", file=sys.stderr)
    else:
        mirror = {k: None for k in contract_fields(contract)}

    ts = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    skeleton = dict(mirror)
    skeleton["case_id"] = case_id
    skeleton["status"] = args.status
    skeleton["sources"] = skeleton.get("sources") or []
    skeleton["uncertainty"] = (skeleton.get("uncertainty") or []) + uncertainty
    skeleton["change_records"] = [{
        "ts": ts,
        "action": "scaffold",
        "status": args.status,
        "note": "由 scaffold_result.py 生成的诚实骨架：先落盘 partial，再迭代改进。",
    }]

    if args.fill:
        if not os.path.exists(args.fill):
            print("错误：fill 文件不存在: %s" % args.fill, file=sys.stderr)
            return 2
        try:
            with open(args.fill, "r", encoding="utf-8") as f:
                fill = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("错误：fill JSON 读取失败: %s" % e, file=sys.stderr)
            return 2
        skeleton = deep_merge(skeleton, fill)
        skeleton["change_records"].append({
            "ts": ts, "action": "fill",
            "note": "深度合并 --fill %s。" % args.fill,
        })

    if args.out.endswith(".json"):
        out_path = args.out
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    else:
        os.makedirs(args.out, exist_ok=True)
        out_path = os.path.join(args.out, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("骨架已写入 %s（case_id=%s, status=%s, 契约镜像字段 %d 个）"
          % (out_path, case_id, args.status, len(mirror)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
