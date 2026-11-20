#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py -- assemble the final result.json and the human-readable
rob_report.md.

Applies the explicit domain -> overall-risk mapping table from
rules/judgment_levels.md (the derivation is recorded; no orphan grades),
mirrors every raw field of the case.json output_contract, and copies the
scale-revision suggestions into the output directory.

Reads : final/<doc_id>.jsonl (fallback: verified/, adjudicated/),
        domain_plan.json, docs.jsonl, verify_report.json,
        overrides_applied.json, adjudication_ledger.jsonl
Writes: /app/output/result.json, /app/output/rob_report.md,
        /app/output/scale_revision_suggestions.md (if present)
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu
import domain_specs as ds

SCRIPT_VERSION = "build_result/1.0"


def overall_risk(domains, grade):
    """Explicit domain -> overall mapping. Returns (level, derivation)."""
    core = [d for d in domains if d.get("core")]
    noncore = [d for d in domains if not d.get("core")]
    n = len(domains)
    n_insuf = sum(1 for d in domains if d["judgment"] == "insufficient")
    steps = []

    if grade == "abstract_only":
        steps.append("文献为 abstract_only：全文不可得，按规则整体等级"
                     "封顶为 insufficient_evidence")
        return "insufficient_evidence", steps
    if n == 0:
        return "insufficient_evidence", ["无可评价领域"]
    if n_insuf > n / 2.0:
        steps.append("%d/%d 领域判 insufficient（>50%%）→ 整体证据不足"
                     % (n_insuf, n))
        return "insufficient_evidence", steps

    core_present = [d["id"] for d in core if d["judgment"] == "present"]
    if core_present:
        steps.append("核心领域存在 present：%s → high" % ", ".join(core_present))
        return "high", steps

    likely_any = [d["id"] for d in domains if d["judgment"] == "likely"]
    core_likely = [d["id"] for d in core if d["judgment"] == "likely"]
    noncore_present = [d["id"] for d in noncore
                       if d["judgment"] == "present"]
    if len(likely_any) >= 2:
        steps.append("≥2 个领域判 likely：%s → some_concerns"
                     % ", ".join(likely_any))
        return "some_concerns", steps
    if core_likely:
        steps.append("核心领域判 likely：%s → some_concerns"
                     % ", ".join(core_likely))
        return "some_concerns", steps
    if noncore_present:
        steps.append("非核心领域判 present：%s → some_concerns"
                     % ", ".join(noncore_present))
        return "some_concerns", steps
    if n_insuf > 0:
        steps.append("无 present/likely，但 %d 个领域 insufficient；"
                     "其余未见迹象 → some_concerns（保守）" % n_insuf)
        return "some_concerns", steps
    steps.append("全部领域 no_indication（均做过主动否定性检索）→ low")
    return "low", steps


def read_final_rows(workdir, doc_id):
    for sub in ("final", "verified", "adjudicated"):
        p = os.path.join(workdir, sub, doc_id + ".jsonl")
        if os.path.exists(p):
            return cu.read_jsonl(p), sub
    return [], None


def fill_contract(contract, result):
    """Mirror every raw contract field; give real values when obvious."""
    mirrored = {"raw": contract, "fields": {}}
    items = []
    if isinstance(contract, list):
        items = [(str(x), x) for x in contract]
    elif isinstance(contract, dict):
        items = [(str(k), v) for k, v in contract.items()]
    for key, _raw in items:
        if key in result:
            mirrored["fields"][key] = result[key]
        elif key in ("documents", "results", "evaluations"):
            mirrored["fields"][key] = result.get("documents")
        else:
            mirrored["fields"][key] = None
    return mirrored


