#!/usr/bin/env python3
"""fill_result.py — 用流水线产物填充 /app/output/result.json 并生成排序依据报告。

字段填充规则：
  - case_id / status / sources / uncertainty / change_records：通用填充；
  - 已知合同字段名（见 FIELD_FILLERS）映射到对应产物；
  - 无法由本 skill 语义填充的合同字段：置 null，并在 uncertainty 中逐字段说明
    （契约允许"填不了的填 null 并说明"），绝不编造内容。

同时写出 /app/output/ranking_rationale.md（人读排序依据报告）。
status：全部合同字段非 null → "success"；有 null 字段或有警告 → "partial"。

退出码：0 正常；2 部分字段为 null（partial）；3 关键产物缺失。
"""
import argparse
import sys
from pathlib import Path

from common_lib import dump_json, eprint, load_json

SKILL_NAME = "transparent-relevance-ranker"


def top_drivers(score_entry, n=3):
    """从分数分解中提取贡献最大的前 n 个 facet，供阅读优先级解释。"""
    facets = score_entry["decomposition"]["coverage"]["facets"]
    ranked = sorted(facets, key=lambda f: -f["contribution"])
    return [{"facet": f["facet"], "contribution": f["contribution"],
             "terms_hit": f["terms_hit"], "terms_total": f["terms_total"]}
            for f in ranked[:n] if f["contribution"] > 0]


def build_product(tiers, scores_by_id):
    """排序候选清单：名次、分数、档位、并列组、主要得分驱动。"""
    out = []
    for e in tiers["ranked"]:
        s = scores_by_id[e["record_id"]]
        out.append({
            "rank": e["rank"],
            "record_id": e["record_id"],
            "title": e["title"],
            "total_score": e["total_score"],
            "tier": e["tier"],
            "tie_group": e["tie_group"],
            "top_score_drivers": top_drivers(s),
        })
    return out


