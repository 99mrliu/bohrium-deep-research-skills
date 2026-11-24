#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fact_check.py — 改写稿事实核验器（skill-a-factsentry）

输入 ledger_extract.py 生成的 evidence_ledger.json 与改写稿文本（md/txt），
输出 fact_check_report.json 与（可选）同名 Markdown 报告。三类核验：

  (a) unsupported_number 数字漂移 / 单位错配
      改写稿中每个「数值+单位」必须能在台账中找到值与单位均一致的条目，
      否则记 unsupported_number，并给出同单位候选值（疑似漂移）
      或同值异单位提示（疑似单位错配）。
  (b) dropped_evidence 证据丢失
      台账中的关键条目（全部数字、图表引用、引用标记）若未出现在改写稿中，
      记 dropped_evidence。严重度：number/figure_ref = mandatory，
      citation = recommended；--min-severity 控制计入失败判定的最低严重度。
  (c) strength_upgrade 论断强度升格
      按锚句相似度（CJK 二字组 + 拉丁词 + 数字的 Jaccard）把改写稿论断句
      配对于源文论断句；若改写稿强度级别更高（阶梯见
      references/claim_strength_ladder.md），记 strength_upgrade。
      「相关→因果」（如 导致/治愈/根治/causes）在本阶梯中为最高级 4，
      源文无同级因果表述时必然触发告警。

退出码：0 = 无 drift（PASS）；3 = 发现 drift（FAIL）；2 = 用法或输入/输出错误。

用法：
  python3 fact_check.py --ledger evidence_ledger.json --draft draft.md \
      --json-out fact_check_report.json --md-out fact_check_report.md \
      [--min-severity mandatory|recommended]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_extract as le  # noqa: E402

VERSION = "1.0.0"
SIM_THRESHOLD = 0.15  # 论断句配对的 Jaccard 相似度阈值

SEVERITY_RANK = {"optional": 0, "recommended": 1, "mandatory": 2}
DROP_SEVERITY = {"number": "mandatory", "figure_ref": "mandatory",
                 "citation": "recommended"}
KIND_ORDER = {"unsupported_number": 0, "dropped_evidence": 1,
              "strength_upgrade": 2}
KIND_LABEL = {"unsupported_number": "数字漂移/单位错配",
              "dropped_evidence": "证据丢失",
              "strength_upgrade": "论断强度升格"}


# ---------------------------------------------------------------------------
# 论断句分组：同一锚句中的多个强度词取最高级别
# ---------------------------------------------------------------------------

def group_strength(entries):
    groups = {}
    for e in entries:
        if e.get("kind") != "strength":
            continue
        key = (e["locator"], e["anchor"])
        g = groups.setdefault(key, {
            "locator": e["locator"], "anchor": e["anchor"],
            "level": 0.0, "words": [], "categories": set(),
        })
        g["level"] = max(g["level"], e["level"])
        if e["word"] not in g["words"]:
            g["words"].append(e["word"])
        g["categories"].add(e["category"])
    for g in groups.values():
        g["causal"] = "causal" in g["categories"]
        g["categories"] = sorted(g["categories"])
        g["shingles"] = le.shingles(g["anchor"])
    return list(groups.values())


# ---------------------------------------------------------------------------
# 核验
# ---------------------------------------------------------------------------

def check_unsupported(draft_numbers, src_by_key, src_numbers):
    findings = []
    for d in draft_numbers:
        if d["key"] in src_by_key:
            continue
        same_value = [s for s in src_numbers
                      if le.norm_value(s["value"]) == le.norm_value(d["value"])]
        if same_value:
            s = same_value[0]
            hint = ("数值 %s 在源文中以单位「%s」出现（%s）"
                    % (d["value"], s["unit"] or "（无）", s["locator"]))
            suggestion = ("疑似单位错配：请核对单位，源文为「%s」。"
                          % (s["unit"] or "（无单位）"))
        else:
            cands = sorted({s["value"] for s in src_numbers
                            if s["unit"] == d["unit"]})
            hint = ("源文中单位为「%s」的数值：%s"
                    % (d["unit"] or "（无）", "、".join(cands[:5]) or "无"))
            suggestion = "疑似数字漂移：请对照台账核对数值与单位。"
        findings.append({
            "kind": "unsupported_number",
            "severity": "mandatory",
            "draft_locator": d["locator"],
            "draft_anchor": d["anchor"],
            "raw": d["raw"],
            "value": d["value"],
            "unit": d["unit"],
            "hint": hint,
            "suggestion": suggestion,
        })
    return findings


