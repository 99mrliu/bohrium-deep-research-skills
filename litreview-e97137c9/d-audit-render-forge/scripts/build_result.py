#!/usr/bin/env python3
"""build_result.py — 组装 result.json 并镜像 output_contract（bundle D）。

字段来源映射（contract 字段名 → 默认内容）：
  research_product / product / review / draft  → 草稿路径 + 主题 + 底线结论
  evidence_matrix / evidence / ledger          → 证据行（标注 referenced_in_draft）
  audit_artifacts / artifacts                  → 审计包产物路径
  link_check                                   → 链接校验摘要
  uncertainties / uncertainty                  → 不确定性清单
  sources                                      → 文献清单 + sha256 + tier
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


def collect_uncertainties(work, out, docs, coverage, link_report):
    u = list(load_json(os.path.join(work, "uncertainties.json"), []))
    for d in docs:
        if d.get("tier") == "abstract_only":
            u.append(f"{d['doc_id']}：仅摘要可用，证据强度不超过 suggestive")
        if d.get("tier") == "metadata_only":
            u.append(f"{d['doc_id']}：仅有题录/URL 无全文，未纳入证据池")
        if d.get("tier") == "failed":
            u.append(f"{d['doc_id']}：文本抽取失败（{d.get('extract_method')}），未纳入")
    for g in load_json(os.path.join(work, "dup_groups.json"), []):
        u.append(f"近重复组 {g.get('members')}：仅代表篇纳入主题与证据池")
    for did in coverage.get("uncovered_documents", []):
        u.append(f"{did}：未被任何主题覆盖（见 coverage_map.json）")
    for w in link_report.get("warnings", []):
        u.append(f"link_check 警告：{w}")
    if profile_fallback_id(work):
        u.append("case_id 缺失，以文件名回退")
    return sorted(set(u))


def profile_fallback_id(work):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    return profile.get("field_probing", {}).get("case_id_from") == "filename_fallback"


def build(work, out):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    ledger = load_jsonl(os.path.join(work, "evidence_ledger.jsonl"))
    themes = load_json(os.path.join(work, "themes.json"), [])
    coverage = load_json(os.path.join(out, "coverage_map.json"), {})
    link_report = load_json(os.path.join(out, "link_check_report.json"), {})
    change_log = load_json(os.path.join(work, "change_log.json"), [])

    draft = ""
    for p in (os.path.join(out, "review_draft.md"), os.path.join(work, "review_draft.md")):
        if os.path.exists(p):
            draft = open(p, encoding="utf-8").read()
            break

    usable = [d for d in docs if d.get("tier") in ("fulltext", "abstract_only")]
    if not docs or not usable:
        status = "blocked"
    elif not draft or not ledger:
        status = "partial"
    elif link_report.get("ok") and link_report.get("marks_total", 0) > 0:
        status = "completed"
    else:
        status = "partial"

    uncertainties = collect_uncertainties(work, out, docs, coverage, link_report)
    sources = [{"doc_id": d["doc_id"], "ref": d.get("ref"), "sha256": d.get("sha256"),
                "tier": d.get("tier"), "metadata": d.get("provided_metadata") or {}}
               for d in docs]
    referenced = set()
    for eid, n in (link_report.get("referenced_counts") or {}).items():
        if n > 0:
            referenced.add(eid)
    evidence_matrix = [dict(r, referenced_in_draft=r.get("evidence_id") in referenced)
                       for r in ledger]

    research_product = {
        "question": profile.get("research_question", ""),
        "themes": themes,
        "draft_file": "review_draft.md" if draft else None,
        "draft_excerpt": draft[:1500],
        "bottom_line": "",
    }
    audit_artifacts = {
        "evidence_matrix_csv": "evidence_matrix.csv",
        "coverage_map_json": "coverage_map.json",
        "audit_report_html": "audit_report.html",
        "link_check_report": "link_check_report.json",
    }
    link_summary = {
        "ok": bool(link_report.get("ok")),
        "referenced": len(link_report.get("referenced_counts") or {}),
        "unused": len(link_report.get("unused_evidence") or []),
        "unsupported": len(link_report.get("unsupported_sentences") or []),
    }

    defaults = {
        "case_id": profile.get("case_id", "unknown_case"),
        "status": status,
        "research_product": research_product,
        "evidence_matrix": evidence_matrix,
        "audit_artifacts": audit_artifacts,
        "link_check": link_summary,
        "uncertainties": uncertainties,
        "sources": sources,
        "change_log": change_log,
    }

    contract = profile.get("output_contract")
    if isinstance(contract, list):
        fields = [str(x) for x in contract]
    elif isinstance(contract, dict):
        fields = [str(k) for k in contract.keys()]
    else:
        fields = []
    alias = {
        "product": "research_product", "review": "research_product", "draft": "research_product",
        "evidence": "evidence_matrix", "ledger": "evidence_matrix", "matrix": "evidence_matrix",
        "artifacts": "audit_artifacts", "audit": "audit_artifacts",
        "uncertainty": "uncertainties", "changes": "change_log", "source": "sources",
    }
    if fields:
        result = {}
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
