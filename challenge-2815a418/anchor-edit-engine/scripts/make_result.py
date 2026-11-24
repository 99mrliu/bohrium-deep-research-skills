#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_result.py — 写出/更新 /app/output/result.json。

保证：
  - case_id 从 case.json 原样复制（绝不改写）；
  - output_contract 的全部字段都作为顶层键出现（--artifact 字段=路径 填值，
    未提供的字段置 null 并在 uncertainty 中说明，诚实 partial）；
  - sources / uncertainty / notes 累积去重；
  - change_records 从 changes.json 读入；
  - 重复执行时保留已有字段，只覆盖本次显式给出的项。

用法（prepare，先落合法的部分 result）：
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --status partial --uncertainty "初始化：意见尚未处理"
用法（finish）：
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --status success \
      --artifact revised_manuscript=/app/output/revised-manuscript.md \
      --artifact response_letter=/app/output/response-letter.md \
      --source materials/reviewer-comments.md \
      --uncertainty "R2.1 置信区间因缺原始数据未补算" \
      --changes /app/output/changes.json
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import sys


def dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser(description="result.json 写出/更新")
    ap.add_argument("--case", help="case.json 路径（取 case_id 与 output_contract）")
    ap.add_argument("--case-id", help="无 case.json 时手工指定 case_id")
    ap.add_argument("--contract", help="无 case.json 时逗号分隔的 contract 字段名")
    ap.add_argument("--out", required=True, help="result.json 路径")
    ap.add_argument("--status", choices=["success", "partial", "failed"])
    ap.add_argument("--source", action="append", default=[], help="来源，可重复")
    ap.add_argument("--uncertainty", action="append", default=[], help="不确定项，可重复")
    ap.add_argument("--note", action="append", default=[], help="备注，可重复")
    ap.add_argument("--artifact", action="append", default=[],
                    help="字段=路径，可重复；字段名应对应 output_contract")
    ap.add_argument("--changes", help="changes.json 路径，读入 change_records")
    args = ap.parse_args()

    case_id = args.case_id
    contract_keys = []
    if args.case:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        case_id = case.get("case_id", case_id)
        oc = case.get("output_contract", {})
        if isinstance(oc, dict):
            contract_keys = list(oc.keys())
        elif isinstance(oc, list):
            contract_keys = [str(k) for k in oc]
    if args.contract:
        contract_keys = dedup(contract_keys +
                              [k.strip() for k in args.contract.split(",") if k.strip()])

    result = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            result = {}

    if case_id is not None:
        result["case_id"] = case_id  # 原样复制
    if args.status:
        result["status"] = args.status

    artifacts = {}
    for item in args.artifact:
        if "=" not in item:
            print("警告：忽略非法 --artifact 项 %r（应为 字段=路径）" % item,
                  file=sys.stderr)
            continue
        k, v = item.split("=", 1)
        artifacts[k.strip()] = v.strip()

    for k in contract_keys:
        if k in artifacts:
            result[k] = artifacts[k]
        else:
            result.setdefault(k, None)
    for k, v in artifacts.items():
        result[k] = v

    # 产物路径存在性检查（只警告，不阻断）
    existence_warnings = []
    for k in contract_keys:
        v = result.get(k)
        if v and not os.path.exists(v):
            existence_warnings.append("字段 %s 指向的路径不存在: %s" % (k, v))

    result["sources"] = dedup(result.get("sources", []) + args.source)
    # 先剔除历史运行留下的"字段未提供"消息，再按当前状态重算，避免过期声明
    stale = [u for u in result.get("uncertainty", [])
             if not u.startswith("output_contract 字段未提供产物")]
    result["uncertainty"] = dedup(stale + args.uncertainty + existence_warnings)
    result["notes"] = dedup(result.get("notes", []) + args.note)

    if args.changes:
        with open(args.changes, "r", encoding="utf-8") as f:
            result["change_records"] = json.load(f)

    missing = [k for k in contract_keys if not result.get(k)]
    if missing:
        msg = "output_contract 字段未提供产物（诚实声明）: %s" % ", ".join(missing)
        result["uncertainty"].append(msg)
        if result.get("status") == "success":
            print("警告：status=success 但 contract 字段缺失: %s" % ", ".join(missing),
                  file=sys.stderr)

    outdir = os.path.dirname(os.path.abspath(args.out))
    if outdir and not os.path.isdir(outdir):
        os.makedirs(outdir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("result.json 已写出: %s（status=%s, contract 字段 %d 个, 缺失 %d 个）"
          % (args.out, result.get("status"), len(contract_keys), len(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
