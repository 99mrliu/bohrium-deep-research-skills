#!/usr/bin/env python3
"""Assemble /app/output/result.json honoring the case output_contract.

Every field named in output_contract gets a real value derived from work
artifacts; unfillable fields are filled with null plus an uncertainty note,
never silently dropped.

Usage: forensics_result.py CASE_JSON WORK_DIR OUT_JSON
"""
import json
import os
import shutil
import sys

DEFAULTS = {
    "case_id": None,
    "status": "partial",
    "summary": "",
    "inventory": {},
    "answers": [],
    "excluded": [],
    "sources": [],
    "uncertainty": [],
    "change_log": [],
}


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

    profile = load("case_profile.json", {})
    inv = load("inventory.json", {})
    ans = load("answers.json", {})
    uncertainty = []
    if not inv:
        uncertainty.append("inventory.json 缺失或不可解析：审计步骤未完成")
    if not profile.get("library_root"):
        uncertainty.append("未能从 case.json 定位文档库根目录")

    result = dict(DEFAULTS)
    result["case_id"] = profile.get("case_id") or case.get("case_id") or "unknown"
    result["status"] = "complete" if inv and not uncertainty else "partial"
    result["summary"] = "审计 %d 个文件，%d 个通过；回答 %d 个提问" % (
        inv.get("n_files", 0), inv.get("n_verified", 0), len(ans.get("answers", [])))
    result["inventory"] = {"n_files": inv.get("n_files"),
                           "n_verified": inv.get("n_verified"),
                           "report": "FORENSICS_REPORT.md",
                           "files": inv.get("files", [])}
    result["answers"] = ans.get("answers", [])
    result["excluded"] = ans.get("excluded_files", [])
    result["sources"] = [{"file": r["path"], "sha256_16": (r.get("sha256") or "")[:16],
                          "status": r["status"]} for r in inv.get("files", [])]
    result["uncertainty"] = uncertainty
    result["change_log"] = [{"step": "forensic_audit", "artifact": "inventory.json"},
                            {"step": "answer", "artifact": "answers.json"}]

    # honor contract: ensure every required field exists
    for f in fields:
        if f not in result:
            result[f] = None
            uncertainty.append("output_contract 字段 %r 无对应产物，置 null" % f)
    # extra contract fields filled from close matches
    alias = {"files": "inventory", "file_list": "inventory", "results": "answers",
             "evidence": "sources", "errors": "uncertainty", "notes": "uncertainty"}
    for f in fields:
        if result.get(f) is None and f in alias:
            result[f] = result[alias[f]]
            uncertainty.remove("output_contract 字段 %r 无对应产物，置 null" % f)

    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    for extra in ("FORENSICS_REPORT.md", "inventory.json", "recovery.jsonl"):
        src = os.path.join(work, extra)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(os.path.dirname(out_p), extra))
    print(json.dumps({"status": result["status"],
                      "contract_fields": fields}, ensure_ascii=False))


if __name__ == "__main__":
    main()
