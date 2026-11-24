#!/usr/bin/env python3
"""audit_skeleton.py — 开工保底：从 case.json 生成诚实的 result.json 骨架

在任何实质审查开始前先落一个合法的 partial result.json：
  - case_id 取自 case.json（缺则 UNKNOWN_CASE 并记 warning）；
  - output_contract.required_fields 里的每个字段都被实例化（不认识的字段给
    空占位，保证契约字段一个不缺）；
  - status 固定为 "partial"，uncertainty 如实说明"审查尚未完成"；
  - change_log 写入首条记录（确定性内容，无时间戳）。

纪律：默认拒绝覆盖已存在的输出文件（防止误删真实成果），显式 --force 才覆盖。
缺键/坏 JSON 不崩溃：exit 0，warnings 如实写入骨架。

仅 Python3 标准库；确定性输出；单次运行远低于 5 秒。
"""
import argparse
import json
import os
import sys

DEFAULT_REQUIRED = ["case_id", "status", "findings", "not_reviewed",
                    "uncertainty", "sources", "change_log"]

# 已知字段的诚实保底默认值
KNOWN_DEFAULTS = {
    "case_id": None,  # 特殊处理
    "status": "partial",
    "findings": [],
    "not_reviewed": [],
    "uncertainty": "骨架文件：实质审查尚未开始或未完成；本文件仅保证 output_contract 字段齐全。",
    "sources": [],
    "change_log": None,  # 特殊处理
    "summary": "",
    "anchor_stats": {},
}


def load_case(path, warnings):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            warnings.append("case.json 顶层不是对象，按空处理")
            return {}
        return doc
    except FileNotFoundError:
        warnings.append("case.json 不存在：%s（按空 case 处理）" % path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append("无法解析 case.json：%s（按空 case 处理）" % exc)
    return {}


def extract_facets(case):
    """尽力从 case.json 提取审查面列表；提取不到返回 []。"""
    for key in ("review_facets", "facets", "review_dimensions"):
        val = case.get(key)
        if isinstance(val, list) and val:
            return [str(v) for v in val]
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从 case.json 生成 result.json 保底骨架（status=partial，字段齐全）。"
    )
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--out", required=True, help="输出 result.json 路径")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已存在的输出文件（默认拒绝覆盖以保护已有成果）")
    args = ap.parse_args(argv)

    if os.path.exists(args.out) and not args.force:
        print("audit_skeleton: %s 已存在，未覆盖（用 --force 显式覆盖）。"
              "已有保底/成果文件得到保护。" % args.out)
        return 0

    warnings = []
    case = load_case(args.case, warnings)

    case_id = case.get("case_id")
    if not case_id:
        case_id = "UNKNOWN_CASE"
        warnings.append("case.json 缺少 case_id，使用 UNKNOWN_CASE 占位")

    contract = case.get("output_contract")
    required = None
    if isinstance(contract, dict):
        req = contract.get("required_fields")
        if isinstance(req, list) and req:
            required = [str(f) for f in req]
    if required is None:
        required = list(DEFAULT_REQUIRED)
        warnings.append("未找到 output_contract.required_fields，使用内置默认字段集")

    skeleton = {}
    for field in required:
        if field == "case_id":
            skeleton["case_id"] = case_id
        elif field == "change_log":
            skeleton["change_log"] = [{
                "seq": 1,
                "actor": "audit_skeleton.py",
                "event": "skeleton_created",
                "detail": "开工保底骨架：status=partial；required_fields 全部实例化；"
                          "实质审查完成后由 Agent 追加记录并更新 status。",
            }]
        elif field in KNOWN_DEFAULTS:
            skeleton[field] = KNOWN_DEFAULTS[field]
        else:
            skeleton[field] = None  # 不认识的契约字段：显式 null 占位，绝不缺键

    facets = extract_facets(case)
    if isinstance(skeleton.get("not_reviewed"), list) and facets:
        skeleton["not_reviewed"] = [
            {"facet": f, "reason": "尚未检查（骨架阶段）"} for f in facets
        ]

    if warnings:
        skeleton["skeleton_warnings"] = warnings

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(skeleton, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("audit_skeleton: %s -> %s | case_id=%s required_fields=%d warnings=%d"
          % (args.case, args.out, case_id, len(required), len(warnings)))
    for w in warnings:
        print("  WARNING: " + w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
