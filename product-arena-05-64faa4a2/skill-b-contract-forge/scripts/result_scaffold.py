#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_scaffold.py — 由 contract.json 生成 result.json 骨架。

纯标准库、无网络、确定性输出。

用法：
    python3 result_scaffold.py --contract /app/work/contract.json --work-dir /app/work
    python3 result_scaffold.py --contract /app/work/contract.json --work-dir /app/work \
        --output-dir /app/output

行为：
  1. 生成 <work-dir>/result.skeleton.json：case_id 直接填入；每个契约字段给统一占位结构
     {status:"pending", value:null, sources:[], uncertainty:[], assumptions:[], notes:""}。
  2. 若 contract_fields 为空（未找到契约），给出保守默认字段（artifact/status），
     并在 skeleton_meta.warnings 中说明。
  3. 生成 <work-dir>/WORKSPACE.md：/app/work 目录约定说明。
  4. 指定 --output-dir 时，同时把骨架复制为 <output-dir>/result.json（尽早占位），
     若该文件已存在且非本工具生成的骨架则不覆盖（保护已填充内容）。
"""
import argparse
import json
import os
import sys

PLACEHOLDER_KEYS = ("status", "value", "sources", "uncertainty", "assumptions", "notes")

WORKSPACE_MD = """\
# /app/work 目录约定（由 result_scaffold.py 生成）

- `contract.json`：contract_probe.py 的输出，契约字段清单的唯一权威来源。
- `result.skeleton.json`：result.json 骨架。写作过程中**增量填充**本文件：
  每个字段填 `status`/`value`/`sources`/`uncertainty`/`assumptions`/`notes`，
  完成后导出为 `/app/output/result.json`。
- `chapter.md`：章节正文草稿；定稿后复制到 `/app/output/chapter.md`。
- `snippets/`：建议存放中间片段，实现"尽早保存部分产物"。
- 最终产物一律放 `/app/output`；`/app/work` 内容不视为交付。
- 填充规则：字段语义不明时保守填充并在 `assumptions` 记录解释；
  材料缺失用 `status:"unavailable"` + 原因；最终交付不允许残留 `pending`。
"""


def _placeholder(field):
    ph = {
        "status": "pending",
        "value": None,
        "sources": [],
        "uncertainty": [],
        "assumptions": [],
        "notes": "",
    }
    if field.get("semantic_guess", "").startswith("unknown"):
        ph["assumptions"].append("契约未说明该字段语义，待保守填充时记录解释")
    if field.get("type_guess") in (None, "unknown"):
        ph["notes"] = "类型未明，按保守结构填充"
    return ph


def build_skeleton(contract):
    fields = contract.get("contract_fields") or []
    warnings = []
    if not fields:
        warnings.append("contract.json 中 contract_fields 为空：未找到 output_contract，"
                        "骨架使用保守默认字段 artifact/status，请务必人工核对 case.json")
        fields = [
            {"name": "artifact", "type_guess": "file", "semantic_guess": "主要产物（默认）"},
            {"name": "status", "type_guess": "string", "semantic_guess": "任务完成状态（默认）"},
        ]
    skeleton = {
        "case_id": contract.get("case_id"),
        "skeleton_meta": {
            "generated_by": "result_scaffold.py",
            "contract_source": contract.get("contract_source"),
            "warnings": warnings,
            "field_order": [f["name"] for f in fields],
        },
    }
    for f in fields:
        skeleton[f["name"]] = _placeholder(f)
    return skeleton


def _is_our_skeleton(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and "skeleton_meta" in data


def main(argv=None):
    ap = argparse.ArgumentParser(description="由 contract.json 生成 result.json 骨架")
    ap.add_argument("--contract", required=True, help="contract.json 路径")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output-dir", default=None,
                    help="指定后同时写入 <output-dir>/result.json 骨架（不覆盖已填充文件）")
    args = ap.parse_args(argv)

    try:
        with open(args.contract, "r", encoding="utf-8") as f:
            contract = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: contract.json 读取/解析失败：%s" % e, file=sys.stderr)
        return 2

    skeleton = build_skeleton(contract)
    os.makedirs(args.work_dir, exist_ok=True)
    skel_path = os.path.join(args.work_dir, "result.skeleton.json")
    with open(skel_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)
        f.write("\n")

    ws_path = os.path.join(args.work_dir, "WORKSPACE.md")
    with open(ws_path, "w", encoding="utf-8") as f:
        f.write(WORKSPACE_MD)

    print("OK: skeleton -> %s（字段 %d 个：%s）"
          % (skel_path, len(skeleton["skeleton_meta"]["field_order"]),
             ", ".join(skeleton["skeleton_meta"]["field_order"])))
    print("OK: workspace 说明 -> %s" % ws_path)

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        final_path = os.path.join(args.output_dir, "result.json")
        if os.path.exists(final_path) and not _is_our_skeleton(final_path):
            print("WARN: %s 已存在且非本工具骨架，未覆盖（保护已填充内容）" % final_path)
        else:
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print("OK: 占位骨架 -> %s" % final_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
