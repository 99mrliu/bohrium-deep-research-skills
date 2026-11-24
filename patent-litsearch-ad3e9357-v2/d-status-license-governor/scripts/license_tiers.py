#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""license_tiers.py — 数据源授权分级（绿/黄/红）与能力降级规划。

用法:
    python3 license_tiers.py classify --sources sources.json --out license_report.json
    python3 license_tiers.py plan     --sources sources.json --out degradation_plan.json

sources.json 中每个来源除 tier 外需带 license 字段:
    {access: public|registration|paid|restricted,
     display_scope: full|fields_only|citation_only|none,
     retention_days, confidentiality_note}

分级规则:
    绿 green : access=public 且 display_scope=full
    黄 yellow: display_scope∈{fields_only, citation_only} 或 access=registration；
               license 字段缺失/无法识别 → 按黄级处理直至澄清
    红 red   : access∈{paid, restricted}（含登录墙商业库）或 display_scope=none

退出码: 0 = 正常完成; 1 = 治理违规（本工具不产生）; 2 = 用法/输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

VALID_ACCESS = {"public", "registration", "paid", "restricted"}
VALID_SCOPE = {"full", "fields_only", "citation_only", "none"}


def load_sources(path):
    """容忍 list / {sources:[...]} / {id: {...}} 三种形态，返回条目列表。"""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] sources 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[输入错误] sources 文件不是合法 JSON: {path}: {exc}")
    if isinstance(raw, dict) and isinstance(raw.get("sources"), list):
        entries = raw["sources"]
    elif isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [dict(v, source_id=k) for k, v in raw.items() if isinstance(v, dict)]
    else:
        raise SystemExit(f"[输入错误] sources 文件结构无法识别: {path}")
    return [e for e in entries if isinstance(e, dict)]


def classify_one(src):
    """返回 (color, reason)。"""
    access = src.get("access")
    scope = src.get("display_scope")
    if access in ("paid", "restricted") or scope == "none":
        return "red", (f"access={access!r}, display_scope={scope!r}：付费/受限/登录墙或禁止展示，"
                       f"禁止抓取与原文展示")
    if scope in ("fields_only", "citation_only") or access == "registration":
        return "yellow", (f"access={access!r}, display_scope={scope!r}：仅字段/仅引述或需注册，"
                          f"限许可范围内使用")
    if access == "public" and scope == "full":
        return "green", "access=public 且 display_scope=full：公开且可全文展示"
    return "yellow", (f"license 字段缺失或无法识别（access={access!r}, display_scope={scope!r}），"
                      f"按黄级处理直至澄清")


def build_classification(sources):
    rows = []
    for s in sources:
        color, reason = classify_one(s)
        rows.append({
            "source_id": s.get("source_id"),
            "name": s.get("name"),
            "tier": s.get("tier", "unknown"),
            "access": s.get("access"),
            "display_scope": s.get("display_scope"),
            "retention_days": s.get("retention_days"),
            "confidentiality_note": s.get("confidentiality_note"),
            "color": color,
            "reason": reason,
        })
    summary = {"green": sum(1 for r in rows if r["color"] == "green"),
               "yellow": sum(1 for r in rows if r["color"] == "yellow"),
               "red": sum(1 for r in rows if r["color"] == "red")}
    return rows, summary


def degradation_rule(src, color):
    sid = src.get("source_id")
    scope = src.get("display_scope")
    if color == "red":
        return {
            "source_id": sid,
            "color": "red",
            "rule": "do_not_fetch",
            "action": ("不抓取、不登录、不绕过付费墙/登录墙；仅在结果中声明该来源存在，"
                       "并标注「无法访问」；不得展示、转述其任何受限原文。"),
            "allowed_display": "none",
            "result_marker": "无法访问",
        }
    if scope == "citation_only":
        return {
            "source_id": sid,
            "color": "yellow",
            "rule": "cite_existence_only",
            "action": "仅可引用该来源的存在与题录级信息；不得展示正文，不得作为法律状态依据。",
            "allowed_display": "citation_only",
            "result_marker": "仅引述存在",
        }
    return {
        "source_id": sid,
        "color": "yellow",
        "rule": "fields_only",
        "action": ("仅提取并展示其许可范围内的字段（题录/字段级）；不得展示原文全文；"
                   "作为法律状态依据时只能支撑「未核验」声明。"),
        "allowed_display": "fields_only",
        "result_marker": "仅许可字段",
    }


DEGRADATION_CHECKLIST = [
    "所有红级来源均未抓取、未登录、未绕过付费墙，结果中仅标注其存在与「无法访问」",
    "所有黄级来源仅提取/展示其 display_scope 许可范围内的字段，未展示原文全文",
    "license 字段缺失或未知的来源已按黄级处理，并在 uncertainty 中声明",
    "result.json 的 sources 清单中每个来源均标注 tier 与 color",
    "受限（红/黄）来源未被当作登记依据，法律状态断言均回溯到 register/official_gazette 级来源",
    "留存期限（retention_days）与保密要求（confidentiality_note）已逐条核对",
]


def write_json(obj, out_path):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="数据源授权分级与能力降级规划")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("classify", "plan"):
        p = sub.add_parser(name)
        p.add_argument("--sources", required=True)
        p.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        sources = load_sources(args.sources)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    if not sources:
        print(f"[输入错误] sources 文件中没有可用来源条目: {args.sources}", file=sys.stderr)
        return 2

    rows, summary = build_classification(sources)

    if args.cmd == "classify":
        report = {
            "report": "license_classification",
            "sources_file": args.sources,
            "classifications": rows,
            "summary": summary,
        }
        write_json(report, args.out)
        print(f"[license_tiers classify] 绿={summary['green']} 黄={summary['yellow']} 红={summary['red']} → {args.out}")
        return 0

    if args.cmd == "plan":
        rules = [degradation_rule(s, r["color"]) for s, r in zip(sources, rows) if r["color"] != "green"]
        plan = {
            "report": "degradation_plan",
            "sources_file": args.sources,
            "rules": rules,
            "checklist": DEGRADATION_CHECKLIST,
            "note": "能力降级方案：红级不做能力调用（do_not_fetch），黄级降级为许可字段/存在性引用；"
                    "license 未知来源一律按黄级处理直至澄清。",
        }
        write_json(plan, args.out)
        print(f"[license_tiers plan] 降级规则 {len(rules)} 条，checklist {len(DEGRADATION_CHECKLIST)} 项 → {args.out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
