#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_report.py — 汇总诚实 QA 报告（门禁收口）。

读取 contract_validate / evidence_spotcheck / freshness_check / metrics 的报告 JSON，
汇总为 qa_report.json + qa_report.md：
- overall_status: fail（任一子报告 fail）> warn > pass；
- blocking_items: 全部 error 级 fail 检查逐条列出（tool / id / message / locator），
  fail 时交付被阻断，必须修复后重跑；
- uncertainty: 汇总 metrics notes 与 warn 检查，作为诚实不确定项；
- 报告绝不粉饰：子报告缺失记为 warn 并说明。

用法：
    python3 qa_report.py --case case.json --result result.json \
        --reports contract.json spotcheck.json freshness.json [metrics.json] \
        --out-json qa_report.json --out-md qa_report.md

退出码：0=pass，2=warn，1=fail。仅标准库；永不访问网络。
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from qa_lib import QaError, dump_json, load_json

_STATUS_RANK = {"pass": 0, "warn": 1, "fail": 2}


def aggregate(case_path, result_path, report_paths, case=None, result=None):
    sub = []
    missing = []
    for p in report_paths:
        try:
            sub.append(load_json(p))
        except QaError:
            missing.append(str(p))

    overall = "pass"
    blocking, warnings_list, uncertainty = [], [], []
    metrics_summary = {}

    for rep in sub:
        st = rep.get("status", "fail")
        if _STATUS_RANK.get(st, 2) > _STATUS_RANK[overall]:
            overall = st
        for c in rep.get("checks", []):
            entry = {"tool": rep.get("tool"), "id": c.get("id"),
                     "message": c.get("message")}
            if c.get("locator"):
                entry["locator"] = c["locator"]
            if c.get("status") == "fail":
                blocking.append(entry)
            elif c.get("status") == "warn":
                warnings_list.append(entry)
                uncertainty.append(
                    f"[{rep.get('tool')}] {c.get('id')}: {c.get('message')}")
        if rep.get("tool") == "metrics":
            metrics_summary = rep.get("metrics", {})
            for note in rep.get("notes", []):
                if "不可计算" in note or "unknown" in note.lower():
                    uncertainty.append(f"[metrics] {note}")

    for p in missing:
        warnings_list.append({"tool": None, "id": "report.missing",
                              "message": f"子报告缺失或不可解析: {p}"})
        uncertainty.append(f"子报告缺失: {p}（该门禁结论未知）")
        if _STATUS_RANK[overall] < _STATUS_RANK["warn"]:
            overall = "warn"

    qa = {
        "tool": "qa_report",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offline": True,
        "case_file": str(case_path),
        "result_file": str(result_path),
        "case_id": (case or {}).get("case_id") or (result or {}).get("case_id"),
        "overall_status": overall,
        "gates": [{"tool": r.get("tool"), "status": r.get("status"),
                   "summary": r.get("summary")} for r in sub],
        "blocking_items": blocking,
        "warnings": warnings_list,
        "metrics": metrics_summary,
        "uncertainty": uncertainty,
        "verdict": (
            "全部质量门禁通过，result.json 可交付" if overall == "pass"
            else "存在警告项，可交付但需在 result.uncertainty 中如实披露"
            if overall == "warn"
            else "存在阻断项，禁止交付：修复 blocking_items 后重跑全部门禁"),
    }
    return qa


def render_markdown(qa):
    lines = []
    lines.append(f"# QA 报告 — {qa.get('case_id') or 'unknown case'}")
    lines.append("")
    lines.append(f"- 生成时间（UTC）: {qa['generated_at']}")
    lines.append(f"- 待检结果: `{qa['result_file']}`")
    lines.append(f"- 总体结论: **{qa['overall_status'].upper()}** — {qa['verdict']}")
    lines.append("")
    lines.append("## 各门禁状态")
    lines.append("")
    lines.append("| 门禁 | 状态 | errors | warnings |")
    lines.append("|---|---|---|---|")
    for g in qa["gates"]:
        s = g.get("summary") or {}
        lines.append(f"| {g.get('tool')} | {g.get('status')} "
                     f"| {s.get('errors', '-')} | {s.get('warnings', '-')} |")
    lines.append("")
    lines.append("## 阻断项（blocking items）")
    lines.append("")
    if qa["blocking_items"]:
        for i, b in enumerate(qa["blocking_items"], 1):
            loc = f"（locator: `{b['locator']}`）" if b.get("locator") else ""
            lines.append(f"{i}. **[{b['tool']}] {b['id']}** — {b['message']}{loc}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 警告项")
    lines.append("")
    if qa["warnings"]:
        for w in qa["warnings"]:
            lines.append(f"- [{w.get('tool')}] {w.get('id')}: {w.get('message')}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 指标")
    lines.append("")
    if qa["metrics"]:
        for k, v in qa["metrics"].items():
            s = "null" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
            lines.append(f"- `{k}` = {s}")
    else:
        lines.append("（无指标报告）")
    lines.append("")
    lines.append("## 不确定项（uncertainty）")
    lines.append("")
    if qa["uncertainty"]:
        for u in qa["uncertainty"]:
            lines.append(f"- {u}")
    else:
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总诚实 QA 报告（tracking-qa-harness）")
    ap.add_argument("--case", default=None, help="case.json 路径（可选，用于 case_id）")
    ap.add_argument("--result", required=True, help="待检 result.json 路径")
    ap.add_argument("--reports", nargs="+", required=True, help="子门禁报告 JSON 列表")
    ap.add_argument("--out-json", required=True, help="qa_report.json 输出路径")
    ap.add_argument("--out-md", default=None, help="qa_report.md 输出路径")
    args = ap.parse_args(argv)

    case = result = None
    try:
        if args.case:
            case = load_json(args.case)
        result = load_json(args.result)
    except QaError:
        pass

    qa = aggregate(args.case or "(unknown)", args.result, args.reports,
                   case=case, result=result)
    dump_json(qa, args.out_json)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(render_markdown(qa), encoding="utf-8")

    print(f"[qa_report] overall={qa['overall_status']} "
          f"blocking={len(qa['blocking_items'])} warnings={len(qa['warnings'])}")
    for b in qa["blocking_items"]:
        print(f"  BLOCKER [{b['tool']}] {b['id']}: {b['message']}")
    return {"pass": 0, "warn": 2, "fail": 1}[qa["overall_status"]]


if __name__ == "__main__":
    sys.exit(main())
