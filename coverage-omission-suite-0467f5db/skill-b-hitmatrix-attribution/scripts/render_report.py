#!/usr/bin/env python3
"""render_report.py — 汇总覆盖率报告与 result.json。

读取 work/ 下全部中间产物，生成：
  out/coverage_report.md   人类可读覆盖率报告（分母口径、命中矩阵摘要、
                           漏检归因、补检对比、不确定性）
  out/result.json          含 case_id 与 output_contract 全部必填字段；
                           缺失字段以 null 填充并在 limitations 中说明

用法:
  python3 render_report.py --case /input/case.json --work /app/work --out /app/output

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attribute_miss import load_json  # noqa: E402


def collect_change_records(work_dir, out_dir):
    """以落盘产物为依据生成变更记录（阶段、文件、修改时间）。"""
    records = []
    for d in (work_dir, out_dir):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            records.append({
                "artifact": p,
                "mtime": datetime.fromtimestamp(
                    os.path.getmtime(p), tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                "bytes": os.path.getsize(p)})
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总覆盖率报告与 result.json。")
    ap.add_argument("--case", default="/input/case.json", help="原始 case.json 路径")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out", default="/app/output", help="产物目录（默认 /app/output）")
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.work, "case_normalized.json"))
    if case is None:
        print("ERROR: 缺少 case_normalized.json，请先运行 parse_case.py", file=sys.stderr)
        return 2
    coverage = load_json(os.path.join(args.work, "coverage.json"))
    attribution = load_json(os.path.join(args.work, "miss_attribution.json"))
    supplement = load_json(os.path.join(args.work, "supplement_eval.json"))
    queue = load_json(os.path.join(args.work, "adjudication_queue.json"))
    adjudication = load_json(os.path.join(args.work, "adjudication.json"))

    os.makedirs(args.out, exist_ok=True)
    limitations = []
    status = "ok"
    if coverage is None:
        limitations.append("缺少 coverage.json：覆盖率未复算（前置阶段未完成）")
        status = "partial"
    if attribution is None:
        limitations.append("缺少 miss_attribution.json：漏检未归因")
        status = "partial"
    if supplement is None:
        limitations.append("缺少 supplement_eval.json：未执行补检闭环")
        status = "partial"
    broken = (adjudication or {}).get("broken_files") or []
    if broken:
        limitations.append("响应文件缺失或损坏: %s" % ", ".join(broken))
        status = "partial"
    pending = (queue or {}).get("pending", 0)
    if pending:
        limitations.append("裁决队列尚有 %d 条未裁决，相关单元计 ambiguous 不计命中" % pending)
        status = "partial"
    undet = sum(1 for a in (attribution or {}).get("attributions", [])
                if a.get("primary_category") == "UNDETERMINED")
    if undet:
        limitations.append("%d 条漏检探针无法定论，类别 UNDETERMINED" % undet)
        status = "partial"

    misses = []
    for a in (attribution or {}).get("attributions", []):
        misses.append({"ref_id": a.get("ref_id"),
                       "primary_category": a.get("primary_category"),
                       "sub_reason": a.get("sub_reason"),
                       "query_id": a.get("query_id"),
                       "field": a.get("field"),
                       "date_window": a.get("date_window"),
                       "probe_evidence": a.get("probe_evidence")})

    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage": coverage,
        "misses": misses,
        "supplements": (supplement or {}).get("supplements"),
        "supplement_evaluation": {
            "before": (supplement or {}).get("before"),
            "after": (supplement or {}).get("after"),
            "recall_delta": (supplement or {}).get("recall_delta"),
            "marginal_gain": (supplement or {}).get("marginal_gain"),
            "marginal_gain_is_zero": (supplement or {}).get("marginal_gain_is_zero"),
            "skipped_categories": (supplement or {}).get("skipped_categories"),
        } if supplement else None,
        "sources": {
            "materials_dir": case.get("materials_dir"),
            "results_files": sorted({q.get("results_file")
                                     for q in case.get("search_log", [])
                                     if q.get("results_file")}),
        },
        "uncertainty": {
            "wilson_note": "覆盖率 95% 区间采用 Wilson 得分区间（z=1.96），"
                           "小样本下优于正态近似",
            "ambiguous_cells": (coverage or {}).get("ambiguous_cells"),
            "pending_adjudication": pending,
        },
        "limitations": limitations,
        "change_records": collect_change_records(args.work, args.out),
    }

    # output_contract 必填字段补齐（缺失以 null 填充并登记）
    required = (case.get("output_contract") or {}).get("required_fields") or []
    for field in required:
        if field not in result:
            result[field] = None
            limitations.append("output_contract 字段 %s 无对应产物，以 null 填充" % field)
            status = "partial"
    result["status"] = status
    result["limitations"] = limitations

    result_path = os.path.join(args.out, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 人类可读报告
    report_path = os.path.join(args.out, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 检索覆盖率与漏检归因报告\n\n")
        f.write("- case_id: %s\n" % case.get("case_id"))
        f.write("- 状态: %s\n" % status)
        f.write("- 生成时间: %s\n\n" % result["generated_at"])
        den = (coverage or {}).get("denominator", {})
        f.write("## 分母口径\n\n")
        f.write("- 可用参考数（分母）: %s\n" % den.get("usable_references"))
        f.write("- 剔除规则: %s\n" % den.get("rule"))
        for ex in den.get("excluded", []):
            f.write("  - 剔除 %s：%s\n" % (ex.get("ref_id"), ex.get("reason")))
        if coverage:
            ov = coverage["overall"]
            f.write("\n## 覆盖率（仅从命中矩阵复算）\n\n")
            f.write("- 总体: %d/%d = %.4f, Wilson95=[%.4f, %.4f]\n"
                    % (ov["hits"], ov["total"], ov["recall"] or 0.0,
                       (ov.get("wilson95") or [0, 0])[0] or 0.0,
                       (ov.get("wilson95") or [0, 0])[1] or 0.0))
            f.write("\n### 分来源\n\n| 来源 | 命中 | 召回率 | Wilson95 |\n| --- | --- | --- | --- |\n")
            for s, v in coverage.get("per_source", {}).items():
                f.write("| %s | %d/%d | %.4f | %s |\n"
                        % (s, v["hits"], v["total"], v["recall"] or 0.0, v.get("wilson95")))
            f.write("\n### 分查询\n\n| query_id | 来源 | 命中 | 召回率 |\n| --- | --- | --- | --- |\n")
            for qid, v in coverage.get("per_query", {}).items():
                f.write("| %s | %s | %d/%d | %.4f |\n"
                        % (qid, v.get("source"), v["hits"], v["total"],
                           v["recall"] or 0.0))
        if misses:
            f.write("\n## 漏检归因（每条恰好一个主类别）\n\n")
            f.write("| ref_id | 主类别 | 致漏查询 | 致漏字段 | 证据文件 | 证据片段 |\n"
                    "| --- | --- | --- | --- | --- | --- |\n")
            for m in misses:
                ev = (m.get("probe_evidence") or [{}])[-1]
                f.write("| %s | %s | %s | %s | %s | %s |\n"
                        % (m["ref_id"], m["primary_category"], m.get("query_id"),
                           m.get("field"), ev.get("file", ""),
                           str(ev.get("snippet", "")).replace("|", "\\|")[:80]))
        if supplement:
            f.write("\n## 补检前后对比（同一冻结参考集）\n\n")
            f.write("- 补检前: %.4f；补检后: %.4f；Δ=%.4f；边际增益 %d 条%s\n"
                    % ((supplement["before"] or {}).get("recall") or 0.0,
                       (supplement["after"] or {}).get("recall") or 0.0,
                       supplement.get("recall_delta") or 0.0,
                       supplement.get("marginal_gain") or 0,
                       "（零增益，如实报告）" if supplement.get("marginal_gain_is_zero") else ""))
        if limitations:
            f.write("\n## 限制与不确定性\n\n")
            for lim in limitations:
                f.write("- %s\n" % lim)
        f.write("\n## 可复算性\n\n所有覆盖率数字可由 out/hit_matrix.csv / "
                "hit_matrix.json 独立复算；漏检归因证据见 out/miss_attribution.csv。\n")

    print("render_report: status=%s, limitations=%d" % (status, len(limitations)))
    print("输出: %s ; %s" % (result_path, report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
