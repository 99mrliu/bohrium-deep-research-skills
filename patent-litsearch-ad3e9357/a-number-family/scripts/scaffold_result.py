#!/usr/bin/env python3
"""scaffold_result.py — 生成 /app/output/result.json 骨架（仅标准库）。

用法：
  python3 scaffold_result.py --case /input/case.json --out /app/output \
      [--fill fill.json] [--status partial]
行为：
  - 读取 case.json，取 case_id（缺失则置 null 并写入 uncertainty）；
  - 镜像 output_contract 全部字段：dict 取其键、list 取其项，值默认 null，
    未被 --fill 填充的字段列入 unfilled_contract_fields 并写入 uncertainty；
  - --fill JSON 可填充 candidates/families/evidence_records/sources 等主结果；
  - status 默认 partial（诚实优先：先落盘再迭代改进）。
"""
import argparse
import json
import os
import sys


def load_case(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as e:
        return None, "case.json 无法读取: %s" % e


def mirror_contract(contract, fill):
    fields, unfilled = {}, []
    if isinstance(contract, dict):
        items = list(contract.keys())
    elif isinstance(contract, list):
        items = [str(x) for x in contract]
    else:
        return fields, ["output_contract 缺失或格式不识，无法镜像"]
    for k in items:
        if k in fill:
            fields[k] = fill[k]
        else:
            fields[k] = None
            unfilled.append(k)
    return fields, unfilled


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fill")
    ap.add_argument("--status", default="partial",
                    choices=["ok", "partial", "failed"])
    args = ap.parse_args(argv[1:])

    case, err = load_case(args.case)
    uncertainty = []
    if err:
        uncertainty.append(err)
        case = {}
    case_id = case.get("case_id") or case.get("id")
    if case_id is None:
        uncertainty.append("case.json 中未找到 case_id")

    fill = {}
    if args.fill:
        try:
            with open(args.fill, encoding="utf-8") as f:
                fill = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("fill 文件无法读取: %s" % e, file=sys.stderr)
            return 2

    contract_fields, unfilled = mirror_contract(case.get("output_contract"), fill)
    if unfilled:
        uncertainty.append("以下 output_contract 字段尚未填充（置 null）："
                           + "、".join(map(str, unfilled)))

    result = {
        "case_id": case_id,
        "status": args.status,
        "candidates": fill.get("candidates", []),
        "families": fill.get("families", {}),
        "extracted_fields": fill.get("extracted_fields", []),
        "evidence_records": fill.get("evidence_records", []),
        "sources": fill.get("sources", []),
        "uncertainty": uncertainty + fill.get("uncertainty", []),
        "change_records": fill.get("change_records", []),
        "output_contract": contract_fields,
    }
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"result": path, "case_id": case_id,
                      "status": args.status,
                      "contract_fields": len(contract_fields),
                      "unfilled": len(unfilled)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
