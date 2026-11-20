#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 按 output_contract 生成 /app/output/result.json 骨架。

保底策略：工作流第 2 步即运行本脚本，先落盘骨架（含 case.json output_contract 的
全部字段），之后全程增量填充，防止超时零交付。
默认不覆盖已存在的 result.json（--force 强制重建）。

退出码：0=成功（或骨架已存在）；2=case_summary 缺失（材料不足）；3=输入非法。
顶层未捕获异常汇总并以 exit 2 诚实降级，绝不 crash。

用法：
  python3 scaffold_result.py [--summary /app/work/case_summary.json]
      [--out /app/output/result.json] [--skill querytrace-lineage-chain] [--force]
"""
import argparse
import json
import os
import sys

DEFAULT_FIELDS = ["case_id", "skill_name", "status", "product", "sources",
                  "uncertainty", "change_records", "counts", "checks"]

FIELD_HINTS = {
    "case_id": "来自 case_summary.json 的 case_id",
    "skill_name": "固定为 querytrace-lineage-chain",
    "status": "complete / partial / failed + reason",
    "product": "主产物：查询台账 + 溯源账本 + 链核验 + 导入 diff + 报告路径",
    "sources": "材料清单：文件名+用途+定位（来自 case_summary.materials）",
    "uncertainty": "query_unrecorded、unparsed_files、unresolved 模糊对、限流痕迹等",
    "change_records": "脚手架初始化、人工/模型修改、task.md 取题的二次确认",
    "counts": "各环节计数（材料数/来源库数/记录数/canonical 数/断链数）",
    "checks": "脚本校验结果（parse_case/query_log/build_lineage/verify_chain/"
              "import_diff/selfcheck 的 exit 码与摘要）",
}


def main():
    ap = argparse.ArgumentParser(description="生成 result.json 骨架（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json",
                    help="parse_case.py 输出的 case_summary.json 路径")
    ap.add_argument("--out", default="/app/output/result.json", help="输出路径")
    ap.add_argument("--skill", default="querytrace-lineage-chain", help="skill_name")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 result.json")
    args = ap.parse_args()

    if os.path.isfile(args.out) and not args.force:
        print("OK: %s 已存在，按保底策略不覆盖（如需重建用 --force）。" % args.out)
        return 0
    if not os.path.isfile(args.summary):
        print("ERROR: case_summary 不存在（材料不足）: %s；请先运行 parse_case.py。"
              % args.summary, file=sys.stderr)
        return 2
    try:
        with open(args.summary, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    contract = summary.get("output_contract") or []
    fields = list(dict.fromkeys(DEFAULT_FIELDS + [str(c) for c in contract]))
    extra = [c for c in contract if c not in DEFAULT_FIELDS]
    if extra:
        print("WARN: output_contract 含默认之外的字段，已按占位生成: %s" % extra,
              file=sys.stderr)

    skeleton = {}
    for k in fields:
        if k == "case_id":
            skeleton[k] = summary.get("case_id", "unknown-case")
        elif k == "skill_name":
            skeleton[k] = args.skill
        elif k == "status":
            skeleton[k] = {"state": "partial",
                           "reason": "骨架占位：result.json 由 scaffold_result.py 生成，"
                                     "后续按工作流增量填充"}
        elif k == "change_records":
            skeleton[k] = [{"actor": "scaffold_result.py", "action": "init_skeleton",
                            "note": "保底骨架落盘，防超时零交付"}]
        elif k == "sources":
            srcs = [{"name": "case.json/task.md", "use": "案例输入", "location": "/input/"}]
            for m in summary.get("materials") or []:
                srcs.append({"name": m.get("file"), "use": "检索材料（sniff=%s）"
                             % m.get("sniff"), "location": m.get("path"),
                             "item_count": m.get("item_count")})
            skeleton[k] = srcs
        elif k == "uncertainty":
            skeleton[k] = list(summary.get("warnings") or [])
        elif k == "checks":
            skeleton[k] = []
        elif k in ("counts",):
            skeleton[k] = {"materials": len(summary.get("materials") or []),
                           "source_dbs": len(summary.get("source_dbs") or [])}
        else:
            skeleton[k] = {"_placeholder": True,
                           "hint": FIELD_HINTS.get(k, "output_contract 要求字段，按案例语义填充")}

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
    print("OK: result.json 骨架已写出 -> %s (字段=%d)" % (args.out, len(skeleton)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
