#!/usr/bin/env python3
"""contract_probe.py — 合同探测（contract probe）。

从 case.json / task.md 的多种可能形态中提取 output_contract 字段清单与 case_id，
处理合同缺失/变形（嵌套、列表、自由文本描述）并在 spec 中留痕（warnings/provenance）。

退出码：0=成功（可带 warnings）；2=用法/IO/内部错误；3=合同不可用（如 case_id 缺失）。
幂等：同一输入重复运行产生相同的 contract_spec.json（generated_at 除外）。

仅使用 Python 标准库。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

# 运行时最低保障字段：即使业务合同探测失败，result.json 也必须包含这些字段。
RUNTIME_MINIMUM_FIELDS = ["case_id", "status", "sources", "uncertainty", "change_records"]

CASE_ID_KEYS = {"case_id", "caseid", "case-id"}
CONTRACT_KEYS = {"output_contract", "contract", "deliverable_contract", "outputcontract"}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_key_recursive(obj, names):
    """在任意嵌套 dict/list 中深度优先查找第一个命中 names（小写）的键。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in names:
                return v
        for v in obj.values():
            r = find_key_recursive(v, names)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = find_key_recursive(item, names)
            if r is not None:
                return r
    return None


def normalize_field_name(name):
    """字段名归一化：去反引号/空白/首尾符号。"""
    name = str(name).strip().strip("`").strip()
    name = re.sub(r"\s+", "_", name)
    return name


def fields_from_contract_value(value, warnings, source_tag):
    """把多种形态的合同值统一成字段名列表。"""
    fields = []
    if value is None:
        return fields
    if isinstance(value, dict):
        # 形态 A：{"fields": [...]} / {"required": [...]}
        for wrapper in ("fields", "required", "required_fields", "properties"):
            if wrapper in value:
                inner = value[wrapper]
                if isinstance(inner, dict):  # JSON Schema 风格 properties
                    fields.extend(normalize_field_name(k) for k in inner.keys())
                    warnings.append(f"contract_shape: dict.{wrapper}(properties) from {source_tag}")
                    return dedup(fields)
                return dedup(fields_from_contract_value(inner, warnings, source_tag + "." + wrapper))
        # 形态 B：{"field_name": "描述", ...} —— 键即字段
        for k, v in value.items():
            if isinstance(v, (str, int, float, bool)) or v is None or isinstance(v, (dict, list)):
                fields.append(normalize_field_name(k))
        warnings.append(f"contract_shape: dict-keys-as-fields from {source_tag}")
        return dedup(fields)
    if isinstance(value, list):
        # 形态 C/D：["a","b"] 或 [{"field": "a", ...}, {"name": "b"}]
        for item in value:
            if isinstance(item, str):
                fields.append(normalize_field_name(item))
            elif isinstance(item, dict):
                picked = None
                for kk in ("field", "name", "key", "id"):
                    if kk in item and isinstance(item[kk], str):
                        picked = item[kk]
                        break
                if picked is None and item:
                    picked = next(iter(item.keys()))
                if picked is not None:
                    fields.append(normalize_field_name(picked))
                else:
                    warnings.append(f"unrecognized_field_entry_skipped: {item!r}")
            else:
                warnings.append(f"unrecognized_field_entry_skipped: {item!r}")
        warnings.append(f"contract_shape: list from {source_tag}")
        return dedup(fields)
    if isinstance(value, str):
        # 形态 E：自由文本/逗号分隔
        parts = re.split(r"[,\n;；，、]", value)
        for p in parts:
            p = normalize_field_name(p)
            if p and re.match(r"^[A-Za-z_][\w.-]*$", p):
                fields.append(p)
        warnings.append(f"contract_shape: free-text string from {source_tag}")
        return dedup(fields)
    warnings.append(f"unrecognized_contract_value_type: {type(value).__name__}")
    return fields


def dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


HEADING_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
FIELD_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*`?([A-Za-z_][\w-]*)`?\s*[:：—\-]")
TABLE_ROW_RE = re.compile(r"^\|\s*`?([A-Za-z_][\w-]*)`?\s*\|")
CASE_ID_TEXT_RE = re.compile(r"case[_\- ]?id\s*[:：=]\s*`?([A-Za-z0-9][\w.-]*)`?", re.IGNORECASE)