def main():
    ap = argparse.ArgumentParser(description="Build final result.json")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()

    result_path = os.path.join(args.output_dir, "result.json")
    result = cu.read_json(result_path, default={}) or {}
    result.setdefault("case_id", "unknown_case")
    result.setdefault("uncertainties", [])
    result.setdefault("change_log", [])

    docs = cu.read_jsonl(os.path.join(args.workdir, "docs.jsonl"))
    plan = {d["doc_id"]: d for d in
            cu.read_json(os.path.join(args.workdir, "domain_plan.json"),
                         default={"documents": []}).get("documents", [])}
    verify = cu.read_json(os.path.join(args.workdir, "verify_report.json"),
                          default={})
    overrides = cu.read_json(os.path.join(args.workdir,
                                          "overrides_applied.json"),
                             default={})
    ledger = cu.read_jsonl(os.path.join(args.workdir,
                                        "adjudication_ledger.jsonl"))

    out_docs = []
    for row in docs:
        doc_id = row.get("doc_id")
        pentry = plan.get(doc_id, {})
        rows, src = read_final_rows(args.workdir, doc_id)
        core_ids = {d["id"]: d["core"] for d in pentry.get("domains", [])}
        domain_evals = []
        for r in rows:
            spec = ds.DOMAIN_MAP.get(r.get("domain"), {})
            domain_evals.append({
                "domain": r.get("domain"),
                "domain_name": spec.get("name", r.get("domain")),
                "core": core_ids.get(r.get("domain"), spec.get("core")),
                "judgment": r.get("judgment"),
                "quote": r.get("quote"),
                "locator": r.get("locator"),
                "quote_verified": r.get("quote_verified"),
                "rationale": r.get("rationale"),
                "source": r.get("source"),
                "adjudicated_conservative":
                    r.get("adjudicated_conservative", False),
                "channel_p": r.get("channel_p"),
                "channel_n": r.get("channel_n"),
                "human_override": r.get("human_override"),
                "signaling_questions": [
                    {"id": q["id"], "text": q["text"]}
                    for q in spec.get("questions", [])],
            })
        for d in domain_evals:
            d["judgment"] = d["judgment"] or "insufficient"
        level, derivation = overall_risk(
            [{"id": d["domain"], "judgment": d["judgment"],
              "core": bool(d["core"])} for d in domain_evals],
            row.get("grade"))
        out_docs.append({
            "doc_id": doc_id,
            "path": row.get("path"),
            "sha256": row.get("sha256"),
            "grade": row.get("grade"),
            "extraction_method": row.get("method"),
            "word_count": row.get("word_count"),
            "doc_type": pentry.get("type"),
            "doc_type_uncertain": pentry.get("uncertain"),
            "notes": row.get("notes", []),
            "domains": domain_evals,
            "overall_risk": level,
            "overall_derivation": derivation,
            "records_from": src,
        })

    result.update({
        "status": "completed" if docs else result.get("status",
                                                      "completed_with_warnings"),
        "pipeline_stage": "build_done",
        "skill": "rob-signal-dual-adjudicator",
        "script_version": SCRIPT_VERSION,
        "finished_epoch": time.time(),
        "documents": out_docs,
        "adjudication_summary": {
            "ledger_entries": len(ledger),
            "disagreements": sum(1 for i in ledger
                                 if i.get("type") == "disagreement"),
            "channel_missing": sum(1 for i in ledger
                                   if i.get("type") == "channel_missing"),
        },
        "quote_verification": {k: verify.get(k) for k in
                               ("total_quotes", "verified", "relocated",
                                "failed") if k in verify},
        "overrides_applied": overrides.get("applied", []),
        "overrides_rejected": overrides.get("rejected", []),
    })
    if result.get("output_contract") is not None:
        result["output_contract_mirrored"] = fill_contract(
            result["output_contract"], result)
    result["change_log"].append({"stage": "build",
                                 "message": "final result.json assembled",
                                 "epoch": round(time.time(), 3)})
    cu.write_json(result_path, result)

    # --- human-readable report ---
    lines = ["# 偏倚风险评价报告（rob-signal-dual-adjudicator）",
             "",
             "- case_id: `%s`" % result.get("case_id"),
             "- 状态: `%s`" % result.get("status"),
             "- 生成时间(epoch): %s" % round(time.time(), 3),
             ""]
    for d in out_docs:
        lines.append("## 文献 `%s`（类型：%s%s；分级：%s）"
                     % (d["doc_id"], d.get("doc_type") or "?",
                        "（低置信）" if d.get("doc_type_uncertain") else "",
                        d.get("grade")))
        lines.append("**整体风险等级：%s**" % d["overall_risk"])
        for s in d["overall_derivation"]:
            lines.append("- 推导：%s" % s)
        lines.append("")
        lines.append("| 领域 | 核心 | 判定 | 裁决来源 | 证据摘录 | 页锚 |")
        lines.append("|---|---|---|---|---|---|")
        for de in d["domains"]:
            q = (de.get("quote") or "").replace("|", "\\|")[:120]
            lines.append("| %s | %s | %s%s | %s | %s | %s |" % (
                de.get("domain_name") or de.get("domain"),
                "是" if de.get("core") else "否",
                de.get("judgment"),
                "（人工改判）" if de.get("human_override") else
                ("（保守裁决）" if de.get("adjudicated_conservative") else ""),
                de.get("source") or "-",
                q or "—", de.get("locator") or "—"))
        lines.append("")
    if ledger:
        lines.append("## 裁决台账摘要")
        for i in ledger[:50]:
            lines.append("- `%s` / %s：%s → 规则 %s（%s）"
                         % (i.get("doc_id"), i.get("domain"), i.get("type"),
                            i.get("rule_applied"), i.get("detail", "")))
        lines.append("")
    with open(os.path.join(args.output_dir, "rob_report.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines))

    sugg = os.path.join(args.workdir, "scale_revision_suggestions.md")
    if os.path.exists(sugg):
        with open(sugg, "r", encoding="utf-8") as f:
            content = f.read()
        with open(os.path.join(args.output_dir,
                               "scale_revision_suggestions.md"), "w",
                  encoding="utf-8") as f:
            f.write(content)

    print({"result_json": result_path, "docs": len(out_docs),
           "status": result["status"]})


if __name__ == "__main__":
    main()
