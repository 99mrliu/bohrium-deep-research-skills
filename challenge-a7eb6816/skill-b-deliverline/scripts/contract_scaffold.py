#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_scaffold.py — output_contract 契约定位与保底 result.json 脚手架生成。

用途
----
读取 case.json，递归定位 output_contract（兼容 dict / list / 嵌套 /
字符串 schema 描述等形态），生成：

  1. contract_map.json —— 字段路径、类型、是否必填（供 deliverable_gate.py 使用）
  2. result.json       —— 保底脚手架：case_id 原样保留，全部契约字段以
     诚实占位值填充，status=partial，notes 说明占位原因。

设计原则：任何时刻输出目录中都存在结构合法的 result.json——即使契约
缺失或形态异常，也先写出最小合法脚手架再报错退出，绝不空手而归。

退出码
------
  0  成功：契约已定位，contract_map.json 与 result.json 均已写出
  2  输入缺失或 case.json 不是合法 JSON（不写出任何文件）
  3  未定位到 output_contract：仍写出保底 result.json 与空 contract_map.json
  4  输出目录写入失败

依赖：Python 3 标准库。输出确定性（不含时间戳等易变量）。
"""
import argparse
import json
import os
import re
import sys

# 已知契约顶层键名（按优先级）
CONTRACT_KEYS = ("output_contract", "outputContract", "output-contract",
                 "contract", "output_schema", "result_contract")

TYPE_ALIASES = {
    "str": "string", "string": "string", "text": "string",
    "int": "integer", "integer": "integer", "long": "integer",
    "float": "number", "double": "number", "number": "number", "decimal": "number",
    "bool": "boolean", "boolean": "boolean",
    "list": "array", "array": "array", "arr": "array",
    "dict": "object", "object": "object", "map": "object",
    "any": "any", "unknown": "any",
}

# 诚实占位值：类型允许的最“空”值，配合 notes 说明，不伪造内容
PLACEHOLDERS = {
    "string": "",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "array": [],
    "object": {},
    "any": None,
}


def norm_type(t):
    """类型名归一化；无法识别时返回 'any'。"""
    if not isinstance(t, str):
        return "any"
    return TYPE_ALIASES.get(t.strip().lower(), "any")


def find_contract(obj, path="$"):
    """在 case 结构中递归定位 output_contract。返回 (contract, location) 或 (None, None)。"""
    if isinstance(obj, dict):
        for k in CONTRACT_KEYS:
            if k in obj:
                return obj[k], (path + "." + k if path != "$" else k)
        # 递归深入 dict 值与 list 元素
        for k, v in obj.items():
            found, loc = find_contract(v, "%s.%s" % (path, k))
            if found is not None:
                return found, loc
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found, loc = find_contract(item, "%s[%d]" % (path, i))
            if found is not None:
                return found, loc
    return None, None


def parse_schema_line(line):
    """解析字符串形态契约中的一行，如：
      - title: string (必填)
      word_count: integer, required
      deliverables (array<string>)
    返回 {path,type,required} 或 None。"""
    s = line.strip().strip(",;")
    if not s or s.startswith("#"):
        return None
    m = re.match(r'^[-*•\d.、)\s]*[`"\']?([A-Za-z_][\w.\-]*)[`"\']?', s)
    if not m:
        return None
    name = m.group(1)
    rest = s[m.end():]
    # 在余下文本中寻找类型关键词
    tm = re.search(r'\b(str|string|text|int|integer|long|float|double|number|'
                   r'decimal|bool|boolean|list|array|dict|object|map|any)\b',
                   rest, re.IGNORECASE)
    if not tm:
        return None
    t = norm_type(tm.group(1))
    required = bool(re.search(r'required|必填|必须|mandatory', rest, re.IGNORECASE))
    return {"path": name, "type": t, "required": required}


def parse_contract(contract):
    """把各种形态的契约解析为统一的字段列表。

    返回 (fields, shape)。fields 元素: {path, type, required, enum?, description?}
    """
    # 形态 A：JSON Schema 风格 dict（含 properties）
    if isinstance(contract, dict) and isinstance(contract.get("properties"), dict):
        fields = []

        def rec(props, prefix, required_list):
            for name, spec in props.items():
                p = name if not prefix else prefix + "." + name
                req = name in required_list
                if isinstance(spec, dict):
                    f = {"path": p, "type": norm_type(spec.get("type", "any")),
                         "required": req}
                    if isinstance(spec.get("enum"), list):
                        f["enum"] = spec["enum"]
                    if isinstance(spec.get("description"), str):
                        f["description"] = spec["description"]
                    fields.append(f)
                    if isinstance(spec.get("properties"), dict):
                        rec(spec["properties"], p, spec.get("required", []))
                else:
                    fields.append({"path": p, "type": norm_type(spec),
                                   "required": req})

        rec(contract["properties"], "",
            contract.get("required", []) if isinstance(contract.get("required"), list) else [])
        return fields, "json_schema"

    # 形态 B：扁平 dict，字段名 -> 类型字符串 或 {type, required}
    if isinstance(contract, dict):
        fields = []
        for name, spec in contract.items():
            if name in ("type", "required", "description", "title"):
                continue  # 可能是 schema 元信息而非字段
            if isinstance(spec, str):
                fields.append({"path": name, "type": norm_type(spec),
                               "required": False})
            elif isinstance(spec, dict):
                f = {"path": name, "type": norm_type(spec.get("type", "any")),
                     "required": bool(spec.get("required", False))}
                if isinstance(spec.get("enum"), list):
                    f["enum"] = spec["enum"]
                fields.append(f)
        if fields:
            return fields, "flat_dict"
        return [], "unknown_dict"

    # 形态 C：字段描述列表 [{name,type,required}, ...] 或字符串列表
    if isinstance(contract, list):
        fields = []
        for item in contract:
            if isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("path")
                if not name:
                    continue
                f = {"path": str(name),
                     "type": norm_type(item.get("type", "any")),
                     "required": bool(item.get("required", False))}
                if isinstance(item.get("enum"), list):
                    f["enum"] = item["enum"]
                fields.append(f)
            elif isinstance(item, str):
                f = parse_schema_line(item)
                if f:
                    fields.append(f)
        return fields, "descriptor_list"

    # 形态 D：字符串 schema 描述（逐行解析）
    if isinstance(contract, str):
        fields = []
        for line in contract.splitlines():
            f = parse_schema_line(line)
            if f:
                fields.append(f)
        return fields, "string_schema"

    return [], "unknown"


def set_path(obj, path, value):
    """按点分路径写入嵌套 dict。"""
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def build_scaffold(fields, case_id, contract_found):
    """生成保底 result.json 脚手架。

    - case_id 原样保留；
    - 全部契约字段（含可选字段）以类型允许的空值占位；
    - status=partial；notes 如实说明占位原因。
    """
    result = {}
    enum_by_path = {f["path"]: f.get("enum") for f in fields if f.get("enum")}
    for f in fields:
        if f["path"] in ("case_id", "status", "notes"):
            continue  # 后面统一处理
        set_path(result, f["path"], PLACEHOLDERS.get(f["type"]))
    if case_id is not None:
        result["case_id"] = case_id
    # status：优先 partial；若契约枚举不含 partial 则退到枚举首值并说明
    status_enum = enum_by_path.get("status")
    if status_enum and "partial" not in status_enum:
        result["status"] = status_enum[0]
        status_note = ("注意：契约 status 枚举不含 'partial'，已退用枚举首值 "
                       "'%s'，实际进度仍为未完成。" % status_enum[0])
    else:
        result["status"] = "partial"
        status_note = ""
    reasons = []
    if not contract_found:
        reasons.append("未在 case.json 中定位到 output_contract，本脚手架仅含最小合法结构")
    else:
        reasons.append("契约字段以诚实占位值填充（空串/0/false/空数组），尚未经写作流程回填")
    reasons.append("status=partial 表示交付未完成")
    if status_note:
        reasons.append(status_note)
    result["notes"] = "【保底脚手架】由 contract_scaffold.py 自动生成：" + "；".join(reasons) + "。"
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="定位 output_contract 并生成 contract_map.json 与保底 result.json")
    ap.add_argument("--case", required=True, help="case.json 路径（只读）")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--map-name", default="contract_map.json", help="契约映射文件名")
    ap.add_argument("--result-name", default="result.json", help="脚手架文件名")
    args = ap.parse_args(argv)

    # --- 读输入 ---
    if not os.path.isfile(args.case):
        print("ERROR: 输入不存在: %s" % args.case, file=sys.stderr)
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, ValueError) as e:
        print("ERROR: case.json 读取/解析失败: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(case, dict):
        print("ERROR: case.json 顶层不是对象", file=sys.stderr)
        return 2

    case_id = case.get("case_id")
    contract, location = find_contract(case)
    if contract is not None:
        fields, shape = parse_contract(contract)
        if contract is not None and not fields:
            # 找到了契约键但解析不出字段：如实记录
            shape = shape + "（解析不到字段，按契约缺失处理）"
            contract_found = False
        else:
            contract_found = True
    else:
        fields, shape, location, contract_found = [], "not_found", None, False

    contract_map = {
        "case_id": case_id,
        "contract_found": contract_found,
        "contract_location": location,
        "contract_shape": shape,
        "field_count": len(fields),
        "fields": fields,
    }
    scaffold = build_scaffold(fields, case_id, contract_found)

    # --- 写输出 ---
    try:
        os.makedirs(args.outdir, exist_ok=True)
        map_path = os.path.join(args.outdir, args.map_name)
        result_path = os.path.join(args.outdir, args.result_name)
        with open(map_path, "w", encoding="utf-8") as fh:
            json.dump(contract_map, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(scaffold, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as e:
        print("ERROR: 输出写入失败: %s" % e, file=sys.stderr)
        return 4

    print("contract_map: %s（%d 个字段，形态=%s）" % (map_path, len(fields), shape))
    print("scaffold:     %s" % result_path)
    if not contract_found:
        print("WARN: 未定位到 output_contract，已写出最小保底 result.json", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
