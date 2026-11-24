#!/usr/bin/env python3
"""parse_case.py —— 解析案例输入（case.json + task.md），产出 case_summary.json。

退出码：0=成功；2=输入/材料不足（诚实降级）；3=校验失败。
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        description="解析案例 case.json 与 task.md，生成 case_summary.json。")
    ap.add_argument("--case", required=True, help="案例 case.json 路径")
    ap.add_argument("--task", required=True, help="任务说明 task.md 路径")
    ap.add_argument("--out", required=True, help="输出 case_summary.json 路径")
    args = ap.parse_args()

    for p, tag in ((args.case, "case.json"), (args.task, "task.md")):
        if not os.path.isfile(p):
            print(f"[E2] 输入缺失：{tag} 不存在或不可读：{p}", file=sys.stderr)
            return 2
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] case.json 解析失败：{e}", file=sys.stderr)
        return 3
    with open(args.task, "r", encoding="utf-8") as f:
        task_text = f.read()

    case_id = case.get("case_id") or case.get("id") or "unknown"
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        contract_fields = sorted(contract.keys())
    elif isinstance(contract, list):
        contract_fields = list(contract)
    else:
        contract_fields = []

    summary = {
        "case_id": case_id,
        "title": case.get("title", ""),
        "question": case.get("question") or case.get("research_question", ""),
        "output_contract_fields": contract_fields,
        "materials": case.get("materials", []),
        "task_excerpt": task_text[:2000],
        "case_keys": sorted(case.keys()),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[OK] case_summary.json 已生成：{args.out}（case_id={case_id}，"
          f"合同字段 {len(contract_fields)} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
