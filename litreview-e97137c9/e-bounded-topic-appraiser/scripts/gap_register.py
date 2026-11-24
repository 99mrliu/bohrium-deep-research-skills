#!/usr/bin/env python3
"""gap_register.py — 空白登记：合并 facet 缺口与未裁决冲突（bundle E 签名脚本 2）。

核心约束（见 rules/gap_evidence_binding.md）：每条空白必须绑定"已查文献清单"
（docs_checked）与绑定证据（binding_evidence）；空白只能从证据分布里长出来，
禁止"有待进一步研究"式无绑定表述。

空白来源（gap_type ∈ single_source | unresolved_conflict | facet_absent）：
  1. single_source：仅 1 篇文献覆盖的 theme（theme 优先取模型 themes.json，
     缺失则用 facet 共现粗聚类，与 facet_scan 同一逻辑）。
  2. unresolved_conflict：模型产物 work/claims.jsonl 中同 topic、direction
     相反（positive vs negative）的论断对；并列登记，不调和。
  3. facet_absent：词表中被 0 篇可用文献覆盖的 facet 值（按 facet_matrix）。

claims.jsonl 行格式（模型产物）：
  {"claim_id":"C1","doc_id":"D1","topic":"…","direction":"positive|negative|neutral",
   "statement":"…", "simulated": true|false}

产物：work/gap_register.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facet_scan  # noqa: E402

OPPOSITE = {frozenset(("positive", "negative"))}


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def norm_topic(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def run(work):
    matrix_path = os.path.join(work, "facet_matrix.json")
    if not os.path.exists(matrix_path):
        matrix = facet_scan.run(work)
    else:
        matrix = json.load(open(matrix_path, encoding="utf-8"))
    usable = matrix.get("usable_docs", [])
    doc_facets = {d: set(v) for d, v in matrix.get("doc_facets", {}).items()}

    # theme 在 gaps 阶段重新解析：模型可能已在 init 之后写入 themes.json
    themes, themes_source = facet_scan.load_themes(work, set(usable), doc_facets)

    gaps = []

    # 1) single_source themes
    for t in themes:
        if len(t["docs"]) == 1:
            gaps.append({
                "gap_type": "single_source",
                "description": (f"主题 '{t['theme']} {t['label']}' 仅由 {t['docs'][0]} 一篇文献覆盖，"
                                f"结论无法交叉验证"),
                "docs_checked": sorted(usable),
                "binding_evidence": [f"theme:{t['theme']}", f"sole_doc:{t['docs'][0]}",
                                     f"themes_source:{themes_source}"],
                "related_facets": sorted(doc_facets.get(t["docs"][0], set())),
                "theme": t["theme"],
                "docs_involved": list(t["docs"]),
            })

    # 2) unresolved_conflict（claims.jsonl 中同 topic 方向相反的论断对）
    claims = load_jsonl(os.path.join(work, "claims.jsonl"))
    by_topic = {}
    for c in claims:
        by_topic.setdefault(norm_topic(c.get("topic")), []).append(c)
    for topic, rows in sorted(by_topic.items()):
        dirs = {str(r.get("direction", "")).lower() for r in rows}
        if any(pair <= dirs for pair in OPPOSITE):
            pos = [r for r in rows if str(r.get("direction", "")).lower() == "positive"]
            neg = [r for r in rows if str(r.get("direction", "")).lower() == "negative"]
            ids = [r.get("claim_id", "?") for r in rows]
            docs_involved = sorted({r.get("doc_id") for r in rows if r.get("doc_id")})
            pair_desc = "; ".join(
                f"{p.get('claim_id','?')}({p.get('doc_id','?')}, positive) vs "
                f"{n.get('claim_id','?')}({n.get('doc_id','?')}, negative)"
                for p in pos for n in neg)
            gaps.append({
                "gap_type": "unresolved_conflict",
                "description": (f"议题 '{rows[0].get('topic', topic)}' 上存在方向相反且未裁决的论断："
                                f"{pair_desc}；并列登记，不做调和"),
                "docs_checked": docs_involved,
                "binding_evidence": [f"claim:{i}" for i in ids],
                "related_facets": sorted(set().union(
                    *(doc_facets.get(d, set()) for d in docs_involved)) if docs_involved else set()),
                "topic": rows[0].get("topic", topic),
                "docs_involved": docs_involved,
                "claims": ids,
            })

    # 3) facet_absent
    n_usable = len(usable)
    for fid in matrix.get("absent_facets", []):
        gaps.append({
            "gap_type": "facet_absent",
            "description": (f"facet '{fid}' 在全部 {n_usable} 篇可用文献中均未出现；"
                            f"该维度在语料内完全无证据"),
            "docs_checked": sorted(usable),
            "binding_evidence": [f"facet_matrix.coverage[{fid}] = 0/{n_usable}"],
            "related_facets": [fid],
            "facet": fid,
            "docs_involved": [],
        })

    for i, g in enumerate(gaps, 1):
        g_ordered = {"gap_id": f"G{i:02d}"}
        g_ordered.update(g)
        gaps[i - 1] = g_ordered

    register = {
        "n_gaps": len(gaps),
        "by_type": {t: sum(1 for g in gaps if g["gap_type"] == t)
                    for t in ("single_source", "unresolved_conflict", "facet_absent")},
        "themes_source": themes_source,
        "claims_rows": len(claims),
        "gaps": gaps,
    }
    with open(os.path.join(work, "gap_register.json"), "w", encoding="utf-8") as f:
        json.dump(register, f, ensure_ascii=False, indent=2)
    return register


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    r = run(args.work)
    print(json.dumps({"n_gaps": r["n_gaps"], "by_type": r["by_type"]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
