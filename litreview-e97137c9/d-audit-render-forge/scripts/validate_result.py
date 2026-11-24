#!/usr/bin/env python3
"""validate_result.py — result.json 手写 schema 校验（bundle D 签名脚本 3）。

按 schemas/result.schema.json 校验 result.json，不依赖 jsonschema 库：
  - 必填键存在、值类型符合（string/number/integer/boolean/array/object/null/any，
    type 可为单值或列表，如 ["string","null"]）；
  - status / strength / tier 枚举；
  - evidence_matrix、sources 数组元素的必填字段；
  - output_contract 逐字段完备（与 work/case_profile.json 对照：list 取元素、dict 取键）；
  - result.case_id 与 case_profile.case_id 一致。
产物：out/validation_report.json；任何错误 → 退出码 1。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(HERE, "..", "schemas", "result.schema.json")

TYPE_MAP = {
    "string": str, "number": (int, float), "integer": int,
    "boolean": bool, "array": list, "object": dict, "null": type(None),
}


def type_name(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, str):
        return "string"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    if v is None:
        return "null"
    return type(v).__name__


def check_type(value, spec):
    types = spec if isinstance(spec, list) else [spec]
    if "any" in types:
        return True
    for t in types:
        py = TYPE_MAP.get(t)
        if py is None:
            continue
        if t == "integer" and isinstance(value, bool):
            continue
        if t == "number" and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate_node(value, schema, path, errors):
    if not isinstance(schema, dict):
        return
    if "type" in schema and not check_type(value, schema["type"]):
        errors.append(f"{path or '$'}: 类型错误，期望 {schema['type']}，实际 {type_name(value)}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or '$'}: 值 {value!r} 不在枚举 {schema['enum']} 内")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errors.append(f"{path or '$'}: 缺必填键 '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                validate_node(value[k], sub, f"{path}.{k}" if path else k, errors)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate_node(item, schema["items"], f"{path}[{i}]", errors)


def contract_fields(contract):
    if isinstance(contract, list):
        return [str(x) for x in contract]
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    return []


def validate(schema_path, result_path, case_profile_path, report_path):
    errors, checks = [], []
    schema = json.load(open(schema_path, encoding="utf-8"))
    try:
        result = json.load(open(result_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = None
        errors.append(f"result.json 无法读取或解析：{exc}")

    if isinstance(result, dict):
        validate_node(result, schema, "", errors)
        checks.append("schema: required/types/enum/items")
    elif result is not None:
        errors.append("result.json 顶层必须是 object")

    profile = {}
    if case_profile_path and os.path.exists(case_profile_path):
        profile = json.load(open(case_profile_path, encoding="utf-8"))

    # output_contract 逐字段完备
    fields = contract_fields(profile.get("output_contract"))
    if fields and isinstance(result, dict):
        missing = [f for f in fields if f not in result]
        if missing:
            errors.append(f"output_contract 字段未镜像到 result.json：{missing}")
        checks.append(f"contract_mirror: {len(fields)} 字段，缺失 {len(missing)}")

    # case_id 一致
    if isinstance(result, dict) and profile.get("case_id"):
        if result.get("case_id") != profile["case_id"]:
            errors.append(f"case_id 不一致：result={result.get('case_id')!r} "
                          f"case={profile['case_id']!r}")
        checks.append("case_id 一致性")

    report = {
        "ok": not errors,
        "errors": errors,
        "checks_performed": checks,
        "schema": schema.get("schema_name"), "schema_version": schema.get("version"),
        "result_file": result_path,
        "contract_fields": fields,
    }
    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": report["ok"], "errors": len(errors)}, ensure_ascii=False))
    for e in errors:
        print(f"  [validate] {e}", file=sys.stderr)
    return 0 if report["ok"] else 1


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--schema", default=DEFAULT_SCHEMA)
    ap.add_argument("--case-profile", default=None)
    ap.add_argument("--report", required=True, help="validation_report.json 输出路径")
    args = ap.parse_args(argv)
    sys.exit(validate(args.schema, args.result, args.case_profile, args.report))


if __name__ == "__main__":
    main(sys.argv[1:])
