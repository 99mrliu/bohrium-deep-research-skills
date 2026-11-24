#!/usr/bin/env python3
"""Handoff self-check + result.json assembly. Non-zero exit when the
checklist fails; a failing package must not be delivered as-is.

Checklist:
  1. every input file appears exactly once in manifest.json;
  2. every editable artifact (svg/html/md/csv) has a PNG preview or a
     documented exemption;
  3. result.json has case_id + all output_contract fields;
  4. unanswered questions are explicit no_match.

Usage: handoff_result.py CASE_JSON WORK_DIR RESULT_JSON
(result.json path must be inside the handoff output dir)
"""
import json
import os
import sys


def main():
    case_p, work, result_p = sys.argv[1], sys.argv[2], sys.argv[3]
    out_dir = os.path.dirname(result_p)
    case = json.load(open(case_p, encoding="utf-8"))
    contract = case.get("output_contract") or case.get("outputContract") or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract or [])

    def load(d, name, default):
        p = os.path.join(d, name)
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                return default
        return default

    scan = load(work, "scan.json", {})
    answers = load(out_dir, "answers.json", {}).get("answers", [])
    manifest = load(out_dir, "manifest.json", {})
    previews = load(out_dir, "preview_report.json", {})

    failures = []
    comp = manifest.get("completeness", {})
    if not comp.get("ok"):
        failures.append("completeness: 有输入文件未恰好映射一次")
    editable = [n for n in ("structure.svg", "index.html", "INDEX.md",
                            "metadata.csv", "tree.md")
                if os.path.exists(os.path.join(out_dir, n))]
    exempt = {"index.html": "与 INDEX.md 同内容，预览由 preview_index.png 覆盖",
              "metadata.csv": "表格内容进入 INDEX.md，预览由 preview_index.png 覆盖",
              "tree.md": "树内容进入 INDEX.md，预览由 preview_index.png 覆盖"}
    for n in editable:
        covered = ("preview_structure.png" if n == "structure.svg"
                   else "preview_index.png")
        if n in exempt:
            continue
        if not (previews.get(covered, {}) or {}).get("valid"):
            failures.append("editable artifact %s 缺有效 PNG 预览" % n)
    preview_exempt = exempt
    for n in editable:
        if n not in exempt and n not in ("structure.svg", "INDEX.md"):
            failures.append("editable artifact %s 无预览且无豁免理由" % n)

    n_no_match = sum(1 for a in answers if a["status"] == "no_match")
    result = {
        "case_id": manifest.get("case_id") or case.get("case_id") or "unknown",
        "status": "complete" if not failures else "partial",
        "summary": "交付包含 %d 个文件条目；完整性自检%s；%d 个提问（%d 个 no_match）" % (
            len(manifest.get("entries", [])),
            "通过" if comp.get("ok") else "未通过",
            len(answers), n_no_match),
        "answers": answers,
        "manifest": {"n_entries": len(manifest.get("entries", [])),
                     "completeness": comp,
                     "path": "manifest.json"},
        "deliverables": sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else [],
        "preview_exempt": preview_exempt,
        "checklist": {"completeness": comp.get("ok", False),
                      "previews": {k: v.get("valid") for k, v in previews.items()},
                      "failures": failures},
        "uncertainty": failures + ["%d 个提问 no_match，检索词见 answers.json"
                                   % n_no_match] if n_no_match else failures,
    }
    alias = {"results": "answers", "evidence": "answers", "files": "manifest",
             "inventory": "manifest", "notes": "uncertainty",
             "errors": "uncertainty"}
    for f in fields:
        if f not in result:
            result[f] = result.get(alias.get(f))
            if result[f] is None:
                result["uncertainty"].append(
                    "output_contract 字段 %r 无对应产物，置 null" % f)
                failures.append("missing contract field: %s" % f)
    cid = case.get("case_id") or case.get("id")
    if cid and result["case_id"] != cid:
        failures.append("case_id mismatch")
    result["status"] = "complete" if not failures else "partial"
    result["checklist"]["failures"] = failures
    if failures:
        result["uncertainty"] = list(dict.fromkeys(
            result["uncertainty"] + failures))

    with open(result_p, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    report = {"failures": failures, "ok": not failures}
    with open(os.path.join(out_dir, "checklist_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
