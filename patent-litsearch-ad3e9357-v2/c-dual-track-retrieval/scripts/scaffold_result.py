#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 先生成诚实的 partial 骨架，再逐步填充（预算保护）。

仅依赖 python3 标准库。退出码：0 成功；2 参数/输入不可用。

用法：
  scaffold_result.py --case case.json --out DIR [--fill fill.json] [--status ok|partial|failed]

行为：
  * 对任意形态的 case.json 防御性解析：output_contract 为 dict → 取其键；
    为 list → 取其元素；缺失 → 使用内置默认字段集。所有未填字段 → null，
    并在 uncertainty 中写明“未填字段为 null”。
  * 骨架必含 case_id / status / sources / uncertainty / change_records。
  * --fill fill.json：顶层键合并（fill 优先），并追加一条 change_records。
"""
import argparse
import json
import os
import sys
import time

DEFAULT_FIELDS = ["research_question", "query_log", "candidates", "screening",
                  "omissions_note", "status", "sources", "uncertainty",
                  "change_records"]
STATUSES = ("ok", "partial", "failed")


def load_case(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"_raw": data}
    except (OSError, json.JSONDecodeError) as exc:
        print("WARN: case.json 无法解析（%s），按空 case 生成骨架" % exc,
              file=sys.stderr)
        return {}


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, dict):
        fields = list(c.keys())
    elif isinstance(c, list):
        fields = [str(x) for x in c]
    elif isinstance(c, str):
        fields = [s.strip() for s in c.split(",") if s.strip()]
    else:
        fields = list(DEFAULT_FIELDS)
    for f in DEFAULT_FIELDS:
        if f not in fields:
            fields.append(f)
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 骨架生成/填充")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True, help="输出目录（写出 result.json）")
    ap.add_argument("--fill", default=None, help="可选：顶层键合并的填充 JSON")
    ap.add_argument("--status", choices=STATUSES, default="partial")
    args = ap.parse_args(argv)

    case = load_case(args.case)
    result = {"case_id": case.get("case_id") or "UNKNOWN", "status": args.status}
    for f in contract_fields(case):
        result.setdefault(f, None)
    result["status"] = args.status
    result["sources"] = []
    result["uncertainty"] = [
        "骨架由 scaffold_result.py 生成：未填字段一律为 null，不代表已检索为空。",
        "零命中是合法结果，但必须以 corpus_search 的扫描范围说明佐证，不得臆造。",
    ]
    result["change_records"] = [{
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": "scaffold",
        "detail": "生成镜像 output_contract 的 %s 骨架（%d 个字段）"
                  % (args.status, len(contract_fields(case))),
    }]

    if args.fill:
        with open(args.fill, "r", encoding="utf-8") as f:
            fill = json.load(f)
        if not isinstance(fill, dict):
            print("FAIL: --fill 必须是 JSON 对象", file=sys.stderr)
            return 2
        filled = sorted(k for k, v in fill.items()
                        if v is not None and result.get(k) != v)
        result.update(fill)
        result["change_records"].append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "action": "fill",
            "detail": "合并填充字段: %s" % ("、".join(filled) or "（无实际变更）"),
        })

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    null_fields = [k for k in contract_fields(case)
                   if result.get(k) is None and k not in
                   ("status", "sources", "uncertainty", "change_records")]
    print("scaffold: case_id=%s status=%s → %s（仍为 null 的契约字段: %s）"
          % (result["case_id"], result["status"], out_path,
             "、".join(null_fields) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
