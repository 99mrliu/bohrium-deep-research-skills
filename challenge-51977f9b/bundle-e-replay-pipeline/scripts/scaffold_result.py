#!/usr/bin/env python3
"""scaffold_result.py — 生成 result.json 保底骨架（skill_name=slr-replay-pipeline）。

契约要求第 2 步左右落盘骨架，之后增量填充；任何后续失败都有诚实 partial 可交付。
若骨架已存在则默认保留（断点续跑友好），--force 才重建。
退出码：0=成功；2=case_summary 给定但非法（R1/R2）。
"""
import argparse
import json
import os
import sys

SKILL_NAME = "slr-replay-pipeline"

SKELETON = {
    "case_id": "",
    "skill_name": SKILL_NAME,
    "status": "partial",
    "status_reason": "骨架已生成，综述流程尚未完成；本文件为保底交付。",
    "product": {
        "review_summary": "",
        "conclusions": [],
        "conflict_evidence": [],
        "research_gaps": [],
    },
    "evidence_matrix": [],
    "sources": [],
    "uncertainty": [],
    "change_records": [],
    "counts": {},
    "checks": {
        "runlog_verify": {"exit_code": None, "summary": "未执行"},
        "reconcile": {"exit_code": None, "summary": "未执行"},
        "replay": {"exit_code": None, "summary": "未执行"},
    },
}


def eprint(*a):
    print(*a, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="生成 result.json 保底骨架。")
    ap.add_argument("--out", required=True, help="输出 result.json 路径")
    ap.add_argument("--case-summary", default=None, help="可选 case_summary.json，用于回填 case_id")
    ap.add_argument("--force", action="store_true", help="已存在时强制重建")
    args = ap.parse_args()

    case_id = ""
    if args.case_summary:
        if not os.path.isfile(args.case_summary):
            eprint(f"R1: case_summary 不存在: {args.case_summary}")
            return 2
        try:
            with open(args.case_summary, encoding="utf-8") as f:
                case_id = json.load(f).get("case_id", "")
        except json.JSONDecodeError as e:
            eprint(f"R2: case_summary JSON 非法: {e}")
            return 2

    if os.path.isfile(args.out) and not args.force:
        try:
            with open(args.out, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("skill_name") == SKILL_NAME:
                print(f"骨架已存在，保留现状（断点续跑）: {args.out}")
                return 0
        except json.JSONDecodeError:
            pass  # 已存在但非法，按重建处理

    skeleton = json.loads(json.dumps(SKELETON))
    skeleton["case_id"] = case_id
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"已生成 result.json 骨架: {args.out} (skill_name={SKILL_NAME}, status=partial)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