def probe_task_md(text, warnings):
    """从 task.md 自由文本兜底提取字段与 case_id。"""
    fields, case_id = [], None
    m = CASE_ID_TEXT_RE.search(text)
    if m:
        case_id = m.group(1)
    lines = text.splitlines()
    in_section = False
    section_hit = False
    for line in lines:
        h = HEADING_RE.match(line)
        if h:
            title = h.group(1).lower()
            in_section = any(
                kw in title
                for kw in ("output_contract", "输出合同", "交付合同", "交付物", "result.json", "输出要求")
            )
            section_hit = section_hit or in_section
            continue
        if in_section:
            fm = FIELD_LINE_RE.match(line)
            if fm:
                fields.append(normalize_field_name(fm.group(1)))
                continue
            tm = TABLE_ROW_RE.match(line)
            if tm and tm.group(1).lower() not in ("field", "字段", "name"):
                fields.append(normalize_field_name(tm.group(1)))
    if fields:
        warnings.append("contract_shape: free-text markdown section from task.md")
    elif section_hit:
        warnings.append("task_md_section_found_but_no_fields_parsed")
    return dedup(fields), case_id


def main(argv=None):
    ap = argparse.ArgumentParser(description="探测 output_contract 字段清单与 case_id")
    ap.add_argument("--input", default="/input", help="输入目录（含 case.json / task.md）")
    ap.add_argument("--work", default="/app/work", help="中间产物目录（写出 contract_spec.json）")
    ap.add_argument("--case-json", default=None, help="覆盖 case.json 路径")
    ap.add_argument("--task-md", default=None, help="覆盖 task.md 路径")
    ap.add_argument("--out", default=None, help="覆盖 spec 输出路径")
    args = ap.parse_args(argv)

    try:
        import os
        case_json_path = args.case_json or os.path.join(args.input, "case.json")
        task_md_path = args.task_md or os.path.join(args.input, "task.md")
        out_path = args.out or os.path.join(args.work, "contract_spec.json")

        warnings, provenance = [], {"case_id_source": None, "fields_source": None}
        case_id, fields = None, []

        # --- 1) case.json 优先 ---
        case_data = None
        if os.path.isfile(case_json_path):
            try:
                case_data = load_json(case_json_path)
            except json.JSONDecodeError as e:
                warnings.append(f"case_json_parse_error: {e}")
        else:
            warnings.append(f"case_json_missing: {case_json_path}")

        if case_data is not None:
            cid = find_key_recursive(case_data, CASE_ID_KEYS)
            if cid is None and isinstance(case_data, dict) and isinstance(case_data.get("id"), str):
                cid = case_data["id"]
                warnings.append("case_id_from_top_level_id")
            if isinstance(cid, (str, int)):
                case_id = str(cid)
                provenance["case_id_source"] = "case.json"
            contract_val = find_key_recursive(case_data, CONTRACT_KEYS)
            if contract_val is not None:
                fields = fields_from_contract_value(contract_val, warnings, "case.json")
                if fields:
                    provenance["fields_source"] = "case.json"
            else:
                warnings.append("no_output_contract_key_in_case_json")

        # --- 2) task.md 兜底 ---
        if os.path.isfile(task_md_path):
            with open(task_md_path, "r", encoding="utf-8") as f:
                task_text = f.read()
            md_fields, md_case_id = probe_task_md(task_text, warnings)
            if not fields and md_fields:
                fields = md_fields
                provenance["fields_source"] = "task.md"
            if case_id is None and md_case_id:
                case_id = md_case_id
                provenance["case_id_source"] = "task.md"
        else:
            warnings.append(f"task_md_missing: {task_md_path}")

        # --- 3) 合同缺失时的最低保障兜底 ---
        if not fields:
            fields = list(RUNTIME_MINIMUM_FIELDS)
            provenance["fields_source"] = "runtime_minimum_fallback"
            warnings.append(
                "contract_missing_fallback_runtime_minimum: 未从输入探测到业务合同字段，"
                "回退到运行时最低保障字段；请人工确认这是否符合评测要求"
            )

        # 结构化字段不计入“业务合同字段”，但始终要求存在
        business_fields = [f for f in fields if f not in ("case_id", "status")]

        spec = {
            "spec_version": "1.0",
            "generated_at": utcnow(),
            "generated_by": "contract_probe.py",
            "case_id": case_id,
            "contract_fields": business_fields,
            "runtime_minimum_fields": RUNTIME_MINIMUM_FIELDS,
            "provenance": provenance,
            "warnings": warnings,
        }

        if case_id is None:
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(spec, f, ensure_ascii=False, indent=2)
            print("ERROR: case_id 无法从 case.json/task.md 探测，合同不可用", file=sys.stderr)
            return 3

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

        print(f"OK: case_id={case_id} fields={len(business_fields)} -> {out_path}")
        for w in warnings:
            print(f"WARN: {w}", file=sys.stderr)
        return 0
    except SystemExit:
        raise
    except Exception as e:  # 顶层兜底：任何意外都以退出码 2 失败
        print(f"FATAL: contract_probe 内部错误: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
