#!/usr/bin/env python3
"""score_records.py — 确定性强评分 + 完整分数分解单。

总分公式（全部参数见 config/scoring_config.json，推导见 references/scoring_model.md）：

  total = coverage_points * Σ_f [ w_f * hit_frac(f, r) ]
        + recency_points(r)
        + type_points * type_weight(publication_type(r))
        - diversity_penalty(r)

  hit_frac(f, r) = facet f 中在记录 r 的题名/摘要里锚定命中的不同词数 / f 的词总数

特点：
  - 无任何随机数、无时间戳、无 embedding/ML：同输入必得同分（幂等、可复算）；
  - 每条记录输出完整分解：哪个 facet 哪个词在哪个字段命中、权重多少、贡献多少分；
  - 分数舍入到 config.rounding_decimals 位，杜绝伪精度。

本模块同时暴露 compute_scores()，供 sensitivity.py 以扰动权重复用同一实现。

退出码：0 正常；3 输入缺失/未预期异常。
"""
import argparse
import sys
from pathlib import Path

from common_lib import (default_config_path, dump_json, eprint, load_config,
                        load_json, norm_text, round_score)


def hit_fractions(anchors):
    """从 anchors.json 得到 {facet: {record_id: (命中词数, 词总数, [命中词])}}。"""
    fr = {}
    for fname, fnode in anchors["facets"].items():
        terms = fnode["terms"]
        per_rec = {}
        for term, tnode in terms.items():
            for rid in tnode["hits_by_record"]:
                per_rec.setdefault(rid, set()).add(term)
        fr[fname] = (len(terms), per_rec)
    return fr


def recency_points(year, ref_year, cfg):
    """时效分：ref_year（语料内最大年份）前 window 年内满分，之后线性衰减至 0。"""
    rp = float(cfg["recency_points"])
    if year is None:
        return rp * float(cfg.get("unknown_year_factor", 0.5)), "unknown_year"
    if ref_year is None:
        return 0.0, "no_reference_year"
    window = int(cfg["recency_window_years"])
    span = int(cfg.get("recency_decay_span_years", window))
    age = ref_year - int(year)
    if age <= 0:
        return rp, "current"
    if age <= window:
        return rp, "within_window"
    if age >= window + span:
        return 0.0, "outdated"
    return rp * (window + span - age) / span, "decay"


def diversity_key(rec, cfg):
    """来源多样性键：优先规范化期刊名，缺省回退到第一作者姓氏。"""
    for key in cfg["diversity"].get("key_priority", ["journal", "first_author"]):
        if key == "journal" and norm_text(rec.get("journal")):
            return "journal:" + norm_text(rec["journal"])
        if key == "first_author" and rec.get("authors"):
            first = str(rec["authors"][0])
            surname = first.split()[0] if first.split() else first
            if norm_text(surname):
                return "first_author:" + norm_text(surname)
    return "unknown:" + rec["record_id"]


