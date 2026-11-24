#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_case.py — 防御式解析案例输入，生成 case_summary.json。

读取案例目录中的 case.json 与 task.md（默认 /input/，可用参数覆盖），
做防御式解析：缺文件、JSON 损坏、字段缺失均不崩溃，而是降级为 exit 2
或在摘要中记录 warnings，供后续步骤诚实声明。

退出码：0=成功；2=输入/材料不足（案例文件缺失或不可解析）；3=校验失败。
"""
import argparse
import json
import os
import sys

DEFAULT_CONTRACT_FIELDS = [
    "case_id", "skill_name", "status", "product", "evidence_matrix",
    "sources", "uncertainty", "change_records", "counts", "checks",
]


def eprint(msg):
    print(msg, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description="防御式解析 /input/case.json + task.md，输出 case_summary.json。",
        epilog="退出码：0=成功；2=案例文件缺失或不可解析；3=输出写入失败。",
    )
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--task", default="/input/task.md", help="task.md 路径（可缺省，缺省记 warning）")
    ap.add_argument("--out", default="case_summary.json", help="输出摘要路径")
    args = ap.parse_args()

    if not os.path.isfile(args.case):
        eprint(f"[P1] 错误：案例文件不存在：{args.case}")
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        eprint(f"[P2] 错误：case.json 无法解析（{exc}）")
        return 2
    if not isinstance(case, dict):
        eprint("[P3] 错误：case.json 顶层必须是 JSON 对象")
        return 2

    warnings = []

    case_id = case.get("case_id") or case.get("id") or "UNKNOWN_CASE"
    if case_id == "UNKNOWN_CASE":
        warnings.append("case.json 缺少 case_id 字段，已使用占位值 UNKNOWN_CASE")

    question = (case.get("research_question") or case.get("question")
                or case.get("title") or "")
    if not question:
        warnings.append("case.json 未给出 research_question/question 字段")

    # output_contract 兼容两种形态：字段名列表，或含 required_fields 的对象
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        fields = contract.get("required_fields") or contract.get("fields") or []
    elif isinstance(contract, list):
        fields = [x for x in contract if isinstance(x, str)]
    else:
        fields = []
    contract_source = "case.output_contract"
    if not fields:
        fields = list(DEFAULT_CONTRACT_FIELDS)
        contract_source = "默认通用字段（案例未提供 output_contract）"
        warnings.append("案例未提供 output_contract，result.json 将使用默认通用字段")

    materials = case.get("materials") or case.get("files") or []
    if not isinstance(materials, list):
        materials = [str(materials)]

    task_excerpt = ""
    if os.path.isfile(args.task):
        try:
            with open(args.task, "r", encoding="utf-8") as f:
                task_excerpt = f.read()[:2000]
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"task.md 读取失败：{exc}")
    else:
        warnings.append(f"task.md 不存在（{args.task}），仅以 case.json 为准")

    summary = {
        "case_id": case_id,
        "research_question": question,
        "output_contract_fields": fields,
        "output_contract_source": contract_source,
        "materials": materials,
        "task_excerpt": task_excerpt,
        "extra_keys": sorted(k for k in case.keys()
                             if k not in {"case_id", "id", "research_question",
                                          "question", "title", "output_contract",
                                          "materials", "files"}),
        "warnings": warnings,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        eprint(f"[P4] 错误：摘要写入失败（{exc}）")
        return 3

    print(f"[OK] 案例解析完成：case_id={case_id}，合同字段 {len(fields)} 个，"
          f"材料 {len(materials)} 项，警告 {len(warnings)} 条 → {args.out}")
    for w in warnings:
        print(f"  [警告] {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
