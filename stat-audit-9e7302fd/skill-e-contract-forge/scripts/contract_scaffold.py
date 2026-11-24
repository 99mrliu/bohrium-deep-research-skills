#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_scaffold.py — 输出契约编译器（bundle E / contract-forge-audit）。

读取真实 case.json，提取 case_id 与 output_contract，生成：
  (a) contract_schema.json  —— 归一化契约 schema；
  (b) result.json           —— 骨架：case_id 已填、每个契约字段置 "PENDING::<field>"
                              哨兵、status="partial"、sources=[]、uncertainty 已初始化。

若 case.json 中找不到契约，则生成明确标注 fallback 的通用 schema
（case_id / audit_report / evidence / status / sources / uncertainty）。

仅依赖 Python 标准库。case.json 不可读时以非零码退出。
"""
import argparse
import json
import os
import sys

CONTRACT_KEYS = ("output_contract", "outputContract", "contract")

FALLBACK_FIELDS = {
    "case_id": {"type": "string", "required": True,
                "description": "案例标识（fallback 契约）"},
    "audit_report": {"type": "string", "required": True,
                     "description": "审查报告正文（fallback 契约）"},
    "evidence": {"type": "array", "required": True,
                 "description": "证据列表（fallback 契约）"},
    "status": {"type": "string", "required": True,
               "description": "complete/partial/failed（fallback 契约）"},
    "sources": {"type": "array", "required": True,
                "description": "实际读取过的来源文件（fallback 契约）"},
    "uncertainty": {"type": "string", "required": True,
                    "description": "方法局限与不确定度说明（fallback 契约）"},
}

DEFAULT_FINDING_KEYS = ["id", "location", "message"]


def die(msg, code=2):
    print("contract_scaffold: ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def load_case(path):
    if not os.path.isfile(path):
        die("case.json 不存在或不可读: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError) as e:
        die("case.json 读取失败: %s (%s)" % (path, e))
    except json.JSONDecodeError as e:
        die("case.json 不是合法 JSON: %s (line %d col %d)" % (path, e.lineno, e.colno))
    if not isinstance(data, dict):
        die("case.json 顶层必须是 JSON 对象")
    return data


def find_contract(case):
    """在顶层或一层嵌套内寻找契约定义。返回 (raw_contract, where) 或 (None, None)。"""
    for key in CONTRACT_KEYS:
        if isinstance(case.get(key), (dict, list)):
            return case[key], key
    for top_key, val in case.items():
        if isinstance(val, dict):
            for key in CONTRACT_KEYS:
                if isinstance(val.get(key), (dict, list)):
                    return val[key], "%s.%s" % (top_key, key)
    return None, None


def normalize_entry(name, entry):
    """把单个契约条目归一化为 {type, required, description, item_required_keys}。"""
    if isinstance(entry, str):
        return {"type": entry, "required": True, "description": "",
                "item_required_keys": None}
    if not isinstance(entry, dict):
        return {"type": "any", "required": True, "description": "",
                "item_required_keys": None}
    ftype = entry.get("type") or entry.get("field_type") or "any"
    required = entry.get("required")
    if required is None:
        required = entry.get("optional") is not True
    desc = entry.get("description") or entry.get("desc") or ""
    item_keys = (entry.get("item_required_keys")
                 or entry.get("itemKeys")
                 or entry.get("item_fields"))
    norm = {"type": str(ftype), "required": bool(required),
            "description": str(desc), "item_required_keys": None}
    if isinstance(item_keys, list) and item_keys:
        norm["item_required_keys"] = [str(k) for k in item_keys]
    elif "array" in str(ftype).lower() and (
            "finding" in name.lower()
            or str(entry.get("item_type", "")).lower() == "finding"):
        norm["item_required_keys"] = list(DEFAULT_FINDING_KEYS)
    return norm


def normalize_contract(raw):
    """支持 dict-of-fields 与 list-of-entries 两种契约写法。"""
    fields = {}
    if isinstance(raw, dict):
        # 允许一层包装，如 {"fields": {...}} / {"required_fields": [...]}
        for wrap in ("fields", "output_fields", "schema"):
            if isinstance(raw.get(wrap), (dict, list)):
                raw = raw[wrap]
                break
    if isinstance(raw, dict):
        for name, entry in raw.items():
            if name.startswith("_"):
                continue
            fields[str(name)] = normalize_entry(str(name), entry)
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                fields[entry] = normalize_entry(entry, "any")
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if not name:
                    continue
                fields[str(name)] = normalize_entry(str(name), entry)
    return fields


def extract_case_id(case):
    for key in ("case_id", "caseId", "id"):
        if isinstance(case.get(key), str) and case[key]:
            return case[key]
    for val in case.values():
        if isinstance(val, dict):
            for key in ("case_id", "caseId", "id"):
                if isinstance(val.get(key), str) and val[key]:
                    return val[key]
    return "UNKNOWN_CASE_ID"


def build_skeleton(case_id, fields):
    result = {"case_id": case_id, "status": "partial"}
    for name in fields:
        if name in ("case_id", "status"):
            continue
        result[name] = "PENDING::%s" % name
    if "sources" not in result:
        result["sources"] = []
    if "uncertainty" not in result:
        result["uncertainty"] = "PENDING::uncertainty"
    result["pending_reasons"] = {}
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从 case.json 编译输出契约：生成 contract_schema.json 与 result.json 骨架。")
    ap.add_argument("--case", default="/input/case.json",
                    help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--outdir", default=".",
                    help="输出目录（默认当前目录）")
    ap.add_argument("--schema-out", default=None,
                    help="contract_schema.json 输出路径（默认 <outdir>/contract_schema.json）")
    ap.add_argument("--result-out", default=None,
                    help="result.json 输出路径（默认 <outdir>/result.json，已存在则不覆盖）")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的 result.json 骨架")
    args = ap.parse_args(argv)

    case = load_case(args.case)
    case_id = extract_case_id(case)
    raw, where = find_contract(case)
    fallback = raw is None
    if fallback:
        fields = {k: dict(v, item_required_keys=None) for k, v in FALLBACK_FIELDS.items()}
        print("contract_scaffold: WARNING: 未在 case.json 中找到 output_contract，"
              "使用 FALLBACK 通用契约（已在 schema 中标注）。", file=sys.stderr)
    else:
        fields = normalize_contract(raw)
        if not fields:
            die("找到契约位置 %s 但解析后为空，请人工核对 case.json。" % where)
        print("contract_scaffold: 契约来源: %s（%d 个字段）" % (where, len(fields)),
              file=sys.stderr)

    schema = {
        "schema_version": "1.0",
        "generator": "contract-forge-audit/contract_scaffold.py",
        "fallback": fallback,
        "note": ("FALLBACK: case.json 中未找到 output_contract，本 schema 为通用占位契约，"
                 "务必人工复核真实交付要求。" if fallback else
                 "由真实 case.json 的 output_contract 编译而来。"),
        "contract_location": where or "(fallback)",
        "case_id": case_id,
        "fields": fields,
    }

    os.makedirs(args.outdir, exist_ok=True)
    schema_out = args.schema_out or os.path.join(args.outdir, "contract_schema.json")
    result_out = args.result_out or os.path.join(args.outdir, "result.json")

    with open(schema_out, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if os.path.exists(result_out) and not args.force:
        print("contract_scaffold: result.json 已存在，跳过骨架写入（用 --force 覆盖）: %s"
              % result_out, file=sys.stderr)
    else:
        skeleton = build_skeleton(case_id, fields)
        with open(result_out, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("contract_scaffold: 已生成骨架: %s" % result_out, file=sys.stderr)

    print("contract_scaffold: 已生成 schema: %s (fallback=%s)" % (schema_out, fallback),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
