#!/usr/bin/env python3
"""contract_scaffold.py — 从 case.json 的 output_contract 生成 result.json 骨架。

契约先行：正式动笔之前，先把"平台要什么"编译成一份逐字段的骨架文件，
之后每个阶段只回填、不重构，保证任何时刻中断都有契约合法的半成品。

用法：
  python3 contract_scaffold.py --case /input/case.json \
      --out /app/output/result.json --report /app/work/contract_fields.md

case.json 兼容三种 output_contract 形态：
  1. 对象：{"field_name": <规范或说明>, ...}   —— 取键为字段名；
  2. 数组：["field_name", ...] 或 [{"name": "field_name"}, ...]；
  3. 字符串：按行/逗号切分出字段名。
骨架中 case_id 立即照抄 case.json；契约字段置 null；
补 status="in_progress" 与 provenance（若契约未声明这两个字段，也加入并
在报告中注明为运行状态字段）。
仅依赖 Python 3.8+ 标准库。
"""
import argparse
import json
import sys
from pathlib import Path


def extract_fields(contract):
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        fields = []
        for item in contract:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict) and "name" in item:
                fields.append(str(item["name"]))
            else:
                fields.append(str(item))
        return fields
    if isinstance(contract, str):
        raw = contract.replace("\n", ",").split(",")
        return [t.strip() for t in raw if t.strip()]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    case_id = case.get("case_id")
    if case_id is None:
        print("case.json 缺少 case_id", file=sys.stderr)
        return 2
    contract = case.get("output_contract")
    if contract is None:
        print("case.json 缺少 output_contract", file=sys.stderr)
        return 2
    fields = extract_fields(contract)
    if not fields:
        print("无法从 output_contract 解析出任何字段", file=sys.stderr)
        return 2

    skeleton = {"case_id": case_id}
    for f in fields:
        if f == "case_id":
            continue
        skeleton[f] = None
    extra = []
    for runtime_field, default in (("status", "in_progress"),
                                   ("provenance", {
                                       "generated_by": "contract_scaffold.py",
                                       "note": "骨架；契约字段待回填"})):
        if runtime_field not in skeleton:
            skeleton[runtime_field] = default
            extra.append(runtime_field)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    rep = ["# 契约字段清单", "",
           "case_id：`%s`" % case_id, "",
           "output_contract 声明字段（%d 个，逐字照抄）：" % len(fields), ""]
    rep += ["- `%s`" % f for f in fields]
    if extra:
        rep += ["", "运行状态字段（契约未声明，为过程管理而加）：", ""]
        rep += ["- `%s`" % f for f in extra]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(rep) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": case_id, "contract_fields": len(fields),
                      "runtime_fields_added": extra}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
