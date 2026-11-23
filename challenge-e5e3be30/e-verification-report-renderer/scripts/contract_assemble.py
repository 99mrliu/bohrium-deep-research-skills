#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_assemble.py — output_contract 发现、result.json 骨架生成、增量合并、完工校验。

子命令：
  skeleton  --case case.json --out result.json
      从 case.json 发现 output_contract 全部字段，生成 result.json 骨架：
      case_id 填好、status=partial、全部契约字段填空占位(null)、
      missing_items 列出全部契约字段。用于"先存后改"的第一步。

  merge     --base result.json --new partial.json --out result.json [--case case.json]
      深度合并：新 JSON 的非空值覆写/扩展骨架；空值(null/""/[]/{})绝不覆盖已有非空字段；
      列表按元素去重追加；字典递归合并。提供 --case 时重算 missing_items。

  validate  --case case.json --result result.json
      完工校验：case_id 一致、契约字段齐全、status 枚举合法且与内容自洽
      （partial 必须给出覆盖全部空契约字段的 missing_items；
       success 不得存在空契约字段）。任一 ERROR 以 exit 1 结束。

退出码：0 成功 / 1 校验失败 / 2 用法或 IO 错误。
仅依赖 Python3 标准库。
"""
import argparse
import copy
import datetime
import json
import sys

STATUS_ENUM = ["success", "partial", "cannot_determine", "refused"]
STANDARD_LIST_FIELDS = ["sources", "change_records"]


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 解析失败 {path}: {e}", file=sys.stderr)
        sys.exit(2)


def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def is_empty(v):
    return v is None or v == "" or v == [] or v == {}


def contract_fields(case):
    """从 case.json 发现 output_contract 字段名列表（保持声明顺序）。"""
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        fields = []
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                fields.append(item["name"])
        return fields
    return []


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def change_record(action, detail=""):
    return {"timestamp": now_iso(), "action": action, "detail": detail}


def deep_merge(old, new):
    """把 new 深度合并进 old。规则：new 的空值不覆盖；dict 递归；list 去重追加；
    标量以新的非空值覆写。返回新对象，不修改入参。"""
    if is_empty(new):
        return copy.deepcopy(old)
    if is_empty(old):
        return copy.deepcopy(new)
    if isinstance(old, dict) and isinstance(new, dict):
        out = copy.deepcopy(old)
        for k, v in new.items():
            out[k] = deep_merge(out.get(k), v)
        return out
    if isinstance(old, list) and isinstance(new, list):
        out = copy.deepcopy(old)
        seen = {json.dumps(x, sort_keys=True, ensure_ascii=False) for x in out}
        for item in new:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                out.append(copy.deepcopy(item))
                seen.add(key)
        return out
    return copy.deepcopy(new)


def cmd_skeleton(args):
    case = load_json(args.case)
    fields = contract_fields(case)
    if not fields:
        print("ERROR: case.json 中未发现 output_contract 字段（dict 或 list）", file=sys.stderr)
        sys.exit(2)
    case_id = case.get("case_id")
    if not case_id:
        print("ERROR: case.json 缺少 case_id", file=sys.stderr)
        sys.exit(2)
    skel = {
        "case_id": case_id,
        "status": "partial",
        "sources": [],
        "uncertainty": "",
        "change_records": [change_record("skeleton_created",
                                         f"发现 {len(fields)} 个契约字段")],
        "missing_items": list(fields),
    }
    for f in fields:
        if f in skel:
            print(f"ERROR: 契约字段与标准字段重名: {f}", file=sys.stderr)
            sys.exit(2)
        skel[f] = None
    dump_json(skel, args.out)
    print(f"OK: 骨架已写入 {args.out}（{len(fields)} 个契约字段，status=partial）")
    return 0


def cmd_merge(args):
    base = load_json(args.base)
    new = load_json(args.new)
    if not isinstance(base, dict) or not isinstance(new, dict):
        print("ERROR: base 与 new 必须是 JSON 对象", file=sys.stderr)
        sys.exit(2)
    merged = deep_merge(base, new)
    records = merged.get("change_records")
    if not isinstance(records, list):
        records = []
    records.append(change_record("merge", f"合并 {args.new}"))
    merged["change_records"] = records
    if args.case:
        case = load_json(args.case)
        fields = contract_fields(case)
        merged["missing_items"] = [f for f in fields if is_empty(merged.get(f))]
    dump_json(merged, args.out)
    print(f"OK: 合并结果已写入 {args.out}")
    return 0


def validate_result(case, result):
    """返回错误信息列表；空列表表示通过。"""
    errors = []
    if not isinstance(result, dict):
        return ["result.json 不是 JSON 对象"]
    if result.get("case_id") != case.get("case_id"):
        errors.append(f"case_id 不一致: result={result.get('case_id')!r} "
                      f"case={case.get('case_id')!r}")
    status = result.get("status")
    if status not in STATUS_ENUM:
        errors.append(f"status 非法: {status!r}（应为 {STATUS_ENUM} 之一）")
    fields = contract_fields(case)
    if not fields:
        errors.append("case.json 中未发现 output_contract")
    absent = [f for f in fields if f not in result]
    empty = [f for f in fields if f in result and is_empty(result[f])]
    for f in absent:
        errors.append(f"契约字段缺失（键不存在）: {f}")
    if status == "success":
        for f in empty:
            errors.append(f"status=success 但契约字段为空: {f}")
    elif status == "partial":
        mi = result.get("missing_items")
        if not isinstance(mi, list) or not mi:
            errors.append("status=partial 必须给出非空数组 missing_items 说明缺失项")
        else:
            for f in absent + empty:
                if f not in mi:
                    errors.append(f"missing_items 未列出缺失/空契约字段: {f}")
    for sf in STANDARD_LIST_FIELDS:
        if sf not in result:
            errors.append(f"标准字段缺失: {sf}")
        elif not isinstance(result[sf], list):
            errors.append(f"标准字段 {sf} 必须是数组")
    if "uncertainty" not in result:
        errors.append("标准字段缺失: uncertainty")
    return errors


def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    errors = validate_result(case, result)
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"FAIL: 共 {len(errors)} 个错误")
        return 1
    fields = contract_fields(case)
    print(f"OK: 契约校验通过（{len(fields)} 个契约字段齐全，"
          f"status={result.get('status')} 与内容自洽）")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="output_contract 发现、result.json 骨架生成、增量合并与完工校验")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("skeleton", help="case.json → result.json 骨架（status=partial）")
    ps.add_argument("--case", required=True, help="case.json 路径")
    ps.add_argument("--out", required=True, help="骨架输出路径")
    ps.set_defaults(func=cmd_skeleton)

    pm = sub.add_parser("merge", help="骨架 + 新结果 JSON 深度合并（不丢已有非空字段）")
    pm.add_argument("--base", required=True, help="已有 result.json（骨架或中间态）")
    pm.add_argument("--new", required=True, help="本次新增结果 JSON")
    pm.add_argument("--out", required=True, help="合并输出路径（可与 --base 相同）")
    pm.add_argument("--case", help="可选：提供 case.json 时重算 missing_items")
    pm.set_defaults(func=cmd_merge)

    pv = sub.add_parser("validate", help="对照 case.json 校验 result.json 完工度")
    pv.add_argument("--case", required=True, help="case.json 路径")
    pv.add_argument("--result", required=True, help="result.json 路径")
    pv.set_defaults(func=cmd_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