def check_dropped(src_entries, draft_keys_num, draft_keys_fig, draft_keys_cit):
    findings = []
    for s in src_entries:
        kind = s["kind"]
        if kind == "number":
            present = s["key"] in draft_keys_num
        elif kind == "figure_ref":
            present = s["key"] in draft_keys_fig
        elif kind == "citation":
            present = s["key"] in draft_keys_cit
        else:
            continue
        if present:
            continue
        findings.append({
            "kind": "dropped_evidence",
            "severity": DROP_SEVERITY[kind],
            "category": kind,
            "source_id": s["id"],
            "source_locator": s["locator"],
            "source_anchor": s["anchor"],
            "raw": s["raw"],
            "suggestion": ("该证据（%s）未在改写稿中出现；默认必须保留，"
                           "请恢复，或在交付说明中写明删减理由"
                           "（保留优先级见 references/retention_priority.md）。"
                           % s["raw"]),
        })
    return findings


def check_strength(draft_groups, src_groups):
    findings = []
    for d in draft_groups:
        best, best_sim = None, 0.0
        for s in src_groups:
            sim = le.jaccard(d["shingles"], s["shingles"])
            if sim > best_sim:
                best, best_sim = s, sim
        if best is None or best_sim < SIM_THRESHOLD:
            continue  # 无法配对：不判（见 SKILL.md「局限」）
        if d["level"] > best["level"] + 1e-9:
            findings.append({
                "kind": "strength_upgrade",
                "severity": "mandatory",
                "draft_locator": d["locator"],
                "draft_anchor": d["anchor"],
                "source_locator": best["locator"],
                "source_anchor": best["anchor"],
                "source_words": best["words"],
                "draft_words": d["words"],
                "source_level": le.LEVEL_LABELS[best["level"]],
                "draft_level": le.LEVEL_LABELS[d["level"]],
                "similarity": round(best_sim, 3),
                "suggestion": ("论断强度由源文「%s」（%s）升格为「%s」（%s）；"
                               "建议改用与源文同级的表述。"
                               % ("、".join(best["words"]), le.LEVEL_LABELS[best["level"]],
                                  "、".join(d["words"]), le.LEVEL_LABELS[d["level"]])),
            })
    return findings


# ---------------------------------------------------------------------------
# Markdown 报告
# ---------------------------------------------------------------------------