def render_rationale_md(summary, tiers, scores_by_id, sensitivity):
    """生成人读的 ranking_rationale.md：每条的分数构成、并列、稳定性。"""
    lines = [
        "# 排序依据报告（ranking rationale）",
        "",
        f"- case_id: {summary.get('case_id')}",
        f"- 研究问题: {summary.get('research_question')}",
        "- 方法：facet 覆盖加权和 + 时效分 + 文献类型权重 + 来源多样性调整；"
        "全部命中均已锚定到题名/摘要原文片段；公式与权重见 references/scoring_model.md "
        "与 config/scoring_config.json，可用同一输入复算。",
        "- 边界：本排序仅表达阅读优先级，不构成纳入/排除判定；未去重。",
        "",
        "## 分档汇总",
        "",
        f"- high: {tiers['tier_counts']['high']} 条；medium: {tiers['tier_counts']['medium']} 条；"
        f"low: {tiers['tier_counts']['low']} 条；并列组: {len(tiers['tie_groups'])} 个",
        "",
        "## 逐条依据",
        "",
    ]
    inst = {d["record_id"]: d for d in sensitivity.get("rank_instability", [])}
    for e in tiers["ranked"]:
        s = scores_by_id[e["record_id"]]
        d = s["decomposition"]
        tie = f"，并列组 {e['tie_group']}" if e["tie_group"] else ""
        lines.append(f"### #{e['rank']} {e['record_id']}（{e['tier']}{tie}）{e['title']}")
        lines.append("")
        lines.append(f"- 总分 **{e['total_score']}** = 覆盖 {d['coverage']['subtotal']}"
                     f" + 时效 {d['recency']['points']}"
                     f" + 类型 {d['publication_type']['points']}"
                     f" - 多样性 {d['diversity']['penalty']}")
        for f in d["coverage"]["facets"]:
            if f["terms_hit"]:
                terms = "、".join(sorted({h["term"] for h in f["hits"]}))
                lines.append(f"  - {f['facet']}: 权重 {f['weight']}，命中 "
                             f"{f['terms_hit']}/{f['terms_total']}（{terms}）→ {f['contribution']} 分")
        first_hits = []
        for f in d["coverage"]["facets"]:
            for h in f["hits"][:1]:
                first_hits.append(f"[{f['facet']}|{h['field']}] “{h['snippet']}”")
        if first_hits:
            lines.append(f"  - 证据片段示例: {first_hits[0]}")
        if e["record_id"] in inst:
            lines.append(f"  - ⚠ 权重扰动下换档 {inst[e['record_id']]['n_runs_changed']} 次，"
                         f"档位结论不稳，建议人工核阅")
        lines.append("")
    lines.append("## 并列说明")
    lines.append("")
    if tiers["tie_groups"]:
        for g in tiers["tie_groups"]:
            lines.append(f"- {g['tie_group']}: {', '.join(g['members'])} 同分 {g['total_score']}，"
                         f"共享名次，不以伪精度强排。")
    else:
        lines.append("- 本次无并列。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="填充 result.json 并生成排序依据报告")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args(argv)

    work, out_dir = Path(args.work), Path(args.output_dir)
    required = ["case_summary.json", "scores.json", "tiers.json", "sensitivity.json"]
    for name in required:
        if not (work / name).exists():
            eprint(f"[fill_result] 缺少产物 {name}，请先完成前序步骤")
            return 3

    summary = load_json(work / "case_summary.json")
    scores = load_json(work / "scores.json")["scores"]
    tiers = load_json(work / "tiers.json")
    sensitivity = load_json(work / "sensitivity.json")
    scores_by_id = {s["record_id"]: s for s in scores}

    product = build_product(tiers, scores_by_id)
    rationale_md = render_rationale_md(summary, tiers, scores_by_id, sensitivity)
    (out_dir).mkdir(parents=True, exist_ok=True)
    (out_dir / "ranking_rationale.md").write_text(rationale_md, encoding="utf-8")

    uncertainty = list(summary.get("warnings") or [])
    uncertainty.append("本 skill 仅产出阅读优先级排序，不构成纳入/排除判定；"
                       "合成重复导出等记录按原样排序并在 uncertainty 提示，不去重。")
    if sensitivity.get("rank_instability"):
        ids = ", ".join(d["record_id"] for d in sensitivity["rank_instability"])
        uncertainty.append(f"权重 ±20% 扰动下换档的记录：{ids}；其档位结论不稳。")

    sources = [{"type": "material", "path": m} for m in summary.get("material_files", [])]
    sources.append({"type": "config", "path": "config/scoring_config.json",
                    "note": "全部评分权重与阈值"})
    change_records = [
        {"step": "parse_case", "detail": f"解析 {summary.get('record_count')} 条题录与 output_contract"},
        {"step": "scaffold", "detail": "result.json 骨架落盘"},
        {"step": "build_facets", "detail": "facet 骨架生成，模型填写词表并通过结构校验"},
        {"step": "anchor_hits", "detail": "facet 词全部锚定到题名/摘要原文（零命中词门禁 exit 3）"},
        {"step": "score_records", "detail": "确定性评分与分数分解单"},
        {"step": "tier_and_ties", "detail": "high/medium/low 分档与并列标注"},
        {"step": "sensitivity", "detail": "facet 权重 ±20% 扰动，输出 rank instability 列表"},
        {"step": "fill_result", "detail": "填充 result.json 并生成 ranking_rationale.md"},
    ]

    counts = {"records_total": summary.get("record_count"),
              "tier_counts": tiers["tier_counts"],
              "tie_groups": len(tiers["tie_groups"]),
              "instability_records": len(sensitivity.get("rank_instability", []))}

    decomposition = {s["record_id"]: {"total_score": s["total_score"],
                                      "decomposition": s["decomposition"]}
                     for s in scores}

    result = {
        "case_id": summary.get("case_id"),
        "skill_name": SKILL_NAME,
        "status": "success",
        "product": product,
        "ranked_candidates": product,
        "ranking_rationale": "ranking_rationale.md",
        "score_decomposition": decomposition,
        "sensitivity": {"rank_instability": sensitivity.get("rank_instability", []),
                        "n_perturbation_runs": len(sensitivity.get("runs", []))},
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "counts": counts,
    }

    # 按 output_contract 核对：合同字段必须全部存在；无法填充的置 null 并说明
    null_fields = []
    for field in summary.get("output_contract") or []:
        if field not in result:
            result[field] = None
            null_fields.append(field)
    for f in null_fields:
        result["uncertainty"].append(
            f"合同字段 {f!r} 无法由 transparent-relevance-ranker 的语义填充，按契约置 null。")
    if null_fields or summary.get("warnings"):
        result["status"] = "partial"

    result.pop("_skeleton", None)
    dump_json(out_dir / "result.json", result)
    print(f"[fill_result] result.json 已填充: status={result['status']}，"
          f"null 合同字段={len(null_fields)}，产物 ranking_rationale.md 已写出")
    return 2 if result["status"] == "partial" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[fill_result] 未预期异常: {exc!r}")
        sys.exit(3)
