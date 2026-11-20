#!/usr/bin/env python3
"""scaffold_result.py — 尽早生成 /app/output/result.json 骨架（步骤 2，脚本环节）。

按 case_summary.json 的 output_contract 字段列表生成骨架：
全部字段占位 null/[]/{}，case_id/skill_name 预填，status 先填 "in_progress"。
默认不覆盖已有 result.json（防超时零交付后的增量填充不被冲掉），除非 --force。

退出码：0=通过；2=输入不足；3=校验失败。幂等。
"""
import argparse
import json
import sys
from pathlib import Path

LIST_HINTS = ("source", "matrix", "uncertain", "change", "record", "list", "items",
              "evidence", "decision", "exclusion", "inclusion")
DICT_HINTS = ("count", "check", "summary", "prisma", "audit", "stat")
SKILL_NAME = "criteriaforge-screen-engine"


def placeholder(field: str):
    f = field.lower()
    if any(h in f for h in DICT_HINTS):
        return {}
    if any(h in f for h in LIST_HINTS):
        return []
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="按 output_contract 生成 result.json 骨架")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录（默认 /app/output）")
    ap.add_argument("--force", action="store_true", help="覆盖已有 result.json")
    args = ap.parse_args(argv)

    work = Path(args.work)
    out_dir = Path(args.output_dir)
    summary_path = work / "case_summary.json"
    if not summary_path.exists():
        print(f"[scaffold_result] 缺少 {summary_path}，请先运行 parse_case.py。", file=sys.stderr)
        return 2
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[scaffold_result] 输入不足/目录不可写: {e}", file=sys.stderr)
        return 2

    result_path = out_dir / "result.json"
    if result_path.exists() and not args.force:
        print(f"[scaffold_result] {result_path} 已存在，保留（用 --force 覆盖）。")
        return 0

    fields = summary.get("output_contract_fields") or []
    skeleton = {}
    for f in fields:
        skeleton[f] = placeholder(f)
    if "case_id" in skeleton:
        skeleton["case_id"] = summary.get("case_id")
    if "skill_name" in skeleton:
        skeleton["skill_name"] = SKILL_NAME
    if "status" in skeleton:
        skeleton["status"] = "in_progress"
    if not fields:  # 合同缺失时的最小骨架，运行时以 case.json 合同为准再补
        skeleton = {
            "case_id": summary.get("case_id"),
            "skill_name": SKILL_NAME,
            "status": "in_progress",
            "_warning": "output_contract 为空，骨架仅为占位，最终字段以 case.json 合同为准",
        }
    result_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[scaffold_result] 骨架字段数={len(skeleton)} -> {result_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[scaffold_result] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
