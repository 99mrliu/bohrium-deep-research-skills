#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_consistency.py — 交付前三方一致性门（报告 ↔ 结果表 ↔ result.json）。

校验内容：
  A 输入产物存在且可解析（case/result/cleaned/ledger/summary/报告/图表索引）
  B summary.json 全部统计字段与 cleaned.csv+ledger.csv 重算值一致
  C result.json 含 case.json output_contract 声明的全部字段，case_id 一致，status 合法
  D result.json 中已知的统计字段与重算值一致
  E 报告（md/html）与按当前产物重渲染结果逐字节一致（数字只能来自重算）
  F result.json artifact_hashes 登记的每个文件存在且 sha256 一致
  G 报告引用的图表文件与 figures_index.json 登记的图表文件均存在

任一失败：写出 consistency_check.json 并以退出码 5 终止，禁止交付。
退出码：0 全部通过；5 任一校验失败；2 用法错误。
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fill_report as fr

EXIT_PASS = 0
EXIT_FAIL = 5

SUMMARY_STAT_KEYS = [
    "total_rows", "total_fields", "missing_values_total", "missing_rate_pct",
    "duplicate_groups_removed", "unit_conversions", "outliers_flagged",
    "invalid_values_dropped", "change_records",
]

RESULT_FIELD_MAP = {
    "cleaned_rows": "total_rows",
    "total_rows": "total_rows",
    "total_fields": "total_fields",
    "missing_values_total": "missing_values_total",
    "missing_rate_pct": "missing_rate_pct",
    "duplicates_removed": "duplicate_groups_removed",
    "duplicate_groups_removed": "duplicate_groups_removed",
    "unit_conversions": "unit_conversions",
    "outliers_flagged": "outliers_flagged",
    "invalid_values_dropped": "invalid_values_dropped",
    "change_records": "change_records",
}

STATUS_VALUES = {"success", "partial", "failed"}

IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def num_equal(a, b):
    try:
        return round(float(a), 2) == round(float(b), 2)
    except (TypeError, ValueError):
        return False


