#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 按 output_contract 生成 result.json 占位骨架。

在流程早期（契约要求第 2 步左右）把 result.json 骨架落盘，之后增量填充，
避免任务中断时交付物完全缺失。skill_name 固定为 slr-dual-screen。

退出码：0=成功；2=case_summary.json 缺失或不可解析；3=写入失败。
"""
import argparse
import json
import os
import sys

SKILL_NAME = "slr-dual-screen"

# 各占位字段的默认填充值
def default_value(field, case_id):
    table = {
        "case_id": case_id,
        "skill_name": SKILL_NAME,
        "status": "partial",
        "product": "",
        "evidence_matrix": [],
        "sources": [],
        "uncertainty": ["骨架阶段：全部结论尚未填充，最终以完整流程产物为准"],
        "change_records": [],
        "counts": {},
        "checks": [],
    }
    return table.get(field, None)


def eprint(msg):
    print(msg, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description="按 output_contract 生成 result.json 占位骨架（skill_name=slr-dual-screen）。",
        epilog="退出码：0=成功；2=case_summary.json 缺失或不可解析；3=写入失败。",
    )
    ap.add_argument("--case-summary", default="case_summary.json",
                    help="parse_case.py 的输出")
    ap.add_argument("--out", default="result.json", help="骨架输出路径")
    ap.add_argument("--force", action="store_true",
                    help="覆盖已存在的 result.json（默认不覆盖，保护已填充内容）")
    args = ap.parse_args()

    if not os.path.isfile(args.case_summary):
        eprint(f"[C1] 错误：case_summary.json 不存在：{args.case_summary}（请先运行 parse_case.py）")
        return 2
    try:
        with open(args.case_summary, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        eprint(f"[C2] 错误：case_summary.json 无法解析（{exc}）")
        return 2

    fields = summary.get("output_contract_fields") or []
    if not fields:
        eprint("[C3] 错误：case_summary 中 output_contract_fields 为空")
        return 2
    case_id = summary.get("case_id") or "UNKNOWN_CASE"

    if os.path.exists(args.out) and not args.force:
        # 已存在则只补缺失字段，不覆盖已填充内容
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = {}
        added = []
        for field in fields:
            if field not in existing:
                existing[field] = default_value(field, case_id)
                added.append(field)
        existing["skill_name"] = SKILL_NAME
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            eprint(f"[C4] 错误：result.json 写入失败（{exc}）")
            return 3
        print(f"[OK] result.json 已存在，仅补齐缺失字段 {len(added)} 个：{added}")
        return 0

    result = {field: default_value(field, case_id) for field in fields}
    result["skill_name"] = SKILL_NAME
    if "status" in result:
        result["status"] = "partial"  # 骨架阶段一律 partial，流程走完再置 complete
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        eprint(f"[C4] 错误：result.json 写入失败（{exc}）")
        return 3
    print(f"[OK] result.json 骨架已生成：{args.out}（{len(fields)} 个字段，"
          f"status=partial，待增量填充）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
