#!/usr/bin/env python3
"""tier_and_ties.py — 显式分档（high/medium/low）与并列如实标注。

规则：
  - 档位由 config.tiers 阈值决定：score >= high_min → high；
    >= medium_min → medium；否则 low。
  - 总分（舍入后）完全相等的记录构成 tie_group，共用同一个名次
    （竞赛排名法：1, 2, 2, 4），绝不用伪精度小数强行拆开。
  - 名次即阅读优先级建议，不表达纳入/排除判定。

输入 <work>/scores.json；输出 <work>/tiers.json。
退出码：0 正常；3 输入缺失/异常。
"""
import argparse
import sys
from pathlib import Path

from common_lib import default_config_path, dump_json, eprint, load_config, load_json


def assign_tier(score, tiers_cfg):
    if score >= float(tiers_cfg["high_min"]):
        return "high"
    if score >= float(tiers_cfg["medium_min"]):
        return "medium"
    return "low"


def build_tiers(scores, tiers_cfg):
    """对 compute_scores 输出（已按 -score, record_id 排序）分档与并列标注。

    同分必相邻（排序保证），连续同分段构成 tie_group；sensitivity.py 复用。
    """
    ranked = []
    for i, s in enumerate(scores, 1):
        score = s["total_score"]
        rank = ranked[-1]["rank"] if ranked and score == ranked[-1]["total_score"] else i
        ranked.append({
            "rank": rank,
            "record_id": s["record_id"],
            "title": s.get("title"),
            "total_score": score,
            "tier": assign_tier(score, tiers_cfg),
            "tie_group": None,
        })

    # 连续同分段标注并列组
    tie_groups, tie_index, j = [], 0, 0
    while j < len(ranked):
        k = j
        while k + 1 < len(ranked) and ranked[k + 1]["total_score"] == ranked[j]["total_score"]:
            k += 1
        if k > j:
            tie_index += 1
            gid = f"T{tie_index}"
            for e in ranked[j:k + 1]:
                e["tie_group"] = gid
            tie_groups.append({"tie_group": gid,
                               "total_score": ranked[j]["total_score"],
                               "members": [e["record_id"] for e in ranked[j:k + 1]]})
        j = k + 1

    counts = {"high": 0, "medium": 0, "low": 0}
    for e in ranked:
        counts[e["tier"]] += 1
    return ranked, tie_groups, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="分档与并列标注")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    work = Path(args.work)
    cfg = load_config(args.config)
    scores = load_json(work / "scores.json")["scores"]
    ranked, tie_groups, counts = build_tiers(scores, cfg["tiers"])
    dump_json(work / "tiers.json", {
        "tier_rules": {"high": f"score >= {cfg['tiers']['high_min']}",
                       "medium": f"{cfg['tiers']['medium_min']} <= score < {cfg['tiers']['high_min']}",
                       "low": f"score < {cfg['tiers']['medium_min']}"},
        "ranked": ranked,
        "tie_groups": tie_groups,
        "tier_counts": counts,
        "note": "名次为阅读优先级建议；不构成纳入/排除判定。",
    })
    print(f"[tier_and_ties] 分档完成: high={counts['high']} medium={counts['medium']} "
          f"low={counts['low']}；并列组={len(tie_groups)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[tier_and_ties] 未预期异常: {exc!r}")
        sys.exit(3)
