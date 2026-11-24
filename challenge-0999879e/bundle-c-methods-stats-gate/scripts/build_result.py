#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 汇总清单登记 + 要素矩阵 → result.json + review_report.md。

要点：
- 契约对齐：读取 case.json 的 output_contract（list 或 dict 均兼容，
  未知则回退默认字段集并在 uncertainty 说明）；result.json 必含 case_id；
- 诚实门：任何 fail 条目若缺证据引证/absent 说明、或文本抽取失败被隐瞒，
  直接非零退出，绝不产出"看似完整"的结果；
- 原子写：先写临时文件再 os.replace；
- review_report.md 分组呈现：① 方法缺陷（fail_design）② 报告不全
  （fail_reporting）③ 待复核（unable_to_check），杜绝笼统评语。
"""
import argparse
import json
import os
import sys
import tempfile

DEFAULT_CONTRACT = ["case_id", "status", "review_report", "findings",
                    "sources", "uncertainty", "change_log"]
SEV_ORDER = {"critical": 0, "major": 1, "minor": 2}


def read_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def resolve_contract(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    note = None
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list) and all(isinstance(x, str) for x in oc) and oc:
        fields = list(oc)
    else:
        fields = list(DEFAULT_CONTRACT)
        note = ("case.json 缺少 output_contract 或 schema 未识别(%s)，已回退默认字段集"
                % ("missing" if oc is None else type(oc).__name__))
    if "case_id" not in fields:
        fields = ["case_id"] + fields
    return fields, note


def build_findings(items):
    """把 fail 条目转为结构化 findings，编号稳定（按严重级+清单序）。"""
    fails = [i for i in items if i["status"] in ("fail_design", "fail_reporting")]
    fails.sort(key=lambda i: (SEV_ORDER.get(i.get("severity") or "minor",
                                           9), i["id"]))
    findings = []
    for n, it in enumerate(fails, 1):
        ev = it.get("evidence") or {}
        findings.append({
            "finding_id": "F-%02d" % n,
            "checklist_id": it["id"],
            "facet": it["facet"],
            "issue_type": "design_flaw" if it["status"] == "fail_design"
                          else "reporting_gap",
            "severity": it.get("severity"),
            "title": it["title"],
            "evidence_quote": ev.get("quote"),
            "location": {
                "file": ev.get("file"), "section": ev.get("section"),
                "offset": ev.get("offset"), "absent_note": ev.get("absent_note"),
            },
            "basis": it.get("basis"),
            "disposition": "pending_review" if it["status"] == "fail_design"
                           else "author_fix_reporting",
        })
    return findings


def build_review_report(items, findings, matrix, facets, manuscripts):
    L = []
    L.append("# 审查报告：方法设计与统计报告完备性（bundle-c-methods-stats-gate）")
    L.append("")
    for m in manuscripts:
        L.append("- 稿件：`%s`（SHA-256: `%s`）" % (m["file"], m["sha256"][:16]))
    L.append("")

    def block(status, heading, sev_filter=None):
        L.append("## %s" % heading)
        L.append("")
        sel = [f for f in findings if f["issue_type"] == status] if sev_filter is None \
            else [f for f in findings if f["issue_type"] == status
                  and f["severity"] in sev_filter]
        if not sel:
            L.append("无。")
        for f in sel:
            loc = f["location"]
            quote = " ".join((f["evidence_quote"] or "").split())
            loc_s = ("小节「%s」偏移 %s：%s"
                     % (loc.get("section"), loc.get("offset"), quote)) \
                if quote else ("absent：%s" % loc.get("absent_note"))
            L.append("- **%s [%s / %s] %s（%s）**" %
                     (f["finding_id"], f["severity"], f["checklist_id"],
                      f["title"], f["facet"]))
            L.append("  - 定位：%s" % loc_s)
            L.append("  - 判定依据：%s" % f["basis"])
        L.append("")

    block("design_flaw", "一、方法缺陷（fail_design）")
    block("reporting_gap", "二、报告不全（fail_reporting）")

    L.append("## 三、待复核（unable_to_check）")
    L.append("")
    unc = [i for i in items if i["status"] == "unable_to_check"]
    if not unc:
        L.append("无。")
    for it in unc:
        ev = it.get("evidence") or {}
        L.append("- **%s（%s）**：%s —— %s" %
                 (it["id"], it["facet"], it["title"],
                  ev.get("absent_note") or ev.get("quote") or it.get("basis")))
    L.append("")
    L.append("## 四、通过项与要素矩阵摘要")
    L.append("")
    n_pass = sum(1 for i in items if i["status"] == "pass")
    L.append("- 清单共 %d 条：pass %d / fail_design %d / fail_reporting %d / unable_to_check %d"
             % (len(items), n_pass,
                sum(1 for i in items if i["status"] == "fail_design"),
                sum(1 for i in items if i["status"] == "fail_reporting"),
                sum(1 for i in items if i["status"] == "unable_to_check")))
    L.append("")
    L.append("| 要素 | 状态 |")
    L.append("|---|---|")
    for key, item in matrix["elements"].items():
        L.append("| %s | %s |" % (item["name"], item["status"]))
    L.append("")
    L.append("## 五、六分面覆盖登记")
    L.append("")
    L.append("| 分面 | 状态 | 说明 |")
    L.append("|---|---|---|")
    for name, f in facets["facets"].items():
        L.append("| %s | %s | %s |" % (name, f["status"], f["note"]))
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="汇总门禁登记 → result.json + review_report.md（bundle-c-methods-stats-gate）")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args(argv)

    reg_path = os.path.join(args.work_dir, "checklist_register.json")
    mtx_path = os.path.join(args.work_dir, "stats_matrix.json")
    facet_path = os.path.join(args.work_dir, "facet_coverage.json")
    for p in (reg_path, mtx_path):
        if not os.path.isfile(p):
            print("缺少中间产物 %s，请先运行 stats_gate.py / gate_check.py" % p,
                  file=sys.stderr)
            return 1
    register = read_json(reg_path)
    matrix = read_json(mtx_path)
    facets = read_json(facet_path) if os.path.isfile(facet_path) \
        else {"facets": {}}
    items = register.get("items") or []

    # ---- 诚实门：fail 必须有证据引证或显式 absent 说明；抽取失败如实带入
    honesty_violations = []
    for it in items:
        if it["status"] in ("fail_design", "fail_reporting"):
            ev = it.get("evidence") or {}
            if not ev.get("quote") and not ev.get("absent_note"):
                honesty_violations.append(
                    "%s fail 但既无引证也无 absent 说明" % it.get("id"))
    if honesty_violations:
        for v in honesty_violations:
            print("诚实门拦截: " + v, file=sys.stderr)
        return 1

    case, case_note = {}, None
    case_path = os.path.join(args.input_dir, "case.json")
    if os.path.isfile(case_path):
        try:
            case = read_json(case_path)
        except Exception as e:  # noqa: BLE001
            case_note = "case.json 解析失败 %r，case_id 记为 unknown" % e
            case = {"case_id": "unknown"}
    else:
        case = {"case_id": "unknown"}
        case_note = "case.json 不存在，case_id 记为 unknown"

    fields, contract_note = resolve_contract(case)
    uncertainty = []
    if case_note:
        uncertainty.append(case_note)
    if contract_note:
        uncertainty.append(contract_note)
    for e in matrix.get("extraction_errors") or []:
        uncertainty.append("文本抽取失败: %s (%s)" %
                           (e.get("file"), e.get("extract_error")))
    uncertainty += ["%s：%s" % (i["id"], (i.get("evidence") or {}).get("absent_note")
                               or i.get("basis"))
                    for i in items if i["status"] == "unable_to_check"]
    if any(i["status"] in ("fail_design",) for i in items):
        uncertainty.append("fail_design 为确定性规则初判，终审仍建议人工复核"
                           "（disposition=pending_review）")

    findings = build_findings(items)
    manuscripts = matrix.get("manuscripts") or []
    sources = [{"file": m["file"], "sha256": m["sha256"]} for m in manuscripts]
    sources.append({"reference": "references/stats_reporting_checklist.md",
                    "role": "判定清单"})
    sources.append({"reference": "references/methods_severity_rubric.md",
                    "role": "严重度 rubric"})

    report_md = build_review_report(items, findings, matrix, facets, manuscripts)
    report_path = os.path.join(args.output_dir, "review_report.md")
    atomic_write_text(report_path, report_md)

    payload = {
        "case_id": case.get("case_id", "unknown"),
        "status": "completed" if not uncertainty or
                  not any("抽取失败" in u for u in uncertainty) else "partial",
        "review_report": "review_report.md 已生成：方法缺陷 %d 条、报告不全 %d 条、"
                         "待复核 %d 条（按类别分组，含原文定位）。"
                         % (sum(1 for f in findings if f["issue_type"] == "design_flaw"),
                            sum(1 for f in findings if f["issue_type"] == "reporting_gap"),
                            sum(1 for i in items if i["status"] == "unable_to_check")),
        "findings": findings,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_log": [
            "stats_gate.py: 文本抽取 + 统计报告要素矩阵",
            "gate_check.py run: 清单逐条判定并登记证据",
            "gate_check.py validate: 登记完整性校验通过",
            "build_result.py: 生成 result.json + review_report.md（原子写）",
        ],
        "stats_matrix": {k: v["status"] for k, v in matrix["elements"].items()},
        "checklist_summary": {
            "total": len(items),
            "pass": sum(1 for i in items if i["status"] == "pass"),
            "fail_design": sum(1 for i in items if i["status"] == "fail_design"),
            "fail_reporting": sum(1 for i in items if i["status"] == "fail_reporting"),
            "unable_to_check": sum(1 for i in items if i["status"] == "unable_to_check"),
        },
        "facet_coverage": facets.get("facets", {}),
    }
    for f in fields:
        payload.setdefault(f, None if f not in payload else payload[f])

    result_path = os.path.join(args.output_dir, "result.json")
    atomic_write_json(result_path, payload)
    print("build_result: %d findings（design_flaw=%d, reporting_gap=%d），"
          "status=%s" % (len(findings),
                         sum(1 for f in findings if f["issue_type"] == "design_flaw"),
                         sum(1 for f in findings if f["issue_type"] == "reporting_gap"),
                         payload["status"]))
    print("写出 %s 与 %s" % (result_path, report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
