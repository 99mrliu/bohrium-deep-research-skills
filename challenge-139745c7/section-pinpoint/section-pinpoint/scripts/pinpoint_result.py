#!/usr/bin/env python3
"""Assemble /app/output/result.json for section-pinpoint.

Usage: pinpoint_result.py CASE_JSON WORK_DIR OUT_JSON
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

    hits = load("hits.json", {})
    report = load("ingest_report.json", {})
    uncertainty = []
    for rel, st in (report.get("files") or {}).items():
        if any(k in st for k in ("failed", "no_pdf_tool", "needs_ocr",
                                 "unsupported", "error")):
            uncertainty.append("文件 %s 抽取状态 %s，其内容可能未进入检索" % (rel, st))
    if not hits:
        uncertainty.append("hits.json 缺失：检索步骤未完成")

    result = {
        "case_id": hits.get("case_id") or case.get("case_id") or "unknown",
        "status": "complete" if hits and report else "partial",
        "summary": "库内 %d 个文件切出 %d 个锚点；%d 个提问中 %d 个完成章节级定位" % (
            len(report.get("files", {})), report.get("n_anchors", 0),
            len(hits.get("results", [])),
            sum(1 for e in hits.get("results", []) if e["status"] == "located")),
        "results": hits.get("results", []),
        "ingest_report": report.get("files", {}),
        "locator_scheme": "file › p<物理页> › §<章节路径> › ¶<段序号>；"
                          "每条命中带逐字锚点句与字符区间，可按 locator 复核",
        "uncertainty": uncertainty,
    }
    alias = {"answers": "results", "locations": "results", "evidence": "results",
             "files": "ingest_report", "notes": "uncertainty",
             "errors": "uncertainty"}
    for f in fields:
        if f not in result:
            result[f] = result.get(alias.get(f))
            if result[f] is None:
                uncertainty.append("output_contract 字段 %r 无对应产物，置 null" % f)
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    src = os.path.join(work, "anchors.jsonl")
    if os.path.exists(src):
        shutil.copy(src, os.path.join(os.path.dirname(out_p), "anchors.jsonl"))
    print(json.dumps({"status": result["status"], "contract_fields": fields},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
