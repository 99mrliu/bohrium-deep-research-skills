#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aggregate_grade.py — 按明文阈值把条目判断聚合为确定性等级。

阈值规则与 rules/grading_thresholds.md 逐条对应（R0–R6），输出 grades.json：
{"doc_id": {"grade": "high|moderate|low|ungradable",
            "derivation": ["..."],   # 分级推导链：哪条规则被哪些条目触发
            "stats": {...}}}
仅标准库。
"""
import argparse
import json
import os
import re
import sys

# ---- 明文阈值（修改时请同步 rules/grading_thresholds.md）----
NA_RATIO_UNGRADABLE = 0.6   # R1: not_assessable 占比 > 此值 → ungradable
HIGH_NA_RATIO = 0.15        # R3: high 要求 na 占比 ≤ 此值
HIGH_PARTIAL_RATIO = 0.3    # R3: high 要求 partial 占比 ≤ 此值
MODERATE_CORE_NOT_MET = 1   # R4: moderate 允许核心条目 not_met ≤ 此值
MODERATE_NA_RATIO = 0.35    # R4: moderate 要求 na 占比 ≤ 此值
ABSTRACT_CORE_NA_LOW = 3    # R5b: 仅摘要文献核心条目 not_assessable ≥ 此值 → low

ITEM_HEADER = re.compile(r"^## \[(?P<iid>[A-Z]+-\d+)\]", re.M)
CORE_LINE = re.compile(r"^-\s*核心\s*[:：]\s*(\S+)", re.M)


def log(msg):
    print("[aggregate_grade] %s" % msg, file=sys.stderr)


def default_itembank():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(os.path.join(here, "..", "itembank"))
    return cand if os.path.isdir(cand) else "itembank"


def parse_core_flags(itembank_dir):
    """从条目库解析 item_id → 是否核心条目。"""
    flags = {}
    if not os.path.isdir(itembank_dir):
        return flags
    for fn in sorted(os.listdir(itembank_dir)):
        if not fn.endswith(".md") or fn == "README.md":
            continue
        try:
            with open(os.path.join(itembank_dir, fn), "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        matches = list(ITEM_HEADER.finditer(text))
        for i, m in enumerate(matches):
            block = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            cm = CORE_LINE.search(block)
            flags[m.group("iid")] = bool(cm and cm.group(1).startswith("是"))
    return flags


def load_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return rows


def grade_doc(tier, assessments, core_flags):
    """返回 (grade, derivation, stats)。"""
    n = len(assessments)
    stats = {"n_items": n, "met": 0, "partial": 0, "not_met": 0,
             "not_assessable": 0, "core_not_met": [], "core_na": [],
             "na_ratio": None}
    for a in assessments:
        j = a.get("judgment", "not_assessable")
        stats[j] = stats.get(j, 0) + 1
        iid = a.get("item_id", "")
        if core_flags.get(iid) and j == "not_met":
            stats["core_not_met"].append(iid)
        if core_flags.get(iid) and j == "not_assessable":
            stats["core_na"].append(iid)

    derivation = []
    if tier == "failed":
        derivation.append("R0: 文献解析失败，无任何可依据文本 → ungradable")
        return "ungradable", derivation, stats
    if n == 0:
        derivation.append("R0b: 无任何条目判断（模型未提交或全部解析失败）→ ungradable")
        return "ungradable", derivation, stats

    na = stats.get("not_assessable", 0)
    na_ratio = na / float(n)
    partial_ratio = stats.get("partial", 0) / float(n)
    stats["na_ratio"] = round(na_ratio, 3)
    core_not_met = stats["core_not_met"]
    core_na = stats["core_na"]

    if na_ratio > NA_RATIO_UNGRADABLE:
        derivation.append(
            "R1: not_assessable 占比 %.2f > %.2f（%d/%d 条目不可评价）→ ungradable"
            % (na_ratio, NA_RATIO_UNGRADABLE, na, n))
        return "ungradable", derivation, stats

    if tier == "abstract_only":
        derivation.append("R5: 仅摘要文献，等级上限为 moderate（不允许 high）")
        if len(core_na) >= ABSTRACT_CORE_NA_LOW:
            derivation.append(
                "R5b: 核心条目 not_assessable %d 条 ≥ %d（%s）→ low"
                % (len(core_na), ABSTRACT_CORE_NA_LOW, ", ".join(core_na)))
            return "low", derivation, stats
        if core_not_met:
            derivation.append(
                "R5c: 核心条目 not_met %d 条（%s）→ low"
                % (len(core_not_met), ", ".join(core_not_met)))
            return "low", derivation, stats
        derivation.append("R5a: 无核心条目 not_met 且核心缺口可接受 → moderate")
        return "moderate", derivation, stats

    # 全文文献
    if (not core_not_met and not core_na
            and na_ratio <= HIGH_NA_RATIO and partial_ratio <= HIGH_PARTIAL_RATIO):
        derivation.append(
            "R3: 核心条目 not_met=0 且 not_assessable=0，na 占比 %.2f ≤ %.2f，"
            "partial 占比 %.2f ≤ %.2f → high"
            % (na_ratio, HIGH_NA_RATIO, partial_ratio, HIGH_PARTIAL_RATIO))
        return "high", derivation, stats
    if len(core_not_met) <= MODERATE_CORE_NOT_MET and na_ratio <= MODERATE_NA_RATIO:
        if core_not_met:
            derivation.append(
                "R4: 核心条目 not_met %d 条 ≤ %d（%s），na 占比 %.2f ≤ %.2f → moderate"
                % (len(core_not_met), MODERATE_CORE_NOT_MET,
                   ", ".join(core_not_met), na_ratio, MODERATE_NA_RATIO))
        else:
            derivation.append(
                "R4: 无核心条目 not_met，但 na 占比 %.2f 或核心条目存在 not_assessable（%s），"
                "不满足 R3 → moderate"
                % (na_ratio, ", ".join(core_na) if core_na else "无"))
        return "moderate", derivation, stats
    if len(core_not_met) > MODERATE_CORE_NOT_MET:
        derivation.append(
            "R6: 核心条目 not_met %d 条 > %d（%s）→ low"
            % (len(core_not_met), MODERATE_CORE_NOT_MET, ", ".join(core_not_met)))
    else:
        derivation.append(
            "R6: not_assessable 占比 %.2f > %.2f → low"
            % (na_ratio, MODERATE_NA_RATIO))
    return "low", derivation, stats


def main():
    ap = argparse.ArgumentParser(description="条目判断聚合分级")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--itembank", default=None)
    args = ap.parse_args()

    core_flags = parse_core_flags(args.itembank or default_itembank())
    tiers = {}
    for rec in load_jsonl(os.path.join(args.work, "docs.jsonl")):
        tiers[rec["doc_id"]] = rec.get("tier", "failed")

    vdir = os.path.join(args.work, "assessments_verified")
    grades = {}
    for doc_id, tier in sorted(tiers.items()):
        assessments = load_jsonl(os.path.join(vdir, doc_id + ".jsonl"))
        grade, derivation, stats = grade_doc(tier, assessments, core_flags)
        grades[doc_id] = {"grade": grade, "derivation": derivation, "stats": stats}
        log("%s → %s" % (doc_id, grade))

    with open(os.path.join(args.work, "grades.json"), "w", encoding="utf-8") as f:
        json.dump(grades, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
