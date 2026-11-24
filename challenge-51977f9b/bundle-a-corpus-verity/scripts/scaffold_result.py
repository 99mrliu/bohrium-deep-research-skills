#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scaffold_result.py — result.json 保底骨架生成（slr-corpus-verity）

按 case_summary.json 中的 output_contract 生成全部字段的占位骨架，
保证即使流程中断也有可交付物。已知字段给语义化默认值，未知字段给
空字符串占位并记入 _placeholder_fields，便于后续增量填充时核对。

退出码：0=通过；2=输入/材料不足（诚实降级）；3=输出不可写等校验失败
"""
import argparse
import datetime
import json
import os
import sys

SKILL_NAME = "slr-corpus-verity"

# 已知字段的骨架默认值
KNOWN_DEFAULTS = {
    "case_id": None,                      # 由 summary 填充
    "skill_name": SKILL_NAME,
    "status": "draft",                    # draft → partial/complete/failed
    "product": "",
    "evidence_matrix": [],
    "sources": [],
    "uncertainty": [],
    "change_records": [],
    "counts": {},
    "checks": {},
}


def guess_placeholder(field):
    """未知合同字段的占位值：按字段名猜测容器类型，猜不到给空字符串。"""
    low = field.lower()
    if any(k in low for k in ("matrix", "list", "records", "items", "results",
                              "reasons", "quarantine", "sources", "excluded")):
        return []
    if any(k in low for k in ("count", "summary", "prisma", "stats", "mapping",
                              "checks", "metadata")):
        return {}
    return ""


def main():
    ap = argparse.ArgumentParser(
        description="按 output_contract 生成 result.json 保底骨架（status=draft）。"
                    "退出码：0=通过；2=材料不足；3=校验失败。")
    ap.add_argument("--summary", required=True, help="case_summary.json 路径")
    ap.add_argument("--out", required=True, help="result.json 输出路径（如 /app/output/result.json）")
    args = ap.parse_args()

    if not os.path.isfile(args.summary):
        print("[R1] case_summary.json 缺失：{}（exit 2）".format(args.summary),
              file=sys.stderr)
        return 2
    try:
        with open(args.summary, "r", encoding="utf-8") as fh:
            summary = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        print("[R2] case_summary.json 不可解析：{}（exit 2）".format(e), file=sys.stderr)
        return 2
    if not isinstance(summary, dict):
        print("[R2] case_summary.json 顶层不是对象（exit 2）", file=sys.stderr)
        return 2

    contract = summary.get("output_contract")
    if not isinstance(contract, list) or not contract:
        contract = list(KNOWN_DEFAULTS.keys())

    result, placeholders = {}, []
    for field in contract:
        if not isinstance(field, str) or not field:
            continue
        if field in KNOWN_DEFAULTS:
            result[field] = KNOWN_DEFAULTS[field]
        else:
            result[field] = guess_placeholder(field)
            placeholders.append(field)
    result["case_id"] = summary.get("case_id") or "unknown-case"
    # 保底必备字段：即使合同未列出也补齐
    for field, default in KNOWN_DEFAULTS.items():
        if field not in result and field != "case_id":
            result[field] = default
    result["status"] = "draft"
    result["skill_name"] = SKILL_NAME
    result["_skeleton"] = {
        "generated_by": "scaffold_result.py",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "placeholder_fields": placeholders,
        "note": "保底骨架：流程中断时本文件即为可交付物；后续环节应增量填充并移出占位字段。",
    }
    rq = (summary.get("research_question") or {})
    if rq.get("needs_confirmation") and rq.get("text"):
        result["uncertainty"].append(
            "研究问题来自 task.md 文本提取，needs_confirmation=true：{}".format(rq["text"]))

    try:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        print("[R3] result.json 不可写：{}（exit 3）".format(e), file=sys.stderr)
        return 3

    print("骨架已落盘：{}（合同字段 {} 个，占位字段 {} 个）"
          .format(args.out, len(contract), len(placeholders)))
    if placeholders:
        print("  占位字段：{}".format("、".join(placeholders)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
