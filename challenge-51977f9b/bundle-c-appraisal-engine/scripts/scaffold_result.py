#!/usr/bin/env python3
"""scaffold_result.py —— 生成 result.json 保底骨架（第 2 步落盘，之后增量填充）。

退出码：0=成功；2=输入/材料不足；3=校验失败。
"""
import argparse
import json
import os
import sys

DEFAULT_FIELDS = ["case_id", "skill_name", "status", "product",
                  "evidence_matrix", "sources", "uncertainty",
                  "change_records", "counts", "checks"]


def main():
    ap = argparse.ArgumentParser(
        description="生成 result.json 保底骨架，skill_name 默认 slr-appraisal-engine。")
    ap.add_argument("--case-summary", required=True, help="case_summary.json 路径")
    ap.add_argument("--out", required=True, help="输出 result.json 路径")
    ap.add_argument("--skill-name", default="slr-appraisal-engine",
                    help="写入骨架的 skill_name（默认 slr-appraisal-engine）")
    args = ap.parse_args()

    if not os.path.isfile(args.case_summary):
        print(f"[E2] 输入缺失：case_summary.json 不存在：{args.case_summary}",
              file=sys.stderr)
        return 2
    try:
        with open(args.case_summary, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] case_summary.json 解析失败：{e}", file=sys.stderr)
        return 3

    fields = summary.get("output_contract_fields") or DEFAULT_FIELDS
    for d in DEFAULT_FIELDS:
        if d not in fields:
            fields.append(d)

    skeleton = {}
    for k in fields:
        if k == "case_id":
            skeleton[k] = summary.get("case_id", "unknown")
        elif k == "skill_name":
            skeleton[k] = args.skill_name
        elif k == "status":
            skeleton[k] = "partial"
        elif k in ("product", "counts", "checks"):
            skeleton[k] = {}
        elif k in ("evidence_matrix", "sources", "change_records"):
            skeleton[k] = []
        elif k == "uncertainty":
            skeleton[k] = ["骨架阶段：流程未完成，其余字段为占位值。"]
        else:
            skeleton[k] = None
    skeleton["status_reason"] = "保底骨架已落盘，综述流程尚未完成。"

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    print(f"[OK] result.json 骨架已生成：{args.out}（字段 {len(skeleton)} 个，"
          f"skill_name={args.skill_name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
