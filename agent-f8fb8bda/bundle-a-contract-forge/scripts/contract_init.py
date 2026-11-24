#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_init.py —— 阶段一：契约初始化（仅 Python3 标准库，无网络依赖）。

读取 case.json，在 --out 目录产出三份确定性文件：
  contract.json       规范化契约：case_id、output_contract 字段清单（点路径展开，
                      保留每字段原始声明文本）、材料文件清单及各自 SHA-256
  result.json         交付骨架：原样 case_id、全部契约字段以 "PENDING" 占位、
                      status="partial"、六个固定要点区块存在且置空、
                      sources=[]、uncertainty/limitations 为初始化占位文案
  budget_ledger.json  预算上限（64 请求 / 900 秒）与五阶段配额建议、usage 空表

退出码：
  0  成功
  2  用法 / IO 错误（case.json 缺失、JSON 损坏、顶层非对象、缺 case_id 或
     output_contract 不可用）；此时仍尽力在 --out 写出 status=blocked 的
     result.json 说明缺什么，然后退出 2。

产物不含随机数与时间戳，同一 case.json 重复运行结果字节一致。
"""

import argparse
import hashlib
import json
import os
import sys

BUDGET_CAPS = {"model_requests": 64, "wall_seconds": 900}

STAGE_QUOTA = [
    {"stage": "1_contract_init", "quota_requests": 3, "quota_seconds": 60,
     "note": "先跑本脚本生成骨架，模型只读 contract.json，不手写契约字段"},
    {"stage": "2_problem_decomposition", "quota_requests": 8, "quota_seconds": 120,
     "note": "尽量一次响应完成拆解并回填 problem_decomposition"},
    {"stage": "3_search_execution", "quota_requests": 30, "quota_seconds": 420,
     "note": "检索主战场；每轮检索后立即回填 search_coverage 与 sources"},
    {"stage": "4_evidence_synthesis", "quota_requests": 16, "quota_seconds": 220,
     "note": "集中回填 evidence_linkage / conflict_evidence / synthesis / research_gaps"},
    {"stage": "5_delivery_gate", "quota_requests": 7, "quota_seconds": 80,
     "note": "先 checkpoint save 再修；contract_check 门控通过后交付"},
]

SIX_BLOCKS = ["problem_decomposition", "search_coverage", "evidence_linkage",
              "conflict_evidence", "synthesis", "research_gaps"]

RESERVED_KEYS = {"case_id", "status", "blocked_reason", "sources",
                 "uncertainty", "limitations"} | set(SIX_BLOCKS)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def expand_fields(prefix, value, out):
    """把 output_contract 展开为点路径清单。

    值为非空 dict 时递归展开；空 dict、数组、字符串、数字、null 一律视为叶子，
    叶子保留 json.dumps 后的原始声明文本。字段类型不明时不猜测、不报错。
    """
    if isinstance(value, dict) and value:
        for key, sub in value.items():
            path = "{}.{}".format(prefix, key) if prefix else str(key)
            expand_fields(path, sub, out)
    else:
        out.append({
            "path": prefix,
            "declaration": json.dumps(value, ensure_ascii=False),
        })


def empty_block(name):
    return "" if name == "synthesis" else []


def base_result(case_id, status):
    result = {"case_id": case_id, "status": status}
    for name in SIX_BLOCKS:
        result[name] = empty_block(name)
    result["sources"] = []
    result["uncertainty"] = []
    result["limitations"] = []
    return result


def write_blocked(out_dir, case_id, reason):
    try:
        os.makedirs(out_dir, exist_ok=True)
        result = base_result(case_id, "blocked")
        result["blocked_reason"] = reason
        result["uncertainty"] = ["初始化失败：{}".format(reason)]
        result["limitations"] = ["case.json 不可用，五个阶段均未执行；修复后重跑 contract_init.py"]
        path = os.path.join(out_dir, "result.json")
        dump_json(path, result)
        print("[contract_init] BLOCKED: {}".format(reason))
        print("[contract_init] 已写出 {}".format(path))
    except OSError as exc:
        print("[contract_init] FATAL: 连 blocked result.json 都无法写出：{}".format(exc),
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="阶段一：从 case.json 生成 contract.json / result.json 骨架 / budget_ledger.json")
    parser.add_argument("--case", default="/input/case.json", help="case.json 路径")
    parser.add_argument("--out", default="/app/output", help="产物输出目录")
    parser.add_argument("--materials-dir", default=None,
                        help="材料文件目录（默认取 case.json 所在目录，递归计算 SHA-256）")
    args = parser.parse_args(argv)

    # ---- 防御式读取 case.json：任何缺失都清晰报错，绝不猜测 ----
    if not os.path.isfile(args.case):
        write_blocked(args.out, None, "case.json 不存在：{}".format(args.case))
        return 2
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        write_blocked(args.out, None, "case.json 读取或解析失败：{}".format(exc))
        return 2
    if not isinstance(case, dict):
        write_blocked(args.out, None, "case.json 顶层必须是 JSON 对象")
        return 2
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        write_blocked(args.out, None,
                      "case.json 缺少有效的 case_id 字符串（实际为 {!r}）".format(case_id))
        return 2
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        write_blocked(args.out, case_id,
                      "case.json 缺少有效的 output_contract 非空对象（实际为 {!r}）".format(
                          type(contract).__name__))
        return 2

    # ---- 展开契约字段（点路径 + 原始声明文本）----
    fields = []
    for key, value in contract.items():
        expand_fields(str(key), value, fields)
    top_fields = [str(k) for k in contract.keys()]
    collisions = [k for k in top_fields if k in RESERVED_KEYS]

    # ---- 材料清单与 SHA-256 ----
    materials_dir = args.materials_dir or os.path.dirname(os.path.abspath(args.case))
    materials = []
    materials_note = None
    if os.path.isdir(materials_dir):
        for root, _dirs, files in os.walk(materials_dir):
            for name in sorted(files):
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                materials.append({
                    "path": os.path.relpath(full, materials_dir),
                    "sha256": sha256_of(full),
                    "bytes": os.path.getsize(full),
                })
        materials.sort(key=lambda m: m["path"])
    else:
        materials_note = "材料目录不存在：{}（materials 置空）".format(materials_dir)

    os.makedirs(args.out, exist_ok=True)

    # ---- (a) contract.json ----
    notes = [
        "fields[].path 为点路径展开结果；declaration 为 case.json 中的原始声明文本",
        "result.json 骨架中所有契约字段以 PENDING 占位，必须由对应阶段回填",
        "本文件不含随机数与时间戳，重复运行字节一致",
    ]
    if collisions:
        notes.append("以下契约字段名与保留键冲突，骨架中未为其设置 PENDING 占位："
                     + ", ".join(collisions))
    if materials_note:
        notes.append(materials_note)
    contract_doc = {
        "case_id": case_id,
        "generated_by": "contract_init.py",
        "output_contract": {
            "top_level_fields": top_fields,
            "fields": fields,
        },
        "materials_dir": os.path.abspath(materials_dir),
        "materials": materials,
        "reserved_key_collisions": collisions,
        "notes": notes,
    }
    contract_path = os.path.join(args.out, "contract.json")
    dump_json(contract_path, contract_doc)

    # ---- (b) result.json 骨架 ----
    result = base_result(case_id, "partial")
    for key in top_fields:
        if key not in RESERVED_KEYS:
            result[key] = "PENDING"
    result["uncertainty"] = ["初始化：尚未执行检索与综合"]
    result["limitations"] = ["初始化占位，待各阶段回填"]
    result_path = os.path.join(args.out, "result.json")
    dump_json(result_path, result)

    # ---- (c) budget_ledger.json ----
    ledger = {
        "budget_caps": BUDGET_CAPS,
        "stage_quota": STAGE_QUOTA,
        "usage": [],
        "usage_format": {"stage": "阶段名", "requests": "本次消耗的请求数",
                         "seconds": "本次消耗的秒数", "note": "可选备注"},
        "note": "usage 由 agent 在每阶段结束后自行追加一条；配额用尽前按 references/budget_protocol.md 降级",
    }
    ledger_path = os.path.join(args.out, "budget_ledger.json")
    dump_json(ledger_path, ledger)

    print("[contract_init] OK case_id={}".format(case_id))
    print("[contract_init] 契约顶层字段 {} 个，展开路径 {} 条：{}".format(
        len(top_fields), len(fields), ", ".join(top_fields)))
    print("[contract_init] 材料 {} 个（{}）".format(len(materials), materials_dir))
    if collisions:
        print("[contract_init] WARNING 保留键冲突：{}".format(", ".join(collisions)))
    print("[contract_init] 写出：{} / {} / {}".format(
        contract_path, result_path, ledger_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
