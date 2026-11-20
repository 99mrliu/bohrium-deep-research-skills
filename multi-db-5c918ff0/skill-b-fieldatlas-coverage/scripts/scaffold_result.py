#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 从 case_summary.json 的 output_contract 生成
/app/output/result.json 骨架（全字段占位），之后全程增量填充，防超时零交付。

行为：
  - output_contract 为 dict：按全部键生成占位（None）；
  - 已存在的 result.json 不被覆盖：仅补缺失键（增量语义）；
  - 固定补充 status / sources / uncertainty / change_records / checks；
  - 每次运行向 change_records 追加一条落盘记录（幂等可重跑）。

退出码：0=骨架就绪；2=case_summary.json 缺失（材料不足）；3=summary 非法。
"""
import argparse
import json
import os
import sys
import time

SKILL_NAME = "fieldatlas-coverage-audit"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main():
    ap = argparse.ArgumentParser(
        description="按 output_contract 生成 result.json 骨架，增量填充（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json",
                    help="case_summary.json 路径")
    ap.add_argument("--out", default="/app/output/result.json",
                    help="result.json 输出路径")
    args = ap.parse_args()

    if not os.path.isfile(args.summary):
        print("ERROR: case_summary.json 不存在（材料不足，exit 2）: %s"
              % args.summary, file=sys.stderr)
        return 2
    try:
        with open(args.summary, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary.json 非法（校验失败，exit 3）: %s" % e,
              file=sys.stderr)
        return 3

    contract = summary.get("output_contract") or {}
    if isinstance(contract, dict):
        contract_fields = list(contract.keys())
    elif isinstance(contract, list):
        contract_fields = [str(x) for x in contract]
    else:
        contract_fields = []

    result = {}
    if os.path.isfile(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                result = existing
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 旧骨架损坏：备份后重建
            os.replace(args.out, args.out + ".corrupt.bak")

    result.setdefault("case_id", summary.get("case_id", "UNKNOWN_CASE"))
    result.setdefault("skill_name", SKILL_NAME)
    result.setdefault("status", {
        "state": "partial",
        "reason": "脚手架初始化：字段尚未填充，后续步骤增量写入。",
    })
    for fld in contract_fields:
        if fld not in result:
            result[fld] = None
    result.setdefault("sources", [
        {"file": m.get("path"), "sniff": m.get("sniff"),
         "role": ("原始响应材料" if m.get("sniff") in
                  ("crossref", "europepmc", "publisher", "recordlist", "jsonl", "csv")
                  else m.get("sniff"))}
        for m in summary.get("materials", [])
    ])
    result.setdefault("uncertainty", [])
    result.setdefault("change_records", [])
    result.setdefault("checks", {})
    if not isinstance(result.get("change_records"), list):
        result["change_records"] = []
    result["change_records"].append({
        "ts": utc_now(),
        "action": "scaffold_init",
        "detail": "按 output_contract 生成/补齐骨架，占位字段 %d 个（增量语义，"
                  "已填字段不覆盖）。" % len(contract_fields),
    })

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("OK: result.json 骨架就绪 -> %s (contract 字段=%d)" % (args.out, len(contract_fields)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR: scaffold_result 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
