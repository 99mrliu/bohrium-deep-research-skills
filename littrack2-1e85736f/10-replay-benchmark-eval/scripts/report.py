#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py — 由 truth.json / metrics.json / regression.json 生成 eval_report.md。

报告所有计数均可回放到 metrics.json / truth.json 中的逐条清单（带 locator）。
仅使用 Python3 标准库，完全离线。
"""
import argparse
import json
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt(v):
    return "null" if v is None else ("%.4f" % v if isinstance(v, float) else str(v))


def loc_str(loc):
    if not loc:
        return "(无 locator)"
    return "%s[%s] doi=%s arxiv=%s title=%s" % (
        loc.get("snapshot"), loc.get("index"),
        loc.get("doi"), loc.get("arxiv_id"), loc.get("title"))


def item_lines(items, key_fields=("canonical_key",)):
    lines = []
    for it in items:
        head = "; ".join("%s=%s" % (k, it.get(k)) for k in key_fields if it.get(k))
        extra = ""
        if it.get("fp_reason"):
            extra = " | fp_reason=%s" % it["fp_reason"]
        lines.append("- %s%s | %s" % (head, extra, loc_str(it.get("locator"))))
    return lines or ["- （无）"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成评测报告 eval_report.md")
    ap.add_argument("--truth", required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--regression", default=None)
    ap.add_argument("--case", default=None, help="case.json（取 case_id 与 synthetic 标注）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    truth = load_json(args.truth)
    metrics = load_json(args.metrics)
    reg = load_json(args.regression) if args.regression else None
    case = load_json(args.case) if args.case else {}

    c, m = metrics["counts"], metrics["metrics"]
    L = []
    L.append("# 增量质量评测报告（time-replay benchmark evaluation）")
    L.append("")
    L.append("- case_id: %s" % case.get("case_id", "(未知)"))
    if case.get("synthetic"):
        L.append("- **数据性质：合成示例（synthetic）**。%s" % (case.get("synthetic_note") or ""))
    L.append("- 真值来源: %s" % truth.get("source_basis"))
    L.append("- 快照对: prev=`%s` now=`%s`" % (truth.get("snapshots", {}).get("prev"),
                                              truth.get("snapshots", {}).get("now")))
    w = truth.get("window") or {}
    L.append("- 时间窗口: %s ~ %s（两端含）" % (w.get("start"), w.get("end")))
    L.append("")
    L.append("## 1. 真值构造（机械构造，非人工标注）")
    L.append("")
    tc = truth["counts"]
    L.append("| 类别 | 条数 |")
    L.append("| --- | --- |")
    L.append("| 快照对新增候选（t_now − t_prev） | %d |" % tc["added_total"])
    L.append("| truth_new（窗口内发表） | %d |" % tc["new"])
    L.append("| truth_backfill（窗口前发表、晚入库） | %d |" % tc["backfill"])
    L.append("| truth_out_of_window（窗口后发表） | %d |" % tc["out_of_window"])
    L.append("| unclassifiable（发表日期缺失/无法解析） | %d |" % tc["unclassifiable"])
    L.append("")
    L.append("## 2. 指标总览")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("| --- | --- |")
    L.append("| precision | %s |" % fmt(m["precision"]))
    L.append("| recall | %s |" % fmt(m["recall"]))
    L.append("| duplicate_rate | %s |" % fmt(m["duplicate_rate"]))
    L.append("| false_alert_rate | %s |" % fmt(m["false_alert_rate"]))
    L.append("| backfill_misclassification | %d（占 truth_backfill 比例 %s）"
             % (m["backfill_misclassification_count"], fmt(m["backfill_misclassification_rate"])))
    L.append("")
    L.append("计数：候选条目 %d，唯一声明 %d，重复声明 %d；TP=%d FP=%d FN=%d。"
             % (c["candidate_entries"], c["unique_claims"], c["duplicates"], c["tp"], c["fp"], c["fn"]))
    L.append("")
    L.append("## 3. TP（命中真新增）")
    L.append("")
    L.extend(item_lines(metrics["tp_items"]))
    L.append("")
    L.append("## 4. FP（误报，含 backfill 误报为 new）")
    L.append("")
    L.extend(item_lines(metrics["fp_items"]))
    L.append("")
    L.append("## 5. FN（漏报的真新增）")
    L.append("")
    L.extend(item_lines(metrics["fn_items"]))
    L.append("")
    L.append("## 6. 重复声明")
    L.append("")
    if metrics["duplicate_items"]:
        for d in metrics["duplicate_items"]:
            L.append("- identity=%s | 候选第 %d 条与第 %d 条重复" % (
                d["identity"], d["first_candidate_index"], d["candidate_index"]))
    else:
        L.append("- （无）")
    L.append("")
    L.append("## 7. 回归对比")
    L.append("")
    if reg is None:
        L.append("- 未执行回归对比。")
    elif reg.get("status") != "compared":
        L.append("- status=%s：%s" % (reg.get("status"), reg.get("note", "")))
    else:
        L.append("- 基线 run: %s；verdict: **%s**" % (reg.get("baseline_run_id"), reg.get("verdict")))
        L.append("")
        L.append("| 指标 | 基线 | 本次 | delta |")
        L.append("| --- | --- | --- | --- |")
        for k, dv in (reg.get("deltas") or {}).items():
            L.append("| %s | %s | %s | %s |" % (
                k, fmt((reg.get("baseline_metrics") or {}).get(k)),
                fmt((reg.get("current_metrics") or {}).get(k)), fmt(dv)))
        L.append("")
        if reg.get("flags"):
            L.append("回归标记：")
            for f in reg["flags"]:
                L.append("- **%s**：%s" % (f["type"], f["detail"]))
        else:
            L.append("- 无回归标记。")
    L.append("")
    L.append("## 8. 假设与局限")
    L.append("")
    L.append("- 真值完全由快照对机械构造：t_now 有而 t_prev 无者 + published/窗口分类；未做人工标注。")
    L.append("- 若记录在两快照间被修改标题且缺 DOI/arXiv 号，可能被误判为新增（见 references/truth_construction.md）。")
    L.append("- backfill 判定依赖 published 字段的准确性；published 缺失者单列 unclassifiable，不猜测。")
    L.append("- 本报告只做测量，不产出、不背书任何追踪管道本身的检索结果。")
    L.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("report: %s (%d lines)" % (args.out, len(L)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
