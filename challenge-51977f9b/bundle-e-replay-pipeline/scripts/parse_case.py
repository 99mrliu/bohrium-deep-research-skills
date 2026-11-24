#!/usr/bin/env python3
"""parse_case.py — 解析案例输入 case.json（及可选 task.md），输出结构化 case_summary.json。

退出码：0=成功；2=输入缺失或非法（规则码 R1/R2）。
产物为确定性 JSON（sort_keys），不含时间戳/随机数/绝对路径，可被 replay 复现。
"""
import argparse
import json
import os
import sys

CASE_ID_KEYS = ["case_id", "caseId", "caseID", "id"]
QUESTION_KEYS = ["question", "research_question", "title", "topic", "objective"]
CONTRACT_KEYS = ["output_contract", "outputContract", "deliverables"]
DEFAULT_CONTRACT = ["case_id", "skill_name", "status", "product", "evidence_matrix",
                    "sources", "uncertainty", "change_records", "counts", "checks"]


def eprint(*a):
    print(*a, file=sys.stderr)


def first_key(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return None


def main():
    ap = argparse.ArgumentParser(
        description="解析案例 case.json/task.md，生成 case_summary.json（确定性产物）。")
    ap.add_argument("--case", required=True, help="案例 case.json 路径")
    ap.add_argument("--task", default=None, help="可选 task.md 路径")
    ap.add_argument("--out", required=True, help="输出 case_summary.json 路径")
    args = ap.parse_args()

    if not os.path.isfile(args.case):
        eprint(f"R1: 案例文件不存在: {args.case}（输入不足，诚实降级）")
        return 2
    try:
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except json.JSONDecodeError as e:
        eprint(f"R2: 案例 JSON 解析失败: {e}")
        return 2
    if not isinstance(case, dict):
        eprint("R2: 案例 JSON 顶层必须是对象")
        return 2

    task_excerpt = ""
    if args.task:
        if os.path.isfile(args.task):
            with open(args.task, encoding="utf-8") as f:
                task_excerpt = f.read()[:2000]
        else:
            eprint(f"R1: task.md 不存在: {args.task}（继续，仅缺任务说明摘录）")

    case_id = first_key(case, CASE_ID_KEYS) or "UNKNOWN-CASE"
    contract = first_key(case, CONTRACT_KEYS) or DEFAULT_CONTRACT
    if not isinstance(contract, list):
        contract = DEFAULT_CONTRACT

    summary = {
        "case_id": case_id,
        "research_question": first_key(case, QUESTION_KEYS) or "",
        "pico": case.get("pico") or case.get("PICO") or {},
        "output_contract": contract,
        "materials": case.get("materials") or [],
        "task_excerpt": task_excerpt,
        "skill_name": "slr-replay-pipeline",
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"已生成案例摘要: {args.out} (case_id={case_id}, 合同字段 {len(contract)} 个)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