def render_md(report):
    s = report["summary"]
    lines = [
        "# 事实核验报告（fact_check_report）",
        "",
        "- 工具：fact_check %s（基于 ledger_extract 台账）" % report["version"],
        "- 台账：`%s`" % report["inputs"]["ledger"],
        "- 改写稿：`%s`" % report["inputs"]["draft"],
        "- 失败判定阈值（--min-severity）：%s" % report["min_severity"],
        "- 结论：**%s**（退出码 %d）" % (s["status"], s["exit_code"]),
        "",
        "## 汇总",
        "",
        "| 类别 | 条数 |",
        "| --- | --- |",
    ]
    for k in ("unsupported_number", "dropped_evidence", "strength_upgrade"):
        lines.append("| %s（%s） | %d |" % (k, KIND_LABEL[k], s["by_kind"].get(k, 0)))
    lines += [
        "| **合计** | **%d**（其中计入失败判定 %d 条） |" % (
            s["findings_total"], s["findings_blocking"]),
        "",
        "核验覆盖面：改写稿数字 %d 个；台账数字 %d 个、图表引用 %d 个、引用标记 %d 个；"
        "论断句配对 %d 组。" % (
            s["checked"]["draft_numbers"], s["checked"]["source_numbers"],
            s["checked"]["source_figure_refs"], s["checked"]["source_citations"],
            s["checked"]["strength_pairs"]),
        "",
        "## 逐条发现",
        "",
    ]
    if not report["findings"]:
        lines.append("未发现 drift：改写稿通过全部核验。")
        lines.append("")
        return "\n".join(lines)
    for i, f in enumerate(report["findings"], 1):
        lines.append("### %d. [%s] %s（严重度：%s）" % (
            i, f["kind"], KIND_LABEL[f["kind"]], f["severity"]))
        lines.append("")
        if f["kind"] == "unsupported_number":
            lines += [
                "- 改写稿位置：`%s`" % f["draft_locator"],
                "- 改写稿锚句：%s" % f["draft_anchor"],
                "- 问题值：%s（单位：%s）" % (f["raw"], f["unit"] or "（无）"),
                "- 线索：%s" % f["hint"],
            ]
        elif f["kind"] == "dropped_evidence":
            lines += [
                "- 台账条目：`%s`（%s，位于 `%s`）" % (
                    f["source_id"], f["category"], f["source_locator"]),
                "- 源文锚句：%s" % f["source_anchor"],
                "- 丢失内容：%s" % f["raw"],
            ]
        else:
            lines += [
                "- 改写稿位置：`%s`" % f["draft_locator"],
                "- 改写稿锚句：%s" % f["draft_anchor"],
                "- 源文位置：`%s`（配对相似度 %s）" % (
                    f["source_locator"], f["similarity"]),
                "- 源文锚句：%s" % f["source_anchor"],
                "- 强度变化：%s → **%s**" % (f["source_level"], f["draft_level"]),
            ]
        lines += [
            "- 修复建议：%s" % f["suggestion"],
            "",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(ledger_path, draft_path, min_severity):
    with open(ledger_path, "r", encoding="utf-8") as f:
        ledger = json.load(f)
    if not isinstance(ledger, dict) or "entries" not in ledger:
        raise ValueError("台账 JSON 缺少 entries 字段：%s" % ledger_path)
    with open(draft_path, "r", encoding="utf-8") as f:
        draft_text = f.read()

    src_entries = ledger["entries"]
    src_numbers = [e for e in src_entries if e["kind"] == "number"]
    src_by_key = {e["key"] for e in src_numbers}

    draft_entries = le.scan_text(draft_text, draft_path, {})
    draft_numbers = [e for e in draft_entries if e["kind"] == "number"]
    draft_keys_num = {e["key"] for e in draft_numbers}
    draft_keys_fig = {e["key"] for e in draft_entries if e["kind"] == "figure_ref"}
    draft_keys_cit = {e["key"] for e in draft_entries if e["kind"] == "citation"}

    findings = []
    findings += check_unsupported(draft_numbers, src_by_key, src_numbers)
    findings += check_dropped(src_entries, draft_keys_num,
                              draft_keys_fig, draft_keys_cit)
    src_groups = group_strength(src_entries)
    draft_groups = group_strength(draft_entries)
    findings += check_strength(draft_groups, src_groups)

    findings.sort(key=lambda f: (KIND_ORDER[f["kind"]],
                                 f.get("draft_locator") or f.get("source_locator") or "",
                                 f.get("raw", "")))
    threshold = SEVERITY_RANK[min_severity]
    blocking = [f for f in findings
                if SEVERITY_RANK[f["severity"]] >= threshold]
    by_kind = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    status = "FAIL" if blocking else "PASS"
    exit_code = 3 if blocking else 0

    return {
        "tool": "fact_check",
        "version": VERSION,
        "inputs": {"ledger": ledger_path, "draft": draft_path},
        "min_severity": min_severity,
        "summary": {
            "status": status,
            "exit_code": exit_code,
            "findings_total": len(findings),
            "findings_blocking": len(blocking),
            "by_kind": by_kind,
            "checked": {
                "draft_numbers": len(draft_numbers),
                "source_numbers": len(src_numbers),
                "source_figure_refs": sum(1 for e in src_entries
                                          if e["kind"] == "figure_ref"),
                "source_citations": sum(1 for e in src_entries
                                        if e["kind"] == "citation"),
                "strength_pairs": len(draft_groups),
            },
        },
        "findings": findings,
    }, exit_code


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="改写稿事实核验：对照证据台账检出数字漂移、单位错配、"
                    "图表/引用丢失与论断强度升格。",
        epilog="退出码：0=无 drift（PASS）；3=发现 drift（FAIL）；"
               "2=用法或输入/输出错误。")
    ap.add_argument("--ledger", required=True, help="evidence_ledger.json 路径")
    ap.add_argument("--draft", required=True, help="改写稿文本路径（md/txt）")
    ap.add_argument("--json-out", default="fact_check_report.json",
                    help="JSON 报告输出路径（默认 fact_check_report.json）")
    ap.add_argument("--md-out", default=None,
                    help="Markdown 报告输出路径（可选）")
    ap.add_argument("--min-severity", choices=["mandatory", "recommended"],
                    default="mandatory",
                    help="计入失败判定的最低严重度（默认 mandatory；"
                         "recommended 时引用标记丢失也判 FAIL）")
    args = ap.parse_args(argv)

    for p in (args.ledger, args.draft):
        if not os.path.isfile(p):
            print("ERROR: 文件不存在：%s" % p, file=sys.stderr)
            return 2
    try:
        report, exit_code = run(args.ledger, args.draft, args.min_severity)
    except (OSError, UnicodeDecodeError, ValueError,
            json.JSONDecodeError) as e:
        print("ERROR: 核验失败：%s" % e, file=sys.stderr)
        return 2

    try:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if args.md_out:
            with open(args.md_out, "w", encoding="utf-8") as f:
                f.write(render_md(report))
    except OSError as e:
        print("ERROR: 写入报告失败：%s" % e, file=sys.stderr)
        return 2

    s = report["summary"]
    print("fact_check: %s（退出码 %d） findings=%d (blocking=%d) "
          "unsupported_number=%d dropped_evidence=%d strength_upgrade=%d -> %s"
          % (s["status"], s["exit_code"], s["findings_total"],
             s["findings_blocking"], s["by_kind"].get("unsupported_number", 0),
             s["by_kind"].get("dropped_evidence", 0),
             s["by_kind"].get("strength_upgrade", 0), args.json_out))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
