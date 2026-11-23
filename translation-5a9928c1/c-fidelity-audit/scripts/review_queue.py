#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_queue.py — turn fidelity_report.json into a human review queue (markdown checklist).

Usage:
  python3 review_queue.py --report fidelity_report.json --out human_review_queue.md

Rule: 任何条目不得在未修复/未人工确认的情况下被关闭；关闭时须在处理记录中注明。
Python 3.8+, stdlib only.
"""
import argparse
import json

SUGGESTED_ACTION = {
    "number-dropped": "回译文补回该数字（含单位），随后重跑 check_fidelity 直至该 blocker 清零。",
    "number-changed": "核对源文与译文取值，按源文改正译文数字；若译文确有依据，须由领域人工书面确认后关闭。",
    "unit-changed": "将译文单位改为与源文一致（注意 μ/u、℃/°C 等归一化差异），重跑核验。",
    "citation-lost": "在译文对应位置补回引文标记，保持与源文多重集一致。",
    "ref-lost": "在译文对应位置补回图/表/公式引用（如“如图 2 所示”），重跑核验。",
    "negation-lost": "检查译文是否丢失否定语义，补回“不/未/无/无法/没有”等对应表达；若为源文误判，人工确认后关闭。",
    "hedge-lost": "确认译文是否保留“可能/约/至多/至少/仅/然而/尽管”等语气；必要时修订译文。",
    "number-format": "确认数字格式差异（千分位、空格）不影响取值；确认后关闭。",
    "target-missing": "补齐该段译文后重跑整个流水线；不得跳过该段。",
    "unable_to_determine": "该段机器无法判断（图片内数字/OCR 乱码等），必须由人工直接比对原文与译文。",
}


def item_lines(f):
    lines = []
    lines.append("- [ ] [%s] %s — %s" % (f["seg_id"], f["code"], f.get("note", "")))
    if f.get("evidence_source"):
        lines.append("  > 源文: %s" % f["evidence_source"])
    if f.get("evidence_target"):
        lines.append("  > 译文: %s" % f["evidence_target"])
    else:
        lines.append("  > 译文: （未找到对应内容）")
    action = SUGGESTED_ACTION.get(f["code"], "请人工核对源文与译文并修订。")
    lines.append("  - 建议动作: %s" % action)
    lines.append("  - 处理记录: （关闭时必填：处理人 / 修复方式或人工确认依据）")
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser(description="Render human review queue from fidelity report.")
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.report, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    findings = report.get("findings", [])
    blockers = [f for f in findings if f.get("severity") == "blocker"]
    warnings = [f for f in findings if f.get("severity") == "warning"]

    lines = ["# 人工确认队列（human_review_queue）", ""]
    lines.append("本清单由 review_queue.py 依据 fidelity_report.json 自动生成；"
                 "所有条目均需人工逐条处理，任何条目不得在未修复/未人工确认的情况下被关闭。")
    lines.append("")
    lines.append("## Blockers (must fix)")
    lines.append("")
    if blockers:
        for f in blockers:
            lines.extend(item_lines(f))
    else:
        lines.append("（无）")
        lines.append("")
    lines.append("## Warnings (human confirmation)")
    lines.append("")
    if warnings:
        for f in warnings:
            lines.extend(item_lines(f))
    else:
        lines.append("（无）")
        lines.append("")
    s = report.get("summary", {})
    lines.append("---")
    lines.append("统计: blockers=%d, warnings=%d（报告共 %d 段 / %d 项检查）。"
                 % (len(blockers), len(warnings), s.get("segments", 0), s.get("checks", 0)))
    lines.append("规则: 任何条目不得在未修复/未人工确认的情况下被关闭；关闭时须在处理记录中注明"
                 "处理人与依据。")
    lines.append("")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("wrote %s: %d blockers, %d warnings" % (args.out, len(blockers), len(warnings)))


if __name__ == "__main__":
    main()
