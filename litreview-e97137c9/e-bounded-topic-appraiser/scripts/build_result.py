#!/usr/bin/env python3
"""build_result.py — 组装 result.json 并镜像 output_contract（bundle E）。

字段来源映射（contract 字段名 → 默认内容）：
  research_product / product / decision / memo  → 决策备忘录内容 + 推荐档位汇总
  appraisal_matrix / appraisal / matrix         → 选题评分矩阵（appraise.py）
  gap_register / gaps                            → 空白登记（gap_register.py）
  facet_matrix / facets                          → facet 覆盖矩阵摘要
  uncertainties / uncertainty                    → 不确定性清单
  sources                                        → 文献清单 + sha256 + tier
  status                                         → completed | partial | blocked
  change_log / changes                           → 变更记录
未知名称的 contract 字段填 null 并在 uncertainties 说明，绝不漏字段。
research_product 中始终包含 decision memo 全文（decision_memo 键）。
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


def collect_uncertainties(work, appraisal):
    u = list(load_json(os.path.join(work, "uncertainties.json"), []))
    matrix = load_json(os.path.join(work, "facet_matrix.json"), {})
    register = load_json(os.path.join(work, "gap_register.json"), {})
    themes_source = register.get("themes_source") or matrix.get("themes_source")
    if themes_source == "coarse_facet_coclustering":
        u.append("模型未产出 work/themes.json，theme 划分采用 facet 共现粗聚类，仅供定位空白")
    if matrix.get("underpowered_facets"):
        vals = ", ".join(f["facet"] for f in matrix["underpowered_facets"][:10])
        u.append(f"{len(matrix['underpowered_facets'])} 个 facet 值仅 1 篇文献覆盖（underpowered）："
                 f"{vals}{' …' if len(matrix['underpowered_facets']) > 10 else ''}")
    if matrix.get("absent_facets"):
        u.append(f"{len(matrix['absent_facets'])} 个 facet 值在语料中 0 覆盖（absent），"
                 f"已登记为 facet_absent 空白；语料外情况未查证")
    u += appraisal.get("notes", [])
    return sorted(set(u))


def build(work, out):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    extras = load_json(os.path.join(work, "case_extras.json"), {})
    matrix = load_json(os.path.join(work, "facet_matrix.json"), {})
    register = load_json(os.path.join(work, "gap_register.json"), None)
    appraisal = load_json(os.path.join(out, "appraisal_matrix.json"), None)
    memo_path = os.path.join(out, "decision_memo.md")
    memo = open(memo_path, encoding="utf-8").read() if os.path.exists(memo_path) else ""
    change_log = load_json(os.path.join(work, "change_log.json"), [])

    usable = [d for d in docs if d.get("tier") in ("fulltext", "abstract_only")]
    if not docs or not usable:
        status = "blocked"
    elif appraisal and appraisal.get("appraisals") and memo:
        status = "completed"
    else:
        status = "partial"

    uncertainties = collect_uncertainties(work, appraisal or {})
    sources = [{"doc_id": d["doc_id"], "ref": d.get("ref"), "sha256": d.get("sha256"),
                "tier": d.get("tier"), "extract_method": d.get("extract_method"),
                "metadata": d.get("provided_metadata") or {}} for d in docs]

    recommendations = {}
    if appraisal:
        for r in appraisal.get("appraisals", []):
            recommendations[r["topic"]] = {
                "weighted_total": r["weighted_total"],
                "recommendation": r["recommendation"],
                "bound_gaps": r["bound_gaps"],
            }
    research_product = {
        "question": profile.get("research_question", ""),
        "kind": "bounded_topic_appraisal",
        "decision_memo_file": "decision_memo.md" if memo else None,
        "decision_memo": memo or None,
        "recommendations": recommendations,
        "constraints_checked": extras.get("constraints", []),
        "bottom_line": (max((r for r in appraisal.get("appraisals", [])),
                            key=lambda r: r["weighted_total"], default=None) or {}
                       ).get("topic"),
    }

    facet_summary = None
    if matrix:
        facet_summary = {
            "usable_docs": matrix.get("usable_docs"),
            "doc_facets_by_category": matrix.get("doc_facets_by_category"),
            "underpowered_facets": matrix.get("underpowered_facets"),
            "absent_facets": matrix.get("absent_facets"),
            "themes_source": matrix.get("themes_source"),
            "theme_gaps": matrix.get("theme_gaps"),
        }

    defaults = {
        "case_id": profile.get("case_id", "unknown_case"),
        "status": status,
        "research_product": research_product,
        "appraisal_matrix": appraisal,
        "gap_register": register,
        "facet_matrix": facet_summary,
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
        "product": "research_product", "decision": "research_product",
        "memo": "research_product", "decision_memo": "research_product",
        "appraisal": "appraisal_matrix", "matrix": "appraisal_matrix",
        "gaps": "gap_register", "facets": "facet_matrix",
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
        result.setdefault("research_product", research_product)
    else:
        result = {k: v for k, v in defaults.items() if v is not None or k in
                  ("case_id", "status", "research_product", "uncertainties", "sources", "change_log")}
        result["uncertainties"] = uncertainties

    # 交付便捷副本
    if register is not None:
        with open(os.path.join(out, "gap_register.json"), "w", encoding="utf-8") as f:
            json.dump(register, f, ensure_ascii=False, indent=2)
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
