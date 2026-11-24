#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""summary_dashboard.py — 从 result.json 生成结构化摘要 dashboard.json。

内容：
  - severity 计数、type 计数、severity×type 交叉矩阵；
  - facet 覆盖率记账（facets_reviewed 若 result.json 提供 + not_reviewed 清单）；
  - 待复核清单（verdict_status 以「待复核」开头的 finding）；
  - top_actions：按 critical→major→minor→info 排序的前 3 条优先行动。

供 Agent 回复用户时直接引用，也供两次运行之间 diff 判断结论漂移。
确定性：无时间戳、无随机数。缺键不崩，exit 0。
"""
import argparse
import json
import os
import sys

SEVERITY_ORDER = ["critical", "major", "minor", "info"]


def load_json(path):
    if not os.path.isfile(path):
        return None, "file not found: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, "cannot parse %s: %s" % (path, e)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def first_sentence(text):
    s = (text or "").strip()
    for sep in ("。", "！", "？", ". ", "! ", "? "):
        idx = s.find(sep)
        if idx >= 0:
            return s[:idx + 1]
    return s


def not_reviewed_text(item):
    if isinstance(item, dict):
        facet = item.get("facet", "(未命名审查面)")
        reason = item.get("reason", "")
        return "%s —— %s" % (facet, reason) if reason else str(facet)
    return str(item)


def main():
    ap = argparse.ArgumentParser(
        description="从 result.json 生成 dashboard.json（计数、覆盖率、待复核、top 3 行动）。")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--out", required=True, help="dashboard.json 输出路径")
    args = ap.parse_args()

    result, err = load_json(args.result)
    dashboard = {"note": "结构化摘要输出，由 summary_dashboard.py 确定性生成"}
    if err:
        dashboard.update({"case_id": None, "status": "blocked", "error": err,
                          "counts": {}, "facet_coverage": {}, "pending_review": [],
                          "top_actions": []})
    else:
        findings = [f for f in as_list(result.get("findings")) if isinstance(f, dict)]
        by_severity = {s: 0 for s in SEVERITY_ORDER}
        by_type = {}
        matrix = {s: {} for s in SEVERITY_ORDER}
        for f in findings:
            sev = f.get("severity")
            t = str(f.get("type", "(unknown)"))
            by_type[t] = by_type.get(t, 0) + 1
            if sev in by_severity:
                by_severity[sev] += 1
                matrix[sev][t] = matrix[sev].get(t, 0) + 1
        pending = [{"id": f.get("id"), "type": f.get("type"),
                    "severity": f.get("severity"),
                    "verdict_status": f.get("verdict_status")}
                   for f in findings
                   if str(f.get("verdict_status", "")).startswith("待复核")]
        rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
        ordered = sorted(findings,
                         key=lambda f: (rank.get(f.get("severity"), len(SEVERITY_ORDER)),
                                        str(f.get("id", ""))))
        top_actions = [{"id": f.get("id"), "severity": f.get("severity"),
                        "type": f.get("type"),
                        "action": first_sentence(f.get("suggestion"))}
                       for f in ordered[:3]]
        not_reviewed = [not_reviewed_text(x) for x in as_list(result.get("not_reviewed"))]
        facets_reviewed = [str(x) for x in as_list(result.get("facets_reviewed"))]
        dashboard.update({
            "case_id": result.get("case_id"),
            "status": result.get("status"),
            "counts": {
                "total_findings": len(findings),
                "by_severity": by_severity,
                "by_type": dict(sorted(by_type.items())),
                "severity_by_type": matrix,
                "pending_review": len(pending),
            },
            "facet_coverage": {
                "facets_reviewed": facets_reviewed,
                "not_reviewed_count": len(not_reviewed),
                "not_reviewed": not_reviewed,
            },
            "pending_review": pending,
            "top_actions": top_actions,
        })
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
        f.write("\n")
    c = dashboard.get("counts") or {}
    print("case_id=%s status=%s findings=%s pending=%s -> %s"
          % (dashboard.get("case_id"), dashboard.get("status"),
             c.get("total_findings", 0), c.get("pending_review", 0), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
