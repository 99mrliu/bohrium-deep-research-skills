#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_check.py — 覆盖矩阵实时对账:检查清单 vs 当前 findings,更新 result.json。

用法:
    python3 coverage_check.py --checklist /app/work/checklist.json \
        --findings /app/work/findings.json \
        --result-in /app/output/result.json --result-out /app/output/result.json \
        --matrix-out /app/work/coverage_matrix.json

覆盖判定规则:
    某 facet 视为"已覆盖",当且仅当满足任一:
      a) findings 文件的 reviewed_facets 列表包含该 facet(Agent 声明已逐条过完);或
      b) 至少一条 finding 归属该 facet(facet 字段,或由 type 关键词推断)。
    否则该 facet 进入 not_reviewed 并注明原因。

状态升级纪律(硬性):
    覆盖率 < 100% 时 result.json 绝不允许 status=complete;
    全部 facet 至少过一遍才允许升 complete。输入异常时输出 partial 报告且 exit 0。
"""
import argparse
import json
import os
import sys

TYPE_TO_FACET = [
    ("cit", "citation"), ("ref", "citation"), ("引用", "citation"), ("文献", "citation"),
    ("ethic", "ethics"), ("伦理", "ethics"),
    ("priv", "privacy"), ("pii", "privacy"), ("隐私", "privacy"), ("脱敏", "privacy"),
    ("copy", "copyright"), ("licen", "copyright"), ("版权", "copyright"), ("许可", "copyright"),
    ("integr", "integrity"), ("image", "integrity"), ("诚信", "integrity"),
    ("图像", "integrity"), ("署名", "integrity"),
    ("submiss", "submission"), ("format", "submission"), ("投稿", "submission"),
    ("格式", "submission"),
]
SEVERITIES = ("critical", "major", "minor", "info")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data
    except (OSError, ValueError):
        return default


def normalize_findings(raw):
    """接受 list 或 {findings:[...], reviewed_facets:[...]} 两种形态。"""
    if isinstance(raw, list):
        return raw, []
    if isinstance(raw, dict):
        findings = raw.get("findings")
        reviewed = raw.get("reviewed_facets")
        return (findings if isinstance(findings, list) else [],
                [str(x) for x in reviewed] if isinstance(reviewed, list) else [])
    return [], []


def facet_of_finding(finding):
    if not isinstance(finding, dict):
        return None
    facet = finding.get("facet")
    if isinstance(facet, str) and facet:
        return facet
    text = " ".join(str(finding.get(k, "")) for k in ("type", "category", "id")).lower()
    for key, facet_name in TYPE_TO_FACET:
        if key in text:
            return facet_name
    return None


def build_matrix(checklist, findings, reviewed_facets):
    items = checklist.get("items") if isinstance(checklist, dict) else None
    items = items if isinstance(items, list) else []
    facets = []
    for it in items:
        f = it.get("facet") if isinstance(it, dict) else None
        if f and f not in facets:
            facets.append(f)
    # findings 里出现但清单没有的 facet 也入账(防漏记)
    finding_facets = {}
    for fd in findings:
        f = facet_of_finding(fd)
        if f:
            finding_facets[f] = finding_facets.get(f, 0) + 1
    for f in list(finding_facets) + list(reviewed_facets):
        if f and f not in facets:
            facets.append(f)

    matrix = []
    covered = 0
    for f in facets:
        checks = [it for it in items if isinstance(it, dict) and it.get("facet") == f]
        done = [it for it in checks if it.get("status") in ("已结项", "待复核")]
        nf = finding_facets.get(f, 0)
        declared_reviewed = f in reviewed_facets
        is_covered = declared_reviewed or nf > 0
        if is_covered:
            covered += 1
        matrix.append({
            "facet": f,
            "facet_label": (checklist.get("facet_labels", {}) or {}).get(f, f)
                           if isinstance(checklist, dict) else f,
            "checks_total": len(checks),
            "checks_done": len(done),
            "checks_pending": len(checks) - len(done),
            "findings_count": nf,
            "declared_reviewed": declared_reviewed,
            "covered": is_covered,
        })
    total = len(facets)
    pct = round(100.0 * covered / total, 1) if total else 0.0
    uncovered = [m["facet"] for m in matrix if not m["covered"]]
    return {"facets": matrix, "facets_total": total, "facets_covered": covered,
            "coverage_pct": pct, "uncovered_facets": uncovered}


def update_result(result, matrix, findings, notes):
    if not isinstance(result, dict):
        result = {}
    result.setdefault("case_id", "unknown-case")
    result["findings"] = findings
    result["not_reviewed"] = [
        {"facet": f,
         "reason": "覆盖矩阵判定该面未覆盖:无 findings 且 Agent 未声明已逐条审查,"
                   "如实记账,不凭空补结论"}
        for f in matrix["uncovered_facets"]
    ]
    sev = {s: 0 for s in SEVERITIES}
    for fd in findings:
        s = str(fd.get("severity", "")).lower() if isinstance(fd, dict) else ""
        if s in sev:
            sev[s] += 1
    result["summary"] = {
        "findings_count": len(findings),
        "facets_total": matrix["facets_total"],
        "facets_covered": matrix["facets_covered"],
        "coverage_pct": matrix["coverage_pct"],
        "severity_counts": sev,
        "stage": "coverage_check",
    }
    full = (matrix["facets_total"] > 0
            and matrix["facets_covered"] == matrix["facets_total"])
    if full:
        result["status"] = "complete"
        result["uncertainty"] = ("全部审查面已至少过一遍;逐条结论仍以 findings 中"
                                 " verdict_status 为准(待复核项未计入确定结论)。")
    else:
        # 硬性纪律:覆盖不足绝不允许 complete
        if result.get("status") == "complete":
            notes.append("输入 result.json 声称 complete 但覆盖率不足,已降级为 partial")
        result["status"] = "partial"
        result["uncertainty"] = (
            "审查未覆盖全部声明审查面(覆盖率 %.1f%%);未覆盖面已列入 not_reviewed,"
            "本结果为诚实 partial。" % matrix["coverage_pct"])
    log = result.get("change_log")
    log = log if isinstance(log, list) else []
    log.append({"seq": len(log) + 1, "action": "coverage_check",
                "detail": "覆盖矩阵对账:%d/%d 面覆盖(%.1f%%),findings=%d,status=%s"
                          % (matrix["facets_covered"], matrix["facets_total"],
                             matrix["coverage_pct"], len(findings), result["status"])})
    result["change_log"] = log
    if notes:
        result.setdefault("coverage_notes", []).extend(notes)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="覆盖矩阵对账:checklist × findings → 覆盖矩阵 + 更新 result.json")
    ap.add_argument("--checklist", required=True, help="checklist.json 路径")
    ap.add_argument("--findings", required=True, help="当前 findings JSON 路径")
    ap.add_argument("--result-in", default=None, help="现有 result.json(保底骨架)")
    ap.add_argument("--result-out", required=True, help="更新后 result.json 输出路径")
    ap.add_argument("--matrix-out", default=None, help="覆盖矩阵 JSON 输出路径")
    args = ap.parse_args(argv)

    notes = []
    checklist = read_json(args.checklist, {})
    if not checklist:
        notes.append("checklist.json 缺失/无法解析,按空清单处理")
    raw = read_json(args.findings, {})
    findings, reviewed = normalize_findings(raw)
    if not findings and not reviewed:
        notes.append("findings 文件缺失/为空/无法解析,按零 findings 处理")

    matrix = build_matrix(checklist, findings, reviewed)
    matrix["_header"] = "合成/运行期覆盖矩阵输出,非正式测评结果"
    matrix["case_id"] = checklist.get("case_id", "unknown-case")

    result = {}
    if args.result_in:
        result = read_json(args.result_in, {})
        if not result:
            notes.append("result-in 缺失/无法解析,从空骨架重建")
    result = update_result(result, matrix, findings, notes)
    result.setdefault("_header", "合成/运行期输出,非正式测评结果")

    out_dir = os.path.dirname(os.path.abspath(args.result_out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.result_out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if args.matrix_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.matrix_out)), exist_ok=True)
        with open(args.matrix_out, "w", encoding="utf-8") as f:
            json.dump(matrix, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": True,
        "coverage_pct": matrix["coverage_pct"],
        "facets_covered": matrix["facets_covered"],
        "facets_total": matrix["facets_total"],
        "uncovered_facets": matrix["uncovered_facets"],
        "status": result["status"],
        "notes": notes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
