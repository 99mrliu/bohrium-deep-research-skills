#!/usr/bin/env python3
"""Assemble /app/output/result.json for queryforge.

Usage: forge_result.py CASE_JSON WORK_DIR OUT_JSON
"""
import json
import os
import shutil
import sys


def main():
    case_p, work, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    case = json.load(open(case_p, encoding="utf-8"))
    contract = case.get("output_contract") or case.get("outputContract") or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])

    def load(name, default):
        p = os.path.join(work, name)
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                return default
        return default

    qr = load("query_results.json", {})
    queries = load("queries.json", {})
    uncertainty = []
    if not qr:
        uncertainty.append("query_results.json 缺失：执行步骤未完成")
    for r in qr.get("results", []):
        if r.get("unparsed_constraints"):
            uncertainty.append("提问 %s 含未结构化约束：%s" % (
                r.get("question_id"), "；".join(r["unparsed_constraints"])))

    result = {
        "case_id": qr.get("case_id") or case.get("case_id") or "unknown",
        "status": "complete" if qr else "partial",
        "summary": "库内候选 %d 个；%d 个提问中 %d 个命中、%d 个如实 no_match" % (
            qr.get("n_candidates", 0), len(qr.get("results", [])),
            sum(1 for r in qr.get("results", []) if r["status"] == "matched"),
            sum(1 for r in qr.get("results", []) if r["status"] == "no_match")),
        "results": qr.get("results", []),
        "queries": queries.get("queries", []),
        "method": "提问编译为查询 JSON；硬过滤先施加且留淘汰轨迹；"
                  "概念打分只排序不淘汰；条件无法满足如实 no_match",
        "uncertainty": uncertainty,
    }
    alias = {"answers": "results", "evidence": "results", "files": "results",
             "notes": "uncertainty", "errors": "uncertainty"}
    for f in fields:
        if f not in result:
            result[f] = result.get(alias.get(f))
            if result[f] is None:
                uncertainty.append("output_contract 字段 %r 无对应产物，置 null" % f)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    for extra in ("queries.json", "query_results.json"):
        src = os.path.join(work, extra)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(os.path.dirname(out_p), extra))
    print(json.dumps({"status": result["status"], "contract_fields": fields},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
