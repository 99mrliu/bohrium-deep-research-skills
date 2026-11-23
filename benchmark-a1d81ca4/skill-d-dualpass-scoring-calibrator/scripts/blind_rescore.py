#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通道 2：盲态复评，并计算逐维一致率与 Cohen's kappa。"""
import argparse
import json
import math
import sys
from collections import Counter

from score_pass import atomic_write_json, build_scores, load_json, load_sources

DIMENSION_ORDER = ["correctness", "evidence_anchoring", "completeness", "boundary_honesty"]


def score_map(pass_payload):
    result = {}
    for item in pass_payload.get("items", []) if isinstance(pass_payload, dict) else []:
        item_id = str(item.get("item_id"))
        result[item_id] = item.get("dimensions", {})
    return result


def compare_passes(pass1, pass2):
    map1 = score_map(pass1)
    map2 = score_map(pass2)
    pairs = []
    disagreements = []
    per_dimension = {key: {"agree": 0, "total": 0} for key in DIMENSION_ORDER}
    for item_id in sorted(set(map1) | set(map2)):
        dims1 = map1.get(item_id, {})
        dims2 = map2.get(item_id, {})
        for dim in DIMENSION_ORDER:
            score1 = dims1.get(dim, {}).get("score")
            score2 = dims2.get(dim, {}).get("score")
            if score1 not in (0, 1, 2) or score2 not in (0, 1, 2):
                continue
            agree = score1 == score2
            pairs.append((score1, score2))
            per_dimension.setdefault(dim, {"agree": 0, "total": 0})
            per_dimension[dim]["total"] += 1
            per_dimension[dim]["agree"] += 1 if agree else 0
            if not agree:
                disagreements.append({
                    "item": item_id,
                    "dimension": dim,
                    "pass1": score1,
                    "pass2": score2,
                    "pass1_reason": dims1.get(dim, {}).get("justification", ""),
                    "pass2_reason": dims2.get(dim, {}).get("justification", ""),
                })
    n_pairs = len(pairs)
    observed = (sum(1 for a, b in pairs if a == b) / n_pairs) if n_pairs else None
    counter1 = Counter(a for a, _ in pairs)
    counter2 = Counter(b for _, b in pairs)
    categories = sorted(set(counter1) | set(counter2))
    expected = None
    kappa = None
    degenerate = False
    if n_pairs:
        expected = sum((counter1.get(cat, 0) / n_pairs) * (counter2.get(cat, 0) / n_pairs) for cat in categories)
        if math.isclose(expected, 1.0):
            degenerate = True
        else:
            kappa = (observed - expected) / (1.0 - expected)
    dimension_agreement = {}
    for dim, stat in per_dimension.items():
        total = stat.get("total", 0)
        dimension_agreement[dim] = {
            "agree": stat.get("agree", 0),
            "total": total,
            "agreement_rate": (stat.get("agree", 0) / total) if total else None,
        }
    interpretation = "undefined_single_category" if degenerate else interpret_kappa(kappa, n_pairs)
    summary = {
        "n_pairs": n_pairs,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "cohens_kappa": kappa,
        "kappa_interpretation": interpretation,
        "degenerate_single_category": degenerate,
        "small_sample_warning": n_pairs < 30,
        "disagreement_count": len(disagreements),
        "dimension_agreement": dimension_agreement,
        "notes": kappa_notes(n_pairs, degenerate),
    }
    return summary, disagreements


def interpret_kappa(kappa, n_pairs):
    if kappa is None:
        return "undefined"
    if kappa < 0.4:
        label = "差"
    elif kappa < 0.6:
        label = "中"
    elif kappa < 0.8:
        label = "良"
    else:
        label = "优"
    return label + ("（小样本警示）" if n_pairs < 30 else "")


def kappa_notes(n_pairs, degenerate):
    notes = []
    if n_pairs < 30:
        notes.append("配对数 N<30，κ 对单个分歧非常敏感，只能作为一致性下界信号。")
    if degenerate:
        notes.append("边际分布出现单类别退化，κ 数学上无定义；应报告观察一致率并检查档位分布。")
    if not notes:
        notes.append("κ 衡量超出偶然一致的程度，不证明任一分值为真。")
    return notes


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="盲态通道 2 复评并输出一致率、Cohen's kappa 与分歧清单")
    parser.add_argument("--case", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--items", required=True)
    parser.add_argument("--semantic", required=True, help="独立 pass2 语义档位及理由")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--pass1", required=True)
    parser.add_argument("--output", required=True, help="pass2_scores.json")
    parser.add_argument("--agreement-out", required=True)
    parser.add_argument("--disagreements-out", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        case = load_json(args.case, {})
        rubric = load_json(args.rubric, {})
        items = load_json(args.items, {})
        semantic = load_json(args.semantic, {})
        if not isinstance(case, dict) or not isinstance(rubric, dict) or not isinstance(items, (dict, list)) or not isinstance(semantic, dict):
            raise ValueError("case/rubric/semantic 须为对象，items 须为对象或数组。")
        for name, payload in (("case", case), ("rubric", rubric), ("items", items), ("semantic", semantic)):
            if isinstance(payload, dict) and "_load_error" in payload:
                raise ValueError(name + " JSON 畸形: " + payload["_load_error"])
        # 盲态顺序：先独立推导并落盘 pass2，之后才读取 pass1 做一致性比较。
        pass2 = build_scores(case, rubric, items, semantic, load_sources(args.source_root), "pass2_blind")
        atomic_write_json(args.output, pass2)
        pass1 = load_json(args.pass1, {})
        if not isinstance(pass1, dict):
            raise ValueError("pass1_scores.json 畸形。")
        agreement, disagreements = compare_passes(pass1, pass2)
        atomic_write_json(args.agreement_out, agreement)
        atomic_write_json(args.disagreements_out, {"disagreements": disagreements, "count": len(disagreements)})
        print(json.dumps({"ok": True, "pass2": args.output, "n_pairs": agreement["n_pairs"], "observed_agreement": agreement["observed_agreement"], "cohens_kappa": agreement["cohens_kappa"], "disagreements": len(disagreements)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
