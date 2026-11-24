#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_result.py — result.json 组装器。

以 case.json 的 output_contract 为准生成 /app/output/result.json：
  - case_id 原样照抄；
  - output_contract 的每个字段都必须出现（--artifact 字段名=路径 提供）；
  - 缺失字段置 null 并把 status 强制降为 partial，同时在 uncertainty 中注明；
  - 含诚实的 status、sources、uncertainty、change_records。

预算安全网：进入任务后的第一条命令应先用 --status partial 落一个合法 result.json，
流水线完成后再用完整 --artifact 覆盖。

仅依赖 Python 3 标准库。

用法：
  python3 make_result.py --case /input/case.json --outdir /app/output \
    --status partial \
    --artifact revised_manuscript=/app/output/revised-manuscript.md \
    --artifact response_letter=/app/output/response-letter.md \
    --source materials/manuscript-baseline.md --source materials/reviewer-comments.md \
    --uncertainty "……" --change-records /app/output/change_record.md
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="组装 result.json")
    ap.add_argument("--case", required=True, help="case.json 路径（取 case_id 与 output_contract）")
    ap.add_argument("--outdir", required=True, help="result.json 输出目录（通常 /app/output）")
    ap.add_argument("--status", default="partial", choices=["ready_for_review", "partial", "failed"])
    ap.add_argument("--artifact", action="append", default=[],
                    help="字段名=路径（字段名须与 output_contract 一致；可重复）")
    ap.add_argument("--source", action="append", default=[], help="来源标注（可重复）")
    ap.add_argument("--uncertainty", action="append", default=[], help="不确定性说明（可重复）")
    ap.add_argument("--change-records", default=None, help="change_record.md 或 changes.json 路径")
    args = ap.parse_args()

    case = load_json(args.case)
    case_id = case.get("case_id", "UNKNOWN-CASE")
    contract = case.get("output_contract") or {}
    if isinstance(contract, list):
        contract_fields = list(contract)
    else:
        contract_fields = list(contract.keys())

    artifacts = {}
    for item in args.artifact:
        if "=" not in item:
            print("make_result: 忽略非法 --artifact（缺 '='）：%s" % item, file=sys.stderr)
            continue
        k, v = item.split("=", 1)
        artifacts[k.strip()] = v.strip()

    uncertainties = list(args.uncertainty)
    status = args.status
    missing = [f for f in contract_fields if f not in artifacts]
    if missing and status != "failed":
        status = "partial"
        uncertainties.append("output_contract 字段缺失（置 null）：%s" % "、".join(missing))
    # 标注不存在的产物路径（诚实检查）
    for k, v in artifacts.items():
        if not os.path.exists(v):
            status = "partial" if status != "failed" else status
            uncertainties.append("产物路径不存在：%s -> %s" % (k, v))

    change_records = []
    if args.change_records and os.path.exists(args.change_records):
        if args.change_records.endswith(".json"):
            doc = load_json(args.change_records)
            for c in doc.get("changes", []):
                change_records.append({
                    "chg_id": c.get("chg_id"), "action": c.get("action"),
                    "status": c.get("status"), "linked_rids": c.get("linked_rids", []),
                    "section": c.get("section"), "line": c.get("line"),
                })
        else:
            with open(args.change_records, "r", encoding="utf-8") as f:
                heads = [ln.strip() for ln in f if ln.startswith("### ")]
            change_records = [{"entry": h.lstrip("# ").strip()} for h in heads]

    result = {
        "case_id": case_id,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill": "editorial-delivery-forge",
        "sources": args.source or ["materials/manuscript-baseline.md", "materials/reviewer-comments.md"],
        "uncertainty": uncertainties,
        "change_records": change_records,
        "honesty_statement": ("本结果基于组织方给出的基线稿件与意见摘要：未冒称审稿人原文逐字要求；"
                              "未补做任何真实实验/数据（未到位证据已如实标注 pending/impossible）；"
                              "不代表原作者已改稿或编辑部已接收。"),
    }
    for f in contract_fields:
        result[f] = artifacts.get(f)
    # 契约外的附加产物也一并登记，便于评审
    extra = {k: v for k, v in artifacts.items() if k not in contract_fields}
    if extra:
        result["additional_artifacts"] = extra

    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("make_result: status=%s, 契约字段 %d（缺失 %d）-> %s" % (
        status, len(contract_fields), len(missing), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
