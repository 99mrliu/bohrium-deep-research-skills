#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 按 case.json 的 output_contract 组装 result.json。

规则：
- result 必须含 case_id 与 output_contract 声明的全部字段；
- 任何字段无法填充 → 补 None（JSON null），并记入 null_filled；
- 存在 partial_reasons 或 null_filled 或 gaps 时 status = "partial"，否则 "complete"；
- 绝不编造字段值：sections 里没有的数据一律走 null 兜底。
"""
import json
import sys


def assemble(case, sections, gaps=None, partial_reasons=None, generated_by=None):
    contract = case.get("output_contract") or []
    if isinstance(contract, dict):  # 兼容 {"fields": [...]} 形式
        contract = contract.get("fields", [])
    gaps = list(gaps or [])
    partial_reasons = list(partial_reasons or [])

    result = {"case_id": case.get("case_id")}
    result.update(sections)
    # status/generated_by 属于结果自身的元字段，先占位再参与 contract 覆盖检查，
    # 避免被误判为 null_filled；status 终值在 null 填充后计算。
    result["generated_by"] = generated_by or "citation-snowball-discovery skill bundle"
    result["status"] = None

    null_filled = []
    for field in contract:
        if field not in result:
            result[field] = None
            null_filled.append(field)
    result.setdefault("gaps", gaps)
    if gaps and result["gaps"] is not gaps:
        result["gaps"] = result["gaps"] + gaps

    status = "partial" if (partial_reasons or null_filled or result.get("gaps")) else "complete"
    result["status"] = status

    meta = {}
    if null_filled:
        meta["null_filled_fields"] = null_filled
    if partial_reasons:
        meta["partial_reasons"] = partial_reasons
    if meta:
        result["_assembly"] = meta
    return result


def write_result(result, output_path):
    import os
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv):
    if len(argv) != 4:
        print("用法: assemble_result.py <case.json> <sections.json> <output_path>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        case = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        payload = json.load(f)
    result = assemble(
        case,
        payload.get("sections", {}),
        gaps=payload.get("gaps"),
        partial_reasons=payload.get("partial_reasons"),
        generated_by=payload.get("generated_by"),
    )
    write_result(result, argv[3])
    print("written: %s (status=%s)" % (argv[3], result["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
