#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 先生成诚实的 result.json 骨架，再增量填充。

用法：
  python3 scaffold_result.py --case case.json --out DIR
      [--fill fill.json] [--status ok|partial|failed]

行为：
  - 防御式读取任意形状的 case.json（非 dict / 缺 output_contract 均可）；
  - 骨架镜像 output_contract 的全部字段：case_id 取 case.case_id，
    status 取 --status（默认 partial，诚实占位），sources/uncertainty/
    change_records 初始化为 []，其余字段填 null 并把字段名记入
    uncertainty（"字段未填充：X（占位 null）"）；
  - --fill 提供深合并填充：dict 递归合并，其余类型覆盖；
  - 每次运行向 change_records 追加一条记录；
  - 输出写到 DIR/result.json。

预算纪律：无论后续分析是否完成，先运行本脚本保证 /app/output/result.json
存在且诚实，再增量 --fill 改进。

退出码：0 正常；2 用法/输入错误。
"""
import argparse
import copy
import json
import os
import sys
import time

DEFAULT_FIELDS = ["case_id", "status", "sources", "uncertainty",
                  "change_records"]
LIST_FIELDS = {"sources", "uncertainty", "change_records"}


def _contract_fields(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        return [str(x) for x in contract]
    return list(DEFAULT_FIELDS)


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def deep_merge(base, fill):
    """dict 递归合并；list/标量以 fill 覆盖。两边非同型时以 fill 为准。"""
    if isinstance(base, dict) and isinstance(fill, dict):
        out = copy.deepcopy(base)
        for k, v in fill.items():
            out[k] = deep_merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(fill)


def build_skeleton(case, status):
    if not isinstance(case, dict):
        case = {"_raw_case": case}
    fields = _contract_fields(case)
    result = {}
    for f in fields:
        if f == "case_id":
            result[f] = case.get("case_id")
        elif f == "status":
            result[f] = status
        elif f in LIST_FIELDS:
            result[f] = []
        else:
            result[f] = None
    # 保证三个必备字段存在（即使 contract 未声明）
    for f in ("sources", "uncertainty", "change_records"):
        result.setdefault(f, [])
    result.setdefault("case_id", case.get("case_id"))
    result.setdefault("status", status)
    for f in fields:
        if result.get(f) is None:
            result["uncertainty"].append("字段未填充：%s（占位 null）" % f)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scaffold_result.py",
                                 description="result.json 骨架生成与增量填充")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True, help="输出目录（写 DIR/result.json）")
    ap.add_argument("--fill", default=None, help="深合并填充 JSON")
    ap.add_argument("--status", default="partial",
                    choices=["ok", "partial", "failed"])
    args = ap.parse_args(argv)

    if not os.path.exists(args.case):
        sys.stderr.write("case 文件不存在：%s\n" % args.case)
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("case 读取失败（%s），按空 case 防御性生成\n" % exc)
        case = {}

    result = build_skeleton(case, args.status)

    if args.fill:
        if not os.path.exists(args.fill):
            sys.stderr.write("fill 文件不存在：%s\n" % args.fill)
            return 2
        try:
            with open(args.fill, "r", encoding="utf-8") as fh:
                fill = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write("fill 读取失败：%s\n" % exc)
            return 2
        result = deep_merge(result, fill)
        result["change_records"].append({
            "ts": _utc_now(), "action": "fill",
            "note": "深合并填充自 %s" % args.fill})
    else:
        result["change_records"].append({
            "ts": _utc_now(), "action": "scaffold",
            "note": "生成镜像 output_contract 的诚实骨架，status=%s"
                    % args.status})

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    sys.stderr.write("已写出 %s（status=%s）\n" % (out_path, result["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
