#!/usr/bin/env python3
"""contract_scan.py — 动态解析 case.json 的 output_contract 字段集，生成 contract.json。

运行时动态读取字段集，不假设固定字段名。兼容三种形态：
  1. list-of-str        : ["answer_summary", ...]
  2. list-of-obj        : [{"name": ..., "type": ..., "required": ...}, ...]
  3. dict               : {"answer_summary": "string"} 或 {"answer_summary": {"type": ..., "required": ...}}
缺 output_contract 时 degraded=true，仅保证 case_id。畸形输入一律降级，绝不崩溃。
仅使用标准库（python3 >= 3.8）。原子写，确定性输出（sort_keys）。
"""
import argparse
import json
import os
import sys
import tempfile

VALID_TYPES = {"string", "number", "integer", "boolean", "array", "object", "any"}


def atomic_write_json(path, obj):
    """原子写 JSON：先写临时文件再 os.replace，避免半截文件。"""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def normalize_type(t):
    if not isinstance(t, str):
        return "any"
    t = t.strip().lower()
    return t if t in VALID_TYPES else "any"


def _field(name, type_guess, required):
    return {"name": name, "type_guess": type_guess,
            "required": bool(required), "filled_by": None}


def parse_fields(oc):
    """把三种 output_contract 形态归一化为字段列表。"""
    fields = []
    if isinstance(oc, list):
        for it in oc:
            if isinstance(it, str) and it.strip():
                fields.append(_field(it.strip(), "any", True))
            elif isinstance(it, dict):
                name = it.get("name") or it.get("field") or it.get("key")
                if not isinstance(name, str) or not name.strip():
                    continue
                fields.append(_field(name.strip(),
                                     normalize_type(it.get("type")),
                                     it.get("required", True)))
    elif isinstance(oc, dict):
        for k, v in oc.items():
            if isinstance(v, str):
                fields.append(_field(str(k), normalize_type(v), True))
            elif isinstance(v, dict):
                fields.append(_field(str(k), normalize_type(v.get("type")),
                                     v.get("required", True)))
            else:
                fields.append(_field(str(k), "any", True))
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 case.json 的 output_contract，生成 contract.json")
    ap.add_argument("--case", default="/input/case.json",
                    help="case.json 路径（默认 /input/case.json）")
    ap.add_argument("--out", default="/app/work/contract.json",
                    help="contract.json 输出路径（默认 /app/work/contract.json）")
    args = ap.parse_args(argv)

    notes = []
    degraded = False
    fields = []
    case_id = None
    case = None
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:  # 文件缺失/畸形 JSON 均降级
        degraded = True
        notes.append("case.json 读取或解析失败(%s)，降级：仅保证 case_id"
                     % type(e).__name__)
        case = {}

    if not isinstance(case, dict):
        degraded = True
        notes.append("case.json 顶层不是 JSON 对象，降级：仅保证 case_id")
    else:
        case_id = case.get("case_id")
        oc = case.get("output_contract")
        if oc is None:
            degraded = True
            notes.append("缺少 output_contract 字段，降级：仅保证 case_id")
        else:
            fields = parse_fields(oc)
            if not fields:
                degraded = True
                notes.append("output_contract 解析结果为空，降级：仅保证 case_id")

    if not isinstance(case_id, str) or not case_id.strip():
        case_id = "UNKNOWN_CASE_ID"
        degraded = True
        notes.append("case_id 缺失或非法，使用占位符 UNKNOWN_CASE_ID")
    else:
        case_id = case_id.strip()

    out = {"case_id": case_id, "degraded": degraded,
           "fields": fields, "notes": notes}
    atomic_write_json(args.out, out)
    print("contract_scan: case_id=%s fields=%d degraded=%s -> %s"
          % (case_id, len(fields), degraded, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
