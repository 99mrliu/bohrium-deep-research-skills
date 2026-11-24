#!/usr/bin/env python3
"""build_result.py — 组装 result.json 并镜像 output_contract（bundle A）。

字段来源映射（contract 字段名 → 默认内容）：
  research_product / product / review / draft  → 草稿路径 + 主题 + 底线结论
  evidence_matrix / evidence / ledger          → 已验证证据行
  screening / screening_log                    → 筛选记录（若模型写了 work/screening_log.json）
  uncertainties / uncertainty                  → 不确定性清单
  sources                                      → 文献清单 + sha256 + trust
  status                                       → completed | partial | blocked
  change_log / changes                         → 变更记录
未知名称的 contract 字段填 null 并在 uncertainties 说明，绝不漏字段。
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
        return json.load(open(path, encoding="utf-8"))
    return default


def collect_uncertainties(work, out):
    u = []
    u += load_json(os.path.join(work, "uncertainties.json"), [])
    gate = load_json(os.path.join(out, "gate_report.json"), {})
    reasons = {d.get("evidence_id"): d.get("reason") for d in gate.get("details", [])}
    for eid in gate.get("failed", []):
        u.append(f"证据行 {eid} 未通过引用门控（{reasons.get(eid, '?')}），相关论断已降级或移除；详见 gate_report.json")
    for m in load_json(os.path.join(work, "source_manifest.json"), []):
        if "metadata_mismatch" in m.get("flags", []):
            u.append(f"{m['doc_id']}：case 元数据与 PDF 内容不一致（{'; '.join(m.get('identity_notes', []))}），按 T2 降级使用")
        if "retracted_or_withdrawn_marker" in m.get("flags", []):
            u.append(f"{m['doc_id']}：检测到撤稿/撤回标记，未作为实质论断来源")
        if m.get("tier") == "abstract_only":
            u.append(f"{m['doc_id']}：仅摘要可用，证据强度不超过 suggestive")
        if m.get("tier") == "metadata_only":
            u.append(f"{m['doc_id']}：仅有题录/URL 无全文，未纳入证据池")
        if m.get("tier") == "failed":
            u.append(f"{m['doc_id']}：文本抽取失败，未纳入")
    return sorted(set(u))


def build(work, out):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    manifest = load_json(os.path.join(work, "source_manifest.json"), [])
    trust = {m["doc_id"]: m["trust_tier"] for m in manifest}
    verified = load_jsonl(os.path.join(out, "evidence_ledger.verified.jsonl"))
    gate = load_json(os.path.join(out, "gate_report.json"), None)
    themes = load_json(os.path.join(work, "themes.json"), [])
    draft_path = os.path.join(out, "review_draft.md")
    draft = open(draft_path, encoding="utf-8").read() if os.path.exists(draft_path) else ""
    change_log = load_json(os.path.join(work, "change_log.json"), [])

    usable = [d for d in docs if trust.get(d["doc_id"]) in ("T1", "T2")]
    if not docs or not usable:
        status = "blocked"
    elif not draft:
        status = "partial"
    elif gate and gate.get("verified", 0) > 0:
        # 门控已就地修订草稿：残留标记均解析到已验证证据行
        status = "completed"
    else:
        status = "partial"

    uncertainties = collect_uncertainties(work, out)
    sources = [{"doc_id": d["doc_id"], "ref": d.get("ref"), "sha256": d.get("sha256"),
                "tier": d.get("tier"), "trust_tier": trust.get(d["doc_id"], "T3"),
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

    defaults = {
        "case_id": profile.get("case_id", "unknown_case"),
        "status": status,
        "research_product": research_product,
        "evidence_matrix": verified,
        "screening_log": screening,
        "uncertainties": uncertainties,
        "sources": sources,
        "change_log": change_log,
        "gate_report": gate,
    }

    contract = profile.get("output_contract")
    result = {}
    fields = []
    if isinstance(contract, list):
        fields = [str(x) for x in contract]
    elif isinstance(contract, dict):
        fields = [str(k) for k in contract.keys()]
    alias = {
        "product": "research_product", "review": "research_product", "draft": "research_product",
        "evidence": "evidence_matrix", "ledger": "evidence_matrix", "matrix": "evidence_matrix",
        "screening": "screening_log", "uncertainty": "uncertainties",
        "changes": "change_log", "source": "sources",
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
    else:
        result = defaults
        result["uncertainties"] = uncertainties

    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
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