def finish(out_path, checks):
    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    doc = {
        "overall": overall,
        "check_count": len(checks),
        "fail_count": sum(1 for c in checks if c["status"] == "FAIL"),
        "checks": checks,
    }
    Path(out_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"[check_consistency] {overall}（失败 {doc['fail_count']}/{len(checks)}）-> {out_path}")
    return EXIT_PASS if overall == "PASS" else EXIT_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="三方一致性门 + 文件存在与 sha256 登记核验")
    ap.add_argument("--case", required=True, help="case.json（含 output_contract）")
    ap.add_argument("--result", required=True, help="result.json")
    ap.add_argument("--cleaned", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--report-md", required=True)
    ap.add_argument("--report-html", required=True)
    ap.add_argument("--figures-index", required=True)
    ap.add_argument("--out", required=True, help="consistency_check.json 输出路径")
    args = ap.parse_args(argv)

    checks = []

    def rec(name, ok, detail=""):
        checks.append({"name": name,
                       "status": "PASS" if ok else "FAIL",
                       "detail": detail})
        return ok

    inputs = {
        "case.json": args.case,
        "result.json": args.result,
        "cleaned.csv": args.cleaned,
        "ledger.csv": args.ledger,
        "summary.json": args.summary,
        "quality_report.md": args.report_md,
        "quality_report.html": args.report_html,
        "figures_index.json": args.figures_index,
    }
    missing = [label for label, p in inputs.items() if not Path(p).is_file()]
    if not rec("A.inputs_exist", not missing,
               "全部输入产物存在" if not missing else "缺件：" + "、".join(missing)):
        return finish(args.out, checks)

    try:
        stats = fr.compute_stats(args.cleaned, args.ledger)
        summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    except (OSError, ValueError, csv.Error) as e:
        rec("A.inputs_parseable", False, f"输入不可解析：{e}")
        return finish(args.out, checks)
    rec("A.inputs_parseable", True, "全部输入可解析")

    # B：summary.json 统计字段 vs 重算
    bad = []
    for k in SUMMARY_STAT_KEYS:
        if k in summary and not num_equal(summary[k], stats[k]):
            bad.append(f"{k}: summary={summary[k]!r} 重算={stats[k]!r}")
    fic_sum = summary.get("field_issue_counts")
    if fic_sum is not None:
        recomputed = {k: stats["field_issue_counts"][k]
                      for k in sorted(stats["field_issue_counts"])}
        if json.dumps(fic_sum, sort_keys=True) != json.dumps(recomputed, sort_keys=True):
            bad.append(f"field_issue_counts: summary={fic_sum!r} 重算={recomputed!r}")
    rec("B.summary_matches_recompute", not bad,
        f"已核对 {len(SUMMARY_STAT_KEYS)} 项统计字段与 field_issue_counts，全部一致"
        if not bad else "；".join(bad))

    # C：result.json 合同字段
    contract = case.get("output_contract") or {}
    required = contract.get("required_fields") or []
    miss = [f for f in required if f not in result]
    rec("C.result_contract_fields", not miss,
        f"output_contract 全部 {len(required)} 个字段齐备"
        if not miss else "缺失字段：" + "、".join(miss))
    rec("C.case_id_match",
        result.get("case_id") is not None and result.get("case_id") == case.get("case_id"),
        f"result.case_id={result.get('case_id')!r}，case.case_id={case.get('case_id')!r}")
    st = result.get("status")
    rec("C.status_honest_enum", st in STATUS_VALUES,
        f"status={st!r}（合法值：success / partial / failed）")
    rec("C.sources_uncertainty_present",
        isinstance(result.get("sources"), list) and isinstance(result.get("uncertainty"), list),
        "sources 与 uncertainty 均为数组" if isinstance(result.get("sources"), list)
        and isinstance(result.get("uncertainty"), list)
        else "sources 与 uncertainty 必须是数组（可为空数组但字段必须存在）")

    # D：result.json 统计字段 vs 重算
    bad = []
    checked = 0
    for rf, sk in RESULT_FIELD_MAP.items():
        if rf in result:
            checked += 1
            if not num_equal(result[rf], stats[sk]):
                bad.append(f"{rf}: result={result[rf]!r} 重算={stats[sk]!r}")
    rec("D.result_numbers_match_recompute", not bad,
        f"已核对 {checked} 个统计字段，全部一致" if not bad else "；".join(bad))

    # E：报告与重渲染逐字节一致
    template = Path(__file__).resolve().parent.parent / "references" / "report_template.md"
    try:
        md2, html2, _s, _p = fr.render_report(
            args.cleaned, args.ledger, args.summary, str(template),
            Path(args.figures_index), Path(args.report_md).resolve().parent)
        md_file = Path(args.report_md).read_text(encoding="utf-8")
        html_file = Path(args.report_html).read_text(encoding="utf-8")
        rec("E.report_md_deterministic", md_file == md2,
            "quality_report.md 与重渲染结果逐字节一致"
            if md_file == md2 else "quality_report.md 与重渲染结果不一致（存在非重算来源的改动）")
        rec("E.report_html_deterministic", html_file == html2,
            "quality_report.html 与重渲染结果逐字节一致"
            if html_file == html2 else "quality_report.html 与重渲染结果不一致（存在非重算来源的改动）")
    except fr.UnknownPlaceholder as e:
        rec("E.report_rerender", False, "模板含未知占位符：" + "、".join(e.names))
    except (OSError, ValueError, csv.Error) as e:
        rec("E.report_rerender", False, f"重渲染失败：{e}")

    # F：artifact_hashes 登记核验
    base = Path(args.result).resolve().parent
    hashes = result.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        rec("F.artifact_hashes", False, "result.json 缺少 artifact_hashes 登记（或为空）")
    else:
        bad = []
        for rel, want in sorted(hashes.items()):
            p = base / rel
            if not p.is_file():
                bad.append(f"{rel}：文件不存在")
                continue
            got = sha256_of(p)
            if got != want:
                bad.append(f"{rel}：sha256 不符（登记 {str(want)[:12]}…，实际 {got[:12]}…）")
        rec("F.artifact_hashes", not bad,
            f"{len(hashes)} 个登记文件存在且 sha256 全部一致" if not bad else "；".join(bad))

    # G：报告与索引引用的图表文件存在
    report_text = Path(args.report_md).read_text(encoding="utf-8")
    rdir = Path(args.report_md).resolve().parent
    bad = [src for src in IMG_LINK_RE.findall(report_text) if not (rdir / src).is_file()]
    idx = json.loads(Path(args.figures_index).read_text(encoding="utf-8"))
    idir = Path(args.figures_index).resolve().parent
    for fig in idx.get("figures", []):
        if not (idir / fig["file"]).is_file():
            bad.append(fig["file"] + "（figures_index 登记）")
    rec("G.referenced_figures_exist", not bad,
        "报告与 figures_index 引用的图表文件全部存在"
        if not bad else "缺失文件：" + "、".join(bad))

    return finish(args.out, checks)


if __name__ == "__main__":
    sys.exit(main())
