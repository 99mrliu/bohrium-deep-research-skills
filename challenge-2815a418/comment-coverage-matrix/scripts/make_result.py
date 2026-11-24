#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_result.py — 生成符合运行契约的 result.json。

- 从 case.json 提取原始 case_id 与 output_contract 全部字段名；result.json 必然包含这些字段
  （用 --artifact 字段名=路径 提供产物；未提供的字段置空串并列入 missing_fields，绝不少字段）。
- 含诚实 status（complete/partial/failed）、sources、uncertainty、change_records。

用法（快速路径第 0 步就该先跑一次 partial 版）:
  python3 make_result.py --case /input/case.json --status partial \
      --uncertainty "..." --out /app/output/result.json
  python3 make_result.py --case /input/case.json --status complete \
      --sources "a,b" --uncertainty "..." \
      --artifact revised_manuscript=/app/output/revised-manuscript.md \
      --change-records /app/output/changes.json --out /app/output/result.json
"""
import argparse, json, os, sys
from datetime import datetime, timezone


def load_case(path):
    if not path or not os.path.exists(path):
        return {}, []
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("[make_result] WARN: case.json 解析失败: %s" % e, file=sys.stderr)
        return {}, []
    cid = d.get("case_id") or d.get("caseId") or d.get("id") or "UNKNOWN"
    oc = d.get("output_contract") or {}
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        fields = [x if isinstance(x, str) else x.get("name", "") for x in oc]
        fields = [f for f in fields if f]
    else:
        fields = []
    return {"case_id": cid}, fields


def main():
    ap = argparse.ArgumentParser(description="生成 result.json（含 output_contract 全部字段）")
    ap.add_argument("--case", default=None)
    ap.add_argument("--status", default="partial", choices=["complete", "partial", "failed"])
    ap.add_argument("--sources", default="", help="逗号分隔的来源列表")
    ap.add_argument("--uncertainty", default="", help="不确定性/界限说明（必须诚实填写）")
    ap.add_argument("--artifact", action="append", default=[], metavar="字段=路径",
                    help="产物字段与路径，可多次；字段名以 case.json 的 output_contract 为准")
    ap.add_argument("--change-records", default=None, help="changes.json 路径（修改记录）")
    ap.add_argument("--note", default="", help="附加说明（如部分完成的界限）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    case, oc_fields = load_case(a.case)
    artifacts = {}
    for kv in a.artifact:
        if "=" not in kv:
            print("[make_result] FATAL: --artifact 须形如 字段=路径，收到 %r" % kv, file=sys.stderr)
            sys.exit(2)
        k, v = kv.split("=", 1)
        artifacts[k.strip()] = v.strip()

    result = {
        "case_id": case.get("case_id", "UNKNOWN"),
        "status": a.status,
        "skill": "comment-coverage-matrix",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec='seconds'),
        "sources": [s for s in (x.strip() for x in a.sources.split(",")) if s],
        "uncertainty": a.uncertainty or "未填写（不合规：必须诚实说明不确定性与界限）",
    }
    if a.note:
        result["note"] = a.note

    # output_contract 全字段：有 artifact 用 artifact，无则空串 + missing 列表
    missing = []
    for f in oc_fields:
        result[f] = artifacts.get(f, "")
        if not artifacts.get(f):
            missing.append(f)
    # artifact 里多给但不在 output_contract 的字段也保留（不丢信息）
    for k, v in artifacts.items():
        if k not in result:
            result[k] = v
    result["missing_fields"] = missing

    # 修改记录
    if a.change_records and os.path.exists(a.change_records):
        try:
            ch = json.load(open(a.change_records, encoding="utf-8"))
            result["change_records"] = [
                {"chg_id": c.get("chg_id"), "sub_ids": c.get("sub_ids"),
                 "section": c.get("section"), "paragraph": c.get("paragraph"),
                 "action": c.get("action"), "status": c.get("status")}
                for c in ch.get("changes", [])]
        except Exception as e:
            result["change_records"] = "changes 解析失败: %s" % e
    else:
        result["change_records"] = []

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("[make_result] case_id=%s status=%s contract_fields=%d missing=%d -> %s"
          % (result["case_id"], a.status, len(oc_fields), len(missing), a.out))
    if a.status == "complete" and missing:
        print("[make_result] WARN: status=complete 但 output_contract 字段缺失: %s" % missing, file=sys.stderr)
    if not a.uncertainty:
        print("[make_result] WARN: uncertainty 未填写", file=sys.stderr)


if __name__ == "__main__":
    main()
