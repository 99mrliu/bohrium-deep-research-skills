#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_extract.py — output_contract 抽取与 result.json 脚手架（标准库）。

从 case.json 中递归定位 output_contract（兼容 dict/list 两种形态与嵌套路径），
生成：
  contract.json          规范化的合同：每个字段的路径、类型提示、描述
  result.scaffold.json   带全部字段占位的 result.json 骨架
                         （status=in_progress，case_id 已填，其余为 null）

设计意图：在任何数据处理**之前**把交付合同钉死，保证"任何时刻都有结构合法的
result.json 可交付"；字段值由后续流程逐步填入，最后由 contract_verify.py 验收。
退出码：0 正常；2 参数/文件错误；3 未找到 output_contract（仍产出 case_id 骨架）。
"""
import argparse
import json
import os
import sys

TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean",
            "list": "array", "dict": "object"}


def find_contract(obj, path="$"):
    """深度优先找 output_contract 键；返回 (路径, 内容) 或 None。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("output_contract", "outputcontract", "outputs_contract"):
                return ("%s.%s" % (path, k), v)
        for k, v in obj.items():
            r = find_contract(v, "%s.%s" % (path, k))
            if r:
                return r
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            r = find_contract(v, "%s[%d]" % (path, i))
            if r:
                return r
    return None


def normalize_fields(contract):
    """把合同规范化为 [{path, name, type, description}]。"""
    fields = []

    def walk(node, prefix):
        if isinstance(node, dict):
            is_leaf_spec = any(k in node for k in ("type", "description", "desc",
                                                   "required", "format")) \
                and not any(isinstance(v, (dict, list)) and k not in (
                    "type", "description", "desc", "required", "format",
                    "example", "items", "properties")
                    for k, v in node.items())
            if "fields" in node and isinstance(node["fields"], (dict, list)):
                walk(node["fields"], prefix)
                return
            if is_leaf_spec:
                fields.append({
                    "path": prefix or "result",
                    "name": prefix.split(".")[-1] if prefix else "result",
                    "type": node.get("type", "any"),
                    "required": node.get("required", True),
                    "description": node.get("description", node.get("desc", ""))})
                return
            for k, v in node.items():
                walk(v, "%s.%s" % (prefix, k) if prefix else k)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    fields.append({"path": item, "name": item, "type": "any",
                                   "required": True, "description": ""})
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("field") or item.get("path")
                    if name:
                        fields.append({"path": name, "name": name.split(".")[-1],
                                       "type": item.get("type", "any"),
                                       "required": item.get("required", True),
                                       "description": item.get(
                                           "description", item.get("desc", ""))})
    walk(contract, "")
    return fields


def placeholder(ftype):
    return {"string": "", "integer": 0, "number": 0.0, "boolean": False,
            "array": [], "object": {}}.get(ftype, None)


def scaffold(fields, case_id):
    root = {"case_id": case_id, "status": "in_progress"}
    for f in fields:
        parts = f["path"].split(".")
        node = root
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = placeholder(f["type"])
    return root


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--out", required=True, help="产物目录（contract.json 等）")
    ap.add_argument("--scaffold-out", default=None,
                    help="result.json 骨架写入路径（默认 <out>/result.scaffold.json）")
    args = ap.parse_args()
    try:
        case = json.load(open(args.case, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: case.json 不可读: %s" % e, file=sys.stderr)
        sys.exit(2)
    os.makedirs(args.out, exist_ok=True)
    case_id = (case.get("case_id") or case.get("id") or case.get("caseId")
               or "UNKNOWN_CASE_ID")
    found = find_contract(case)
    status = {"case_id": case_id}
    if not found:
        status["warning"] = "未找到 output_contract；骨架仅含 case_id/status"
        fields, cpath = [], None
        rc = 3
    else:
        cpath, contract = found
        fields = normalize_fields(contract)
        rc = 0
    doc = {"case_id": case_id, "contract_path": cpath, "fields": fields,
           "field_count": len(fields)}
    with open(os.path.join(args.out, "contract.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    scaf = scaffold(fields, case_id)
    scaf_path = args.scaffold_out or os.path.join(args.out, "result.scaffold.json")
    with open(scaf_path, "w", encoding="utf-8") as f:
        json.dump(scaf, f, ensure_ascii=False, indent=2)
    status.update({"fields": len(fields), "scaffold": os.path.abspath(scaf_path)})
    print(json.dumps(status, ensure_ascii=False))
    sys.exit(rc)


if __name__ == "__main__":
    main()
