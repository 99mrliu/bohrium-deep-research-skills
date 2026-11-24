#!/usr/bin/env python3
"""numeric_conflict.py — 跨文献数值冲突检测（bundle C 签名脚本 3）。

对 work/quant_normalized.jsonl 中 metric 相同且归一化 dimension 相同的跨文献数值对：
  - 相对差异 rel_diff = |a-b| / max(|a|,|b|) > 20%  → 冲突候选；
  - 双方均有 CI 且区间不重叠                      → 冲突候选。
冲突候选写 work/numeric_conflicts.json，供模型裁决（并列 contested），
脚本不自动调和、不取平均。近重复组内只取代表篇参与比较，避免同一研究的
重复版本被当成独立证据。仅用标准库。
"""
import itertools
import json
import os
import sys

REL_DIFF_THRESHOLD = 0.20
COMPARABLE_DIMS = {"ratio", "time", "mass", "length"}


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


def run(work):
    rows = load_jsonl(os.path.join(work, "quant_normalized.jsonl"))
    dup_groups = load_json(os.path.join(work, "dup_groups.json"), [])
    group_of = {}
    representatives = set()
    for g in dup_groups:
        representatives.add(g["members"][0])
        for m in g["members"]:
            group_of[m] = g["members"][0]

    eligible, skipped_dup = [], 0
    for r in rows:
        if r.get("norm_status") != "ok" or r.get("dimension") not in COMPARABLE_DIMS:
            continue
        if not r.get("metric"):
            continue
        rep = group_of.get(r["doc_id"], r["doc_id"])
        if rep != r["doc_id"]:
            skipped_dup += 1
            continue
        eligible.append(r)

    by_key = {}
    for r in eligible:
        by_key.setdefault((r["metric"], r["dimension"]), []).append(r)

    conflicts, compared = [], 0
    for (metric, dim), group in sorted(by_key.items()):
        for a, b in itertools.combinations(group, 2):
            if a["doc_id"] == b["doc_id"]:
                continue
            compared += 1
            va, vb = a["value_canonical"], b["value_canonical"]
            rel = abs(va - vb) / max(abs(va), abs(vb), 1e-9)
            reasons = []
            if rel > REL_DIFF_THRESHOLD:
                reasons.append(f"rel_diff {rel:.1%} > {REL_DIFF_THRESHOLD:.0%}")
            ci_a = (a.get("ci_low_canonical"), a.get("ci_high_canonical"))
            ci_b = (b.get("ci_low_canonical"), b.get("ci_high_canonical"))
            ci_overlap = None
            if None not in ci_a and None not in ci_b:
                ci_overlap = not (ci_a[1] < ci_b[0] or ci_b[1] < ci_a[0])
                if not ci_overlap:
                    reasons.append("ci_nonoverlap")
            if reasons:
                conflicts.append({
                    "conflict_id": f"C{len(conflicts) + 1}",
                    "metric": metric,
                    "dimension": dim,
                    "a": {"qid": a["qid"], "doc_id": a["doc_id"], "locator": a["locator"],
                          "value": a["value"], "unit": a["unit"],
                          "value_canonical": va, "unit_canonical": a["unit_canonical"],
                          "ci_canonical": list(ci_a) if None not in ci_a else None},
                    "b": {"qid": b["qid"], "doc_id": b["doc_id"], "locator": b["locator"],
                          "value": b["value"], "unit": b["unit"],
                          "value_canonical": vb, "unit_canonical": b["unit_canonical"],
                          "ci_canonical": list(ci_b) if None not in ci_b else None},
                    "rel_diff": round(rel, 6),
                    "ci_overlap": ci_overlap,
                    "reasons": reasons,
                    "adjudication": "pending_model_review",
                })

    report = {
        "threshold_rel_diff": REL_DIFF_THRESHOLD,
        "compared_pairs": compared,
        "skipped_duplicate_candidates": skipped_dup,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "note": "冲突候选供模型裁决（并列 contested，说明对象/条件差异），脚本不自动调和、不取平均。",
    }
    with open(os.path.join(work, "numeric_conflicts.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    rep = run(args.work)
    print(json.dumps({"compared_pairs": rep["compared_pairs"],
                      "conflicts": rep["conflict_count"],
                      "skipped_duplicate_candidates": rep["skipped_duplicate_candidates"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
