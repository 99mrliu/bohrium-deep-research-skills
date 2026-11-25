#!/usr/bin/env python3
"""sensitivity.py — 权重扰动稳定性检验（rank instability list）。

对每个 facet 权重分别做 +20% 与 -20% 扰动（幅度见 config.sensitivity.perturbation），
其余 facet 权重按比例缩放以保持和为 1；用与 score_records.py 完全相同的
compute_scores() 复算全部记录分数与档位。命中事实（anchors）不变，只动权重。

凡在任一扰动方案下发生换档（high/medium/low 变化）的记录进入
rank_instability 列表——这些记录的排序结论对权重选择敏感，
提示人工阅读时不应过度信赖其档位边界。

输出 <work>/sensitivity.json。
退出码：0 正常；3 输入缺失/异常。
"""
import argparse
import sys
from pathlib import Path

from common_lib import (default_config_path, dump_json, eprint, load_config,
                        load_json)
from score_records import compute_scores
from tier_and_ties import build_tiers


def perturb_weights(base, target, factor):
    """target 权重乘 factor，其余按比例缩放，使总和保持 1。"""
    new = dict(base)
    new[target] = base[target] * factor
    rest = sum(v for k, v in new.items() if k != target)
    orig_rest = sum(v for k, v in base.items() if k != target)
    if orig_rest > 0 and rest > 0:
        scale = (1.0 - new[target]) / rest if new[target] < 1.0 else 0.0
        for k in new:
            if k != target:
                new[k] = new[k] * scale
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description="权重扰动稳定性检验")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    work = Path(args.work)
    cfg = load_config(args.config)
    records = load_json(work / "records.json")
    anchors = load_json(work / "anchors.json")
    base_scores = load_json(work / "scores.json")["scores"]
    base_ranked, _, _ = build_tiers(base_scores, cfg["tiers"])
    base_tier = {e["record_id"]: e["tier"] for e in base_ranked}

    p = float(cfg.get("sensitivity", {}).get("perturbation", 0.2))
    base_weights = cfg["facet_weights"]

    runs = []
    instability = {}
    for fname in base_weights:
        for sign, label in ((1 + p, "up"), (1 - p, "down")):
            run_id = f"{fname}_{label}{int(p * 100)}pct"
            w = perturb_weights({k: float(v) for k, v in base_weights.items()}, fname, sign)
            scores, _ = compute_scores(records, anchors, cfg, facet_weights=w)
            ranked, _, counts = build_tiers(scores, cfg["tiers"])
            alt_tier = {e["record_id"]: e["tier"] for e in ranked}
            changed = sorted(rid for rid in base_tier if alt_tier[rid] != base_tier[rid])
            runs.append({"run_id": run_id,
                         "perturbed_facet": fname,
                         "factor": sign,
                         "weights": {k: round(v, 6) for k, v in w.items()},
                         "tier_counts": counts,
                         "records_changed_tier": changed})
            for rid in changed:
                instability.setdefault(rid, {"record_id": rid,
                                             "base_tier": base_tier[rid],
                                             "alt_tiers": {}})
                instability[rid]["alt_tiers"][run_id] = alt_tier[rid]

    inst_list = sorted(instability.values(), key=lambda d: d["record_id"])
    for d in inst_list:
        d["n_runs_changed"] = len(d["alt_tiers"])
    dump_json(work / "sensitivity.json", {
        "method": f"每个 facet 权重单独 ±{int(p * 100)}%，其余按比例缩放保持和为 1；"
                  f"共 {len(runs)} 个扰动方案，命中事实不变，仅权重变化",
        "runs": runs,
        "rank_instability": inst_list,
        "interpretation": "rank_instability 中的记录对权重敏感，档位结论不稳，"
                          "建议人工优先核阅这些记录的边界判断；排序仍不构成纳入/排除判定。",
    })
    print(f"[sensitivity] 扰动完成: {len(runs)} 个方案；换档记录数={len(inst_list)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[sensitivity] 未预期异常: {exc!r}")
        sys.exit(3)
