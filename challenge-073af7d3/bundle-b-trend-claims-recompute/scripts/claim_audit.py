#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_audit.py -- 趋势主张 vs 重算统计的审计器（本 bundle 的差异点）。

输入：<work>/slices.json、<work>/changepoints.json、--claims FILE。
claims schema（详见 references/claims_schema.md）：JSON 列表，元素为
    {claim_id, kind: trend|changepoint|fluctuation|decline,
     year 或 year_range: [a,b], direction: up|down|stable,
     significance: claimed|not_claimed, statement}

审计规则（每条主张独立重算，违反即判 violation）：
 (a) decline/trend-down 主张落在 partial_year_suspect 年份
     -> VIOLATION censored_year_as_decline（右删失当年不可作衰退证据）
 (b) changepoint 主张的 τ 不在 supported 候选（rate-ratio CI 排除 1）中
     -> significance=claimed 时 VIOLATION unsupported_changepoint，否则 DOWNGRADE
 (c) changepoint 主张的 τ 是单年波动年且无 supported 候选支持
     -> VIOLATION fluctuation_as_inflection（把泊松噪声当拐点）
 (d) trend 方向主张与重算计数矛盾且统计上有区分度（半数分段 rate-ratio CI
     排除 1）-> VIOLATION direction_mismatch；矛盾但 CI 跨 1 -> DOWNGRADE
 (e) 完全一致 -> OK，并在 evidence 中回显支撑数字。

