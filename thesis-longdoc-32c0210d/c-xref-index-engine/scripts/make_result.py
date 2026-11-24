#!/usr/bin/env python3
"""make_result.py — 读取 case.json 的 output_contract.fields，逐字段填充并原子写 result.json。

用法：
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --status success|partial [--report consistency_report.json] [--impact impact_report.json] \
      [--changes changes.json] [--chapters EDITED_DIR] \
      [--source PATH ...] [--uncertainty TEXT ...] [--note TEXT]

规则：
- 契约字段逐一填充；无法填充的字段填 null，并记入 unfilled_fields（诚实 partial）。
- consistency_report 字段填 {"file","errors","warnings"}；impact_report 填 {"file","affected_count"}。
- 先存 partial 再改进：可在流程早期以 --status partial 运行一次，完成后以 success 覆写。
- 原子写：先写临时文件再 os.replace。
"""
import argparse
import json
import os
import sys


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description="按 output_contract 装配 result.json（原子写）")
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--out", required=True, help="/app/output/result.json")
    ap.add_argument("--status", default="partial", choices=["success", "partial", "failed"])
    ap.add_argument("--report", help="consistency_report.json 路径")
    ap.add_argument("--impact", help="impact_report.json 路径")
    ap.add_argument("--changes", help="change records JSON（list）路径")
    ap.add_argument("--chapters", help="已编辑章节目录（列出其中文件作为 edited_chapters）")
    ap.add_argument("--source", action="append", default=[], help="输入来源，可重复")
    ap.add_argument("--uncertainty", action="append", default=[], help="不确定项，可重复")
    ap.add_argument("--note", default="", help="备注（合成示例必须传 SYNTHETIC 标注）")
    args = ap.parse_args()

    try:
        case = load_json(args.case)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: cannot read case.json: %s" % e, file=sys.stderr)
        return 2
    case_id = case.get("case_id")
    fields = (case.get("output_contract") or {}).get("fields") or []

    report_val = None
    if args.report:
        try:
            rep = load_json(args.report)
            s = rep.get("summary", {})
            report_val = {"file": os.path.basename(args.report),
                          "errors": s.get("errors"), "warnings": s.get("warnings")}
        except (OSError, json.JSONDecodeError):
            report_val = {"file": os.path.basename(args.report), "errors": None,
                          "warnings": None, "problem": "report unreadable"}

    impact_val = None
    if args.impact:
        try:
            imp = load_json(args.impact)
            impact_val = {"file": os.path.basename(args.impact),
                          "affected_count": imp.get("affected_count")}
        except (OSError, json.JSONDecodeError):
            impact_val = {"file": os.path.basename(args.impact), "affected_count": None,
                          "problem": "impact report unreadable"}

    changes = []
    if args.changes:
        try:
            changes = load_json(args.changes)
        except (OSError, json.JSONDecodeError):
            changes = [{"problem": "changes file unreadable: %s" % args.changes}]

    edited = None
    if args.chapters and os.path.isdir(args.chapters):
        edited = sorted(n for n in os.listdir(args.chapters)
                        if os.path.isfile(os.path.join(args.chapters, n)))

    result = {"case_id": case_id, "status": args.status}
    if args.note:
        result["note"] = args.note
    result["sources"] = args.source
    result["uncertainty"] = args.uncertainty
    result["change_records"] = changes

    def fill(field):
        f = field.lower()
        if f == "case_id":
            return case_id, True
        if f == "status":
            return args.status, True
        if f in ("consistency_report", "xref_report"):
            return report_val, report_val is not None
        if f == "impact_report":
            return impact_val, impact_val is not None
        if f in ("edited_chapters", "chapters"):
            return edited, edited is not None
        if f in ("change_record", "change_records", "changes"):
            return changes, True
        if f == "uncertainty":
            return args.uncertainty, True
        if f == "sources":
            return args.source, True
        return None, False

    unfilled = []
    for field in fields:
        if field in result:
            continue
        val, ok = fill(field)
        result[field] = val
        if not ok:
            unfilled.append(field)
    if unfilled:
        result["unfilled_fields"] = unfilled

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, ".result.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, args.out)
    print("result.json written: %s (status=%s, fields=%d, unfilled=%s)"
          % (args.out, args.status, len(fields), unfilled or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
