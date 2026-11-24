#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_contract.py — 工作流步骤 0：解析 case.json 的输出契约并脚手架 result 骨架。

用法:
    python3 parse_contract.py <case.json> <out_dir>

产出（写入 <out_dir>）:
    contract_checklist.json  字段清单（字段名/期望类型/是否必填/形状备注）+ 输入文件 SHA-256
    result.skeleton.json     诚实骨架：case_id + 全部契约字段=null + status="partial"
                             + 空 sources + 非空 uncertainty + 一条 scaffold change_record

设计意图：骨架必须【立即】复制为 /app/output/result.json，使交付自第一分钟起就是
honest partial；此后模型每完成一部分就把中间结论 merge 进去。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

CONTRACT_KEYS = ("output_contract", "outputContract", "output-contract")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_contract(case):
    """在 case.json 顶层（必要时下钻一层）寻找输出契约。返回 (contract, key_path)。"""
    if not isinstance(case, dict):
        return None, None
    for k in CONTRACT_KEYS:
        if k in case:
            return case[k], k
    for k, v in case.items():
        if "contract" in str(k).lower():
            return v, k
    for k, v in case.items():
        if isinstance(v, dict):
            for k2 in CONTRACT_KEYS:
                if k2 in v:
                    return v[k2], "%s.%s" % (k, k2)
    return None, None


def _type_of_spec(spec):
    """从字段规格中提取 (期望类型, 形状备注, 数组元素类型)。"""
    if isinstance(spec, str):
        return spec, "", None
    if not isinstance(spec, dict):
        return "any", "", None
    t = spec.get("type") or spec.get("expected_type") or "any"
    note, items_t = "", None
    if t == "array" and isinstance(spec.get("items"), dict):
        items_t = spec["items"].get("type", "any")
        note = "array<%s>" % items_t
    elif t == "object" and isinstance(spec.get("properties"), dict):
        note = "object{%s}" % ", ".join(sorted(spec["properties"].keys()))
    return t, note, items_t


def extract_fields(contract):
    """容忍三种契约形态：
    1. list[str|dict]                 —— [{"name":..,"type":..,"required":..}, ...]
    2. dict{field: spec|"type"}       —— 平铺字段映射
    3. JSON-Schema properties 形态     —— {"properties": {...}, "required": [...]}
    返回 [{field, expected_type, required, shape, items_type}, ...]。
    """
    fields = []
    if isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields.append({"field": item, "expected_type": "any",
                               "required": True, "shape": "list[str]", "items_type": None})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if not name:
                    continue
                t, note, items_t = _type_of_spec(item)
                fields.append({"field": name, "expected_type": t,
                               "required": bool(item.get("required", True)),
                               "shape": note or "list[dict]", "items_type": items_t})
    elif isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            req = set(contract.get("required") or [])
            for name, spec in contract["properties"].items():
                t, note, items_t = _type_of_spec(spec)
                fields.append({"field": name, "expected_type": t,
                               "required": (name in req) if req else True,
                               "shape": note or "properties", "items_type": items_t})
        elif isinstance(contract.get("fields"), list):
            return extract_fields(contract["fields"])
        else:
            for name, spec in contract.items():
                t, note, items_t = _type_of_spec(spec)
                req = bool(spec.get("required", True)) if isinstance(spec, dict) else True
                fields.append({"field": name, "expected_type": t, "required": req,
                               "shape": note or "dict", "items_type": items_t})
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 case.json 输出契约，生成 contract_checklist.json 与 result.skeleton.json")
    ap.add_argument("case_json", help="case.json 路径")
    ap.add_argument("out_dir", help="输出目录（通常为 /app/output 或示例 output/）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.case_json):
        print("错误：case.json 不存在: %s" % args.case_json, file=sys.stderr)
        return 2
    os.makedirs(args.out_dir, exist_ok=True)

    case = load_json(args.case_json)
    contract, ckey = find_contract(case)
    if contract is None:
        print("错误：未在 case.json 中找到 output_contract（也未找到任何 *contract* 键）",
              file=sys.stderr)
        return 2
    fields = extract_fields(contract)
    if not fields:
        print("错误：output_contract 中未解析出任何字段", file=sys.stderr)
        return 2

    case_id = case.get("case_id") or case.get("id") or "UNKNOWN"
    now = datetime.datetime.now().isoformat(timespec="seconds")

    input_hashes = {
        "case.json": {"path": os.path.abspath(args.case_json),
                      "sha256": sha256_file(args.case_json)}
    }
    task_md = os.path.join(os.path.dirname(os.path.abspath(args.case_json)), "task.md")
    if os.path.isfile(task_md):
        input_hashes["task.md"] = {"path": task_md, "sha256": sha256_file(task_md)}

    checklist = {
        "case_id": case_id,
        "contract_key": ckey,
        "generated_at": now,
        "fields": fields,
        "input_hashes": input_hashes,
    }
    checklist_path = os.path.join(args.out_dir, "contract_checklist.json")
    with open(checklist_path, "w", encoding="utf-8") as f:
        json.dump(checklist, f, ensure_ascii=False, indent=2)

    skeleton = {"case_id": case_id}
    for fd in fields:
        if fd["field"] in ("status", "sources", "uncertainty", "change_record", "case_id"):
            continue
        skeleton[fd["field"]] = None
    skeleton["status"] = "partial"
    skeleton["sources"] = []
    skeleton["uncertainty"] = ["骨架文件：实质审查尚未完成，全部契约字段待填充（步骤 0 脚手架）。"]
    skeleton["change_record"] = [{
        "ts": now, "actor": "parse_contract.py", "action": "scaffold",
        "detail": "契约脚手架：全部契约字段置 null，状态置 partial（诚实起点）。"}]
    skel_path = os.path.join(args.out_dir, "result.skeleton.json")
    with open(skel_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    print("case_id: %s" % case_id)
    print("契约键: %s；共 %d 个字段：" % (ckey, len(fields)))
    for fd in fields:
        req = "必填" if fd["required"] else "可选"
        print("  - %s <%s> %s %s" % (fd["field"], fd["expected_type"], req, fd["shape"]))
    for name, info in input_hashes.items():
        print("输入哈希 %s sha256=%s" % (name, info["sha256"]))
    print("已写出: %s" % checklist_path)
    print("已写出: %s" % skel_path)
    print("下一步：立即将 result.skeleton.json 复制为 /app/output/result.json"
          "（自第一分钟起保持 honest partial）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
