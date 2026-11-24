#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_result.py — 装配 result.json

读取 case.json 的 output_contract，逐键装配最终结果：
  - case_id        ：原样取自 case.json
  - deliverable    ：修复/校准后的最终稿件全文
  - preserved_facts：经核对保留的事实清单（--preserved-facts 提供；缺省为空并在 uncertainty 声明）
  - evidence_map   ：断言 → 材料出处映射（--evidence-map 提供；缺省为空并在 uncertainty 声明）
  - change_log     ：fix_log（自动）+ resolution_log（模型处理记录）合并
另附诚实字段：status / sources / uncertainty 与 lint 统计。

用法：
  python3 assemble_result.py --case /input/case.json --deliverable deliverable.md \
      --fix-log fix_log.json --resolution-log resolution_log.json --lint-stats lint_stats.json \
      --preserved-facts preserved_facts.json --evidence-map evidence_map.json \
      --out /app/output/result.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path, default):
    """读取 JSON 文件；path 为空或文件不存在时返回 default。"""
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        print(f"警告：文件不存在，按缺省处理：{p}", file=sys.stderr)
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="按 output_contract 装配 result.json")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--deliverable", required=True, help="最终稿件（Markdown）路径")
    ap.add_argument("--fix-log", default=None, help="fix_log.json（自动修复记录）")
    ap.add_argument("--resolution-log", default=None, help="resolution_log.json（模型处理记录）")
    ap.add_argument("--lint-stats", default=None, help="lint 统计 JSON")
    ap.add_argument("--preserved-facts", default=None, help="保留事实清单 JSON（字符串数组）")
    ap.add_argument("--evidence-map", default=None, help="证据映射 JSON（对象：断言→出处）")
    ap.add_argument("--sources", nargs="*", default=[], help="材料/来源文件路径列表")
    ap.add_argument("--status", default="success", choices=["success", "partial", "failed"])
    ap.add_argument("--out", required=True, help="result.json 输出路径")
    args = ap.parse_args()

    case = load_json(args.case, {})
    contract = case.get("output_contract", {})
    contract_keys = list(contract.keys()) if isinstance(contract, dict) else list(contract)

    deliverable_text = Path(args.deliverable).read_text(encoding="utf-8")
    fix_log = load_json(args.fix_log, [])
    resolution_log = load_json(args.resolution_log, [])
    lint_stats = load_json(args.lint_stats, {})
    preserved_facts = load_json(args.preserved_facts, [])
    evidence_map = load_json(args.evidence_map, {})

    uncertainty = []
    if not preserved_facts:
        uncertainty.append("preserved_facts 未提供，按空清单输出；正式运行应由模型核对材料后填写。")
    if not evidence_map:
        uncertainty.append("evidence_map 未提供，按空映射输出；正式运行应由模型逐条标注断言出处。")
    highs = lint_stats.get("totals", {}).get("高", None)
    if highs:
        uncertainty.append(f"复检时仍有 {highs} 条高级别 lint 项未清零，交付状态应记为 partial。")
        if args.status == "success":
            args.status = "partial"

    # change_log：自动修复（fix_log）+ 模型处理（resolution_log），逐条可溯
    change_log = []
    for e in fix_log:
        change_log.append({
            "type": "auto",
            "rule": e.get("rule"),
            "line": e.get("line"),
            "original": e.get("original"),
            "replacement": e.get("replacement"),
            "context": e.get("context"),
        })
    for e in resolution_log:
        change_log.append({
            "type": "model",
            "rule": e.get("rule"),
            "line": e.get("line"),
            "action": e.get("action"),          # "fixed" | "rejected"
            "reason": e.get("reason", ""),
            "original": e.get("original", ""),
            "replacement": e.get("replacement", ""),
        })

    # 按 output_contract 逐键装配；未知键以 null 占位并在 uncertainty 声明
    value_pool = {
        "case_id": case.get("case_id"),
        "deliverable": deliverable_text,
        "preserved_facts": preserved_facts,
        "evidence_map": evidence_map,
        "change_log": change_log,
    }
    result = {}
    for key in contract_keys:
        if key in value_pool:
            result[key] = value_pool[key]
        else:
            result[key] = None
            uncertainty.append(f"output_contract 含非常规键「{key}」，已以 null 占位。")

    # 诚实字段与 lint 统计（附加在契约字段之外，不覆盖契约键名）
    result["status"] = args.status
    result["sources"] = args.sources
    result["uncertainty"] = uncertainty
    result["lint_stats"] = lint_stats
    result["assembled_at"] = datetime.now(timezone.utc).isoformat()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = [k for k in contract_keys if k not in result]
    print(f"result.json 已写出：{out}")
    print(f"契约键 {len(contract_keys)} 个，缺失 {len(missing)} 个；status={result['status']}")
    if missing:
        print(f"缺失键：{missing}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