def compute_scores(records, anchors, cfg, facet_weights=None):
    """核心评分：返回 (scores 列表, meta)。sensitivity.py 以扰动 facet_weights 调用。

    scores 元素含完整 decomposition，任何人可按 references/scoring_model.md 复算。
    """
    weights = dict(facet_weights or cfg["facet_weights"])
    w_total = sum(weights.values())
    # 调用方应保证权重和为 1；这里做一次归一化兜底，使扰动实现也安全
    weights = {k: v / w_total for k, v in weights.items()}

    fr = hit_fractions(anchors)
    years = [r["year"] for r in records if r.get("year") is not None]
    ref_year = max(years) if years else None

    # 来源多样性：同一键在语料中出现 n 次，每条记录罚 penalty_per_extra*(n-1)，封顶
    key_count = {}
    for r in records:
        k = diversity_key(r, cfg)
        key_count[k] = key_count.get(k, 0) + 1
    per_extra = float(cfg["diversity"]["penalty_per_extra"])
    max_pen = float(cfg["diversity"]["max_penalty"])

    type_weights = {norm_text(k): float(v) for k, v in cfg["type_weights"].items()}
    dec = int(cfg.get("rounding_decimals", 4))
    cov_pts = float(cfg["coverage_points"])
    type_pts = float(cfg["type_points"])

    scores = []
    for r in records:
        rid = r["record_id"]
        facet_rows, cov_sum = [], 0.0
        for fname in cfg["facet_weights"]:  # 固定 facet 顺序，保证输出稳定
            terms_total, per_rec = fr[fname]
            hit_terms = sorted(per_rec.get(rid, set()))
            frac = (len(hit_terms) / terms_total) if terms_total else 0.0
            w = weights[fname]
            contribution = round_score(cov_pts * w * frac, dec)
            cov_sum += cov_pts * w * frac
            # 命中明细：词 → 命中位置与片段（来自锚定，非评分脚本生成）
            hit_detail = []
            for term in hit_terms:
                for hit in anchors["facets"][fname]["terms"][term]["hits_by_record"][rid]:
                    hit_detail.append({"term": term, **hit})
            facet_rows.append({
                "facet": fname,
                "weight": round_score(w, dec),
                "terms_total": terms_total,
                "terms_hit": len(hit_terms),
                "hit_fraction": round_score(frac, dec),
                "contribution": contribution,
                "hits": hit_detail,
            })

        rec_pts, rec_note = recency_points(r.get("year"), ref_year, cfg)
        ptype_norm = norm_text(r.get("publication_type")) or "unknown"
        tweight = type_weights.get(ptype_norm, type_weights.get("unknown", 0.0))
        dkey = diversity_key(r, cfg)
        same = key_count[dkey]
        penalty = min(max_pen, per_extra * (same - 1))

        total = round_score(cov_sum + rec_pts + type_pts * tweight - penalty, dec)
        scores.append({
            "record_id": rid,
            "title": r.get("title"),
            "year": r.get("year"),
            "publication_type": r.get("publication_type"),
            "total_score": total,
            "decomposition": {
                "coverage": {"points_cap": cov_pts,
                             "subtotal": round_score(cov_sum, dec),
                             "facets": facet_rows},
                "recency": {"year": r.get("year"), "reference_year": ref_year,
                            "rule": rec_note, "points": round_score(rec_pts, dec)},
                "publication_type": {"raw": r.get("publication_type"),
                                     "matched_weight": tweight,
                                     "points": round_score(type_pts * tweight, dec)},
                "diversity": {"key": dkey, "same_key_records": same,
                              "penalty": round_score(penalty, dec)},
                "formula": "total = coverage.subtotal + recency.points + "
                           "publication_type.points - diversity.penalty",
            },
        })

    # 排序确定性：先按总分降序，再按 record_id 字典序（机器可复算的最终次序）
    scores.sort(key=lambda s: (-s["total_score"], s["record_id"]))
    for i, s in enumerate(scores, 1):
        s["sort_order"] = i
    meta = {"reference_year": ref_year, "facet_weights_used": weights,
            "rounding_decimals": dec}
    return scores, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="确定性强评分与分数分解")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    work = Path(args.work)
    cfg = load_config(args.config)
    records = load_json(work / "records.json")
    anchors = load_json(work / "anchors.json")
    if anchors.get("anchor_failures"):
        eprint("[score_records] anchors.json 含 anchor_failures，请先重修 facet 词表")
        return 3

    scores, meta = compute_scores(records, anchors, cfg)
    dump_json(work / "scores.json", {"meta": meta, "scores": scores})
    print(f"[score_records] 评分完成: {len(scores)} 条；最高分 "
          f"{scores[0]['record_id']}={scores[0]['total_score']}，"
          f"最低分 {scores[-1]['record_id']}={scores[-1]['total_score']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[score_records] 未预期异常: {exc!r}")
        sys.exit(3)