输出：<work>/claim_audit.json；任一 violation 时退出码 1，否则 0。
"""
import argparse
import json
import math
import os
import sys

Z_CRIT = 1.959963984540054  # NormalDist().inv_cdf(0.975)
MIN_BINS_TREND = 4


def log_rate_ratio_ci(s1, t1, s2, t2):
    """两段泊松速率比的 log 尺度 95% CI。返回 (rr, lo, hi)，s1/s2 为 0 时返回 None。"""
    if s1 <= 0 or s2 <= 0 or t1 <= 0 or t2 <= 0:
        return None
    rr = (s2 / t2) / (s1 / t1)
    se = math.sqrt(1.0 / s1 + 1.0 / s2)
    return (round(rr, 6),
            round(math.exp(math.log(rr) - Z_CRIT * se), 6),
            round(math.exp(math.log(rr) + Z_CRIT * se), 6))


def bin_of_year(bins, year):
    for b in bins:
        if b["start"] <= year <= b["end"]:
            return b
    return None


def audit_trend(claim, bins, slices, fluct_years):
    """trend/decline 主张：半数分段 rate-ratio 重算。返回 (verdict, violations, evidence)。"""
    direction = claim.get("direction", "up")
    yr = claim.get("year_range")
    year = claim.get("year")
    final_bin = bins[-1] if bins else None
    partial = bool(slices.get("partial_year_suspect"))

    # 规则 (a)：右删失年份作衰退证据
    if partial and final_bin is not None and direction == "down":
        hits_censored = False
        if yr and len(yr) == 2 and yr[1] >= final_bin["start"]:
            hits_censored = True
        if year is not None and bin_of_year([final_bin], year):
            hits_censored = True
        if hits_censored:
            return "violation", ["censored_year_as_decline"], {
                "censored_bin": final_bin["label"],
                "final_count": final_bin["count"],
                "censoring": slices.get("censoring"),
                "note": "末段计数疑似右删失（数据截取不全），不能作为衰退证据",
            }

    # 选定分析区间（剔除删失末段，注明）
    sel = list(bins)
    trimmed = None
    if yr and len(yr) == 2:
        sel = [b for b in bins if b["start"] >= yr[0] and b["end"] <= yr[1]]
    if partial and sel and sel[-1] is final_bin:
        trimmed = sel[-1]["label"]
        sel = sel[:-1]
    if len(sel) < MIN_BINS_TREND:
        return "downgraded", [], {
            "note": "可用 bin 数 %d < %d，趋势主张统计功效不足，降级" % (len(sel), MIN_BINS_TREND),
            "trimmed_censored_bin": trimmed,
        }

    # 半数分段：奇数个 bin 时中间 bin 归入后半段
    h = len(sel) // 2
    g1, g2 = sel[:h], sel[h:]
    s1, t1 = sum(b["count"] for b in g1), len(g1)
    s2, t2 = sum(b["count"] for b in g2), len(g2)
    est = log_rate_ratio_ci(s1, t1, s2, t2)
    evidence = {
        "first_half": {"range": "%s..%s" % (g1[0]["label"], g1[-1]["label"]),
                       "total": s1, "bins": t1, "rate": round(s1 / t1, 6)},
        "second_half": {"range": "%s..%s" % (g2[0]["label"], g2[-1]["label"]),
                        "total": s2, "bins": t2, "rate": round(s2 / t2, 6)},
        "trimmed_censored_bin": trimmed,
    }
    if est is None:
        evidence["note"] = "某半段事件数为 0，无法估计速率比，降级"
        return "downgraded", [], evidence
    rr, lo, hi = est
    evidence.update({"rate_ratio_second_over_first": rr, "ci95": [lo, hi]})

    if direction == "stable":
        if lo > 1.0 or hi < 1.0:
            return "violation", ["direction_mismatch"], dict(
                evidence, note="主张 stable 但重算显示统计上有方向性变化")
        return "ok", [], evidence
    if direction == "up":
        if lo > 1.0:
            return "ok", [], evidence
        if hi < 1.0:
            return "violation", ["direction_mismatch"], dict(
                evidence, note="主张 up 但重算为统计显著的下降")
        return "downgraded", [], dict(
            evidence, note="主张 up 与点估计方向不符或 CI 跨 1，统计功效不足，降级")
    # direction == "down"
    if hi < 1.0:
        return "ok", [], evidence
    if lo > 1.0:
        return "violation", ["direction_mismatch"], dict(
            evidence, note="主张 down 但重算为统计显著的上升")
    return "downgraded", [], dict(
        evidence, note="主张 down 与点估计方向不符或 CI 跨 1，统计功效不足，降级")


def audit_changepoint(claim, candidates_by_tau, fluct_years):
    year = claim.get("year")
    direction = claim.get("direction", "up")
    significance = claim.get("significance", "claimed")
    cand = candidates_by_tau.get(year)
    supported = False
    if cand:
        if direction == "up" and cand["ci95_lo"] > 1.0:
            supported = True
        elif direction == "down" and cand["ci95_hi"] < 1.0:
            supported = True
    if supported:
        return "ok", [], {
            "tau": cand["tau"], "lambda1": cand["lambda1"], "lambda2": cand["lambda2"],
            "rate_ratio": cand["rate_ratio"],
            "ci95": [cand["ci95_lo"], cand["ci95_hi"]],
            "ll_gain": cand["ll_gain"], "rank": cand["rank"],
        }
    evidence = {"tau": year, "matched_candidate": cand,
                "in_fluctuation_years": year in fluct_years}
    if year in fluct_years:
        return "violation", ["fluctuation_as_inflection"], dict(
            evidence, note="该年是 |z|>=2 的单年波动年，且无 supported 变点候选；"
                           "单年尖峰是泊松噪声候选，不得当作真实拐点")
    if significance == "claimed":
        return "violation", ["unsupported_changepoint"], dict(
            evidence, note="主张显著变点，但该 τ 的 rate-ratio CI 未排除 1（或不在候选中）")
    return "downgraded", [], dict(
        evidence, note="未主张显著性；但该 τ 亦无 CI 排除 1 的支持，降级为探索性表述")


def audit_fluctuation(claim, fluctuations_by_year):
    year = claim.get("year")
    f = fluctuations_by_year.get(year)
    if f:
        return "ok", [], {"year": year, "count": f["count"],
                          "ma_baseline": f["ma_baseline"], "z": f["z"],
                          "note": "与重算的波动清单一致"}
    return "downgraded", [], {
        "year": year,
        "note": "该年不在重算波动清单（|z|>=2）中；若报告保留此表述须降级为定性描述"}


def main():
    ap = argparse.ArgumentParser(description="趋势主张审计：主张 vs 重算统计")
    ap.add_argument("--work", required=True)
    ap.add_argument("--claims", required=True, help="claims JSON 文件路径")
    args = ap.parse_args()

    slices_path = os.path.join(args.work, "slices.json")
    cp_path = os.path.join(args.work, "changepoints.json")
    for p in (slices_path, cp_path):
        if not os.path.isfile(p):
            sys.exit("ERROR: %s 不存在；请先运行 slice_stats.py 与 changepoint.py" % p)
    with open(slices_path, encoding="utf-8") as f:
        slices = json.load(f)
    with open(cp_path, encoding="utf-8") as f:
        cps = json.load(f)
    with open(args.claims, encoding="utf-8") as f:
        claims = json.load(f)
    if not isinstance(claims, list):
        sys.exit("ERROR: claims 文件必须是 JSON 列表")

    bins = slices.get("bins", [])
    candidates_by_tau = {c["tau"]: c for c in cps.get("candidates", [])}
    fluctuations = cps.get("fluctuations", [])
    fluctuations_by_year = {f["year"]: f for f in fluctuations}
    fluct_years = set(fluctuations_by_year)

    verdicts = []
    n_viol = n_ok = n_down = 0
    for claim in claims:
        cid = claim.get("claim_id", "?")
        kind = claim.get("kind", "")
        if kind in ("trend", "decline"):
            verdict, violations, evidence = audit_trend(claim, bins, slices, fluct_years)
        elif kind == "changepoint":
            verdict, violations, evidence = audit_changepoint(
                claim, candidates_by_tau, fluct_years)
        elif kind == "fluctuation":
            verdict, violations, evidence = audit_fluctuation(claim, fluctuations_by_year)
        else:
            verdict, violations, evidence = "downgraded", [], {
                "note": "未知 kind=%r，无法审计，降级" % kind}
        verdicts.append({"claim_id": cid, "kind": kind,
                         "statement": claim.get("statement", ""),
                         "verdict": verdict, "violations": violations,
                         "evidence": evidence})
        if verdict == "violation":
            n_viol += 1
        elif verdict == "ok":
            n_ok += 1
        else:
            n_down += 1

    out = {
        "claims_file": os.path.basename(args.claims),
        "n_claims": len(claims),
        "summary": {"ok": n_ok, "violation": n_viol, "downgraded": n_down},
        "verdicts": verdicts,
    }
    with open(os.path.join(args.work, "claim_audit.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("claim_audit: %d claims -> ok=%d violation=%d downgraded=%d"
          % (len(claims), n_ok, n_viol, n_down))
    for v in verdicts:
        if v["verdict"] == "violation":
            print("VIOLATION %s: %s (%s)"
                  % (v["claim_id"], ",".join(v["violations"]), v["statement"]))
    sys.exit(1 if n_viol else 0)


if __name__ == "__main__":
    main()
