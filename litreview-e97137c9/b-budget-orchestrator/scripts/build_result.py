#!/usr/bin/env python3
"""build_result.py — 组装 result.json 并镜像 output_contract（bundle B）。

字段来源映射（契约字段名 → 默认内容）：
  research_product / product / review / draft  → 草稿 + 主题 + 底线结论
  evidence_matrix / evidence / ledger          → 证据行（work/evidence_ledger.jsonl）
  screening / screening_log                    → 筛选记录
  uncertainties / uncertainty                  → 不确定性清单（含降级与异常说明）
  sources                                      → 文献清单 + sha256 + tier + 阅读深度
  change_log / changes                         → 变更记录（budget_ledger 维护）
  run_plan / plan                              → 预算分配与阅读计划
  consistency_report                           → 最近一次一致性校验报告
  requirements                                 → 硬性要求清单（requirements.md 全文）
未知名称的契约字段填 null 并在 uncertainties 说明，绝不漏字段。
status 裁定：零可用文献 → blocked；草稿存在且最近 consistency_report 通过 → completed；
其余 → partial。
"""
import json
import os
import sys


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def collect_uncertainties(work, out, plan, docs):
    u = []
    u += load_json(os.path.join(work, "uncertainties.json"), [])
    for d in plan.get("degradations", []):
        u.append(f"预算降级：{d}")
    for n in plan.get("notes", []):
        u.append(n)
    for r in plan.get("reading_plan", []):
        if r.get("depth") == "abstract" and r.get("tier") == "abstract_only":
            u.append(f"{r['doc_id']}：仅摘要可用，按 abstract 深度阅读，证据强度不超过 suggestive")
        if r.get("depth") == "sections":
            u.append(f"{r['doc_id']}：受预算约束仅章节精读，可能遗漏细节证据")
    tiers = {d["doc_id"]: d.get("tier") for d in docs}
    for did, tier in tiers.items():
        if tier == "metadata_only":
            u.append(f"{did}：仅有题录/URL 无全文，未纳入阅读计划")
        if tier == "failed":
            u.append(f"{did}：文本抽取失败，未纳入阅读计划")
    report = load_json(os.path.join(out, "consistency_report.json"), {})
    for p in report.get("problems", []):
        u.append(f"一致性校验：{p}")
    return sorted(set(u))


def build(work, out):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    plan = load_json(os.path.join(work, "run_plan.json"), {})
    themes = load_json(os.path.join(work, "themes.json"), [])
    ledger = load_jsonl(os.path.join(work, "evidence_ledger.jsonl"))
    change_log = load_json(os.path.join(work, "change_log.json"), [])
    report = load_json(os.path.join(out, "consistency_report.json"), None)
    state = load_json(os.path.join(work, "state.json"), {})

    draft_work = os.path.join(work, "review_draft.md")
    draft = ""
    if os.path.exists(draft_work):
        with open(draft_work, encoding="utf-8") as f:
            draft = f.read()
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "review_draft.md"), "w", encoding="utf-8") as f:
            f.write(draft)

    depths = {r["doc_id"]: r.get("depth") for r in plan.get("reading_plan", [])}
    usable = [d for d in docs if depths.get(d["doc_id"]) in ("full", "sections", "abstract")]

    if not docs or not usable:
        status = "blocked"
    elif draft and report and report.get("ok"):
        status = "completed"
    else:
        status = "partial"

    uncertainties = collect_uncertainties(work, out, plan, docs)
    sources = [{"doc_id": d["doc_id"], "ref": d.get("ref"), "sha256": d.get("sha256"),
                "tier": d.get("tier"), "reading_depth": depths.get(d["doc_id"], "skip"),
                "metadata": d.get("provided_metadata") or {}} for d in docs]

    research_product = {
        "question": profile.get("research_question", ""),
        "themes": themes,
        "draft_file": "review_draft.md" if draft else None,
        "draft_excerpt": draft[:1500],
        "bottom_line": "",
    }
    screening = load_json(os.path.join(work, "screening_log.json"),
                          {"note": "模型阶段未产出筛选记录" if status != "blocked" else "零可用文献"})
    req_path = os.path.join(work, "requirements.md")
    requirements = open(req_path, encoding="utf-8").read() if os.path.exists(req_path) else ""

    defaults = {
        "case_id": profile.get("case_id", "unknown_case"),
        "status": status,
        "research_product": research_product,
        "evidence_matrix": ledger,
        "screening_log": screening,
        "uncertainties": uncertainties,
        "sources": sources,
        "change_log": change_log,
        "run_plan": plan or None,
        "consistency_report": report,
        "requirements": requirements or None,
        "budget_summary": {"total": state.get("budget_total"),
                           "used": state.get("requests_used"),
                           "remaining": (state.get("budget_total", 0) or 0)
                           - (state.get("requests_used", 0) or 0)},
    }

    contract = profile.get("output_contract")
    result = {}
    fields = []
    if isinstance(contract, list):
        fields = [str(x) for x in contract]
    elif isinstance(contract, dict):
        fields = [str(k) for k in contract.keys()]
    elif isinstance(contract, str):
        fields = [contract]
    alias = {
        "product": "research_product", "review": "research_product", "draft": "research_product",
        "evidence": "evidence_matrix", "ledger": "evidence_matrix", "matrix": "evidence_matrix",
        "screening": "screening_log", "uncertainty": "uncertainties",
        "changes": "change_log", "source": "sources", "plan": "run_plan",
        "consistency": "consistency_report",
    }
    if fields:
        for f in fields:
            key = f if f in defaults else alias.get(f.lower())
            if key:
                result[f] = defaults[key]
            else:
                result[f] = None
                uncertainties.append(f"output_contract 字段 '{f}' 无对应内容，填 null")
        result.setdefault("case_id", defaults["case_id"])
        result.setdefault("status", status)
        result.setdefault("uncertainties", uncertainties)
        result.setdefault("sources", sources)
        result.setdefault("change_log", change_log)
        result.setdefault("budget_summary", defaults["budget_summary"])
    else:
        result = defaults
        result["uncertainties"] = uncertainties

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    log_path = os.path.join(work, "change_log.json")
    change_log.append(f"finalize: result.json 已组装，status={status}，"
                      f"契约字段 {len(fields) if fields else '默认结构'}")
    with open(log_path, "w", encoding="utf-8") as fp:
        json.dump(change_log, fp, ensure_ascii=False, indent=2)
    return result


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    r = build(args.work, args.out)
    print(json.dumps({"status": r.get("status"), "fields": len(r)}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
