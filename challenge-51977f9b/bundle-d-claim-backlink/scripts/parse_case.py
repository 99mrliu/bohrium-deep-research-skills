#!/usr/bin/env python3
"""parse_case.py — 解析 /input/case.json，输出 case_summary.json。

退出码：0=成功；2=输入缺失或无法解析（诚实降级）；3=校验失败。
"""
import argparse
import json
import sys

DEFAULT_CONTRACT = [
    "case_id", "skill_name", "status", "product", "evidence_matrix",
    "sources", "uncertainty", "change_records", "counts", "checks",
]


def fail_input(msg):
    print(f"[E-INPUT] {msg}", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(
        description="解析案例 case.json，生成 case_summary.json（供 scaffold_result.py 使用）。")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--out", required=True, help="输出 case_summary.json 路径")
    args = ap.parse_args()

    try:
        with open(args.case, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        fail_input(f"无法读取案例文件 {args.case}：{e}")
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as e:
        fail_input(f"案例文件不是合法 JSON：{e}")
    if not isinstance(case, dict):
        fail_input("案例文件顶层必须是 JSON 对象。")

    case_id = case.get("case_id") or case.get("id") or case.get("slug")
    notes = []
    if not case_id:
        case_id = "case-unknown"
        notes.append("案例缺少 case_id 字段，已用占位值 case-unknown。")

    question = (case.get("question") or case.get("research_question")
                or case.get("description") or case.get("task") or "")
    title = case.get("title") or ""

    materials = case.get("materials") or case.get("sources") or case.get("files") or []
    if isinstance(materials, dict):
        materials = list(materials.values())
    if not isinstance(materials, list):
        materials = [str(materials)]
    if not materials:
        notes.append("案例未列出材料清单；请检查 /input 下的实际文件。")

    contract = case.get("output_contract") or case.get("output_fields") or []
    if isinstance(contract, dict):
        contract = list(contract.keys())
    if not contract:
        contract = list(DEFAULT_CONTRACT)
        notes.append("案例未提供 output_contract，已使用通用默认字段。")

    summary = {
        "case_id": str(case_id),
        "title": str(title),
        "question": str(question),
        "materials": [str(m) for m in materials],
        "output_contract": [str(c) for c in contract],
        "notes": notes,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"已生成 {args.out}：case_id={summary['case_id']}，"
          f"材料 {len(summary['materials'])} 项，输出合同字段 {len(contract)} 个。")
    for n in notes:
        print(f"[提示] {n}")
    sys.exit(0)


if __name__ == "__main__":
    main()
