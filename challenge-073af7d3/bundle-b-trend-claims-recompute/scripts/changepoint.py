#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""changepoint.py -- 泊松两段模型变点扫描 + 单年波动检测。

输入：<work>/slices.json（slice_stats.py 产物）。若 partial_year_suspect=true，
最后一个 bin 被排除出变点/波动分析（右删失年份不得参与速率估计），并写入 warnings。

变点模型：对每个候选变点 τ（= 第二段首个 bin），拟合
    seg1 = bins[<τ]  速率 λ1 = S1/T1，seg2 = bins[>=τ] 速率 λ2 = S2/T2（MLE 闭式解）
对数似然增益 ll_gain = LL(两段) - LL(单一速率)（-Σln x! 项在比较中消去）。
rate_ratio = λ2/λ1，95% CI 在 log 尺度（delta 法）：
    log(rr) ± 1.96 * SE，SE = sqrt(1/S1 + 1/S2)，S1/S2 为两段的事件总数。
    （公式与局限见 references/statistics_notes.md）
supported = CI 整体在 1 的某一侧（ci95_lo > 1 或 ci95_hi < 1）。
采纳规则：只有 supported 的候选才可写入报告的“显著变点”；
adopted_tau = supported 候选中 ll_gain 最大者（无则 null）。

波动检测：z = (x - MA) / sqrt(MA)，MA = 前 3 个 bin 计数的均值；
|z| >= 2 列为 fluctuation candidates（单年噪声候选，不是拐点证据）。

输出：<work>/changepoints.json。
"""
import argparse
import json
import math
import os
import sys

Z_CRIT = 1.959963984540054  # NormalDist().inv_cdf(0.975)，写死以保证确定性
FLUCT_Z = 2.0
MIN_SPAN = 8


def seg_ll(s, t):
    """泊松段对数似然（省去与模型无关的 -Σln x! 常数）。s=事件总数, t=bin 数。"""
    if s <= 0 or t <= 0:
        return 0.0
    return s * math.log(s / t) - s


def main():
    ap = argparse.ArgumentParser(description="泊松两段变点扫描 + 波动检测")
    ap.add_argument("--work", required=True)
    args = ap.parse_args()

    slices_path = os.path.join(args.work, "slices.json")
    if not os.path.isfile(slices_path):
        sys.exit("ERROR: %s 不存在；请先运行 slice_stats.py" % slices_path)
    with open(slices_path, encoding="utf-8") as f:
        slices = json.load(f)

    bins = slices.get("bins", [])
    warnings, excluded = [], []
    if slices.get("partial_year_suspect") and bins:
        excluded.append(bins[-1]["label"])
        bins = bins[:-1]
        warnings.append("censored_bin_excluded: 末段 %s 疑似右删失，已排除出变点/波动分析"
                        % excluded[0])
    if slices.get("mode") != "annual":
        warnings.append("window_mode: 输入为 %d 年窗切片，τ 以窗口首年报告，时间分辨率降低"
                        % slices.get("window", 0))
    if len(bins) < MIN_SPAN:
        warnings.append("span_lt_%d: 有效跨度仅 %d 个 bin，所有变点结论仅供探索，"
                        "不得写为确定结论" % (MIN_SPAN, len(bins)))

    counts = [b["count"] for b in bins]
    total_s, total_t = sum(counts), len(counts)
    single_ll = seg_ll(total_s, total_t)

    candidates = []
    if total_t >= 2:
        for i in range(1, total_t):
            s1, t1 = sum(counts[:i]), i
            s2, t2 = total_s - s1, total_t - i
            if s1 == 0 or s2 == 0:
                warnings.append("candidate_skipped_zero_count: τ=%s 某段事件数为 0，"
                                "rate ratio 无法估计，跳过" % bins[i]["label"])
                continue
            lam1, lam2 = s1 / t1, s2 / t2
            gain = seg_ll(s1, t1) + seg_ll(s2, t2) - single_ll
            rr = lam2 / lam1
            se = math.sqrt(1.0 / s1 + 1.0 / s2)
            lo = math.exp(math.log(rr) - Z_CRIT * se)
            hi = math.exp(math.log(rr) + Z_CRIT * se)
            candidates.append({
                "tau": bins[i]["start"],
                "tau_label": bins[i]["label"],
                "seg1": "%s..%s" % (bins[0]["label"], bins[i - 1]["label"]),
                "seg2": "%s..%s" % (bins[i]["label"], bins[-1]["label"]),
                "lambda1": round(lam1, 6),
                "lambda2": round(lam2, 6),
                "rate_ratio": round(rr, 6),
                "ci95_lo": round(lo, 6),
                "ci95_hi": round(hi, 6),
                "ll_gain": round(gain, 6),
                "supported": bool(lo > 1.0 or hi < 1.0),
            })
    candidates.sort(key=lambda c: (-c["ll_gain"], c["tau"]))
    for rank, c in enumerate(candidates, 1):
        c["rank"] = rank
    supported = [c for c in candidates if c["supported"]]
    adopted = supported[0]["tau"] if supported else None
    if not supported:
        warnings.append("no_supported_changepoint: 没有任何候选的 rate-ratio CI 排除 1；"
                        "报告中不得出现“显著变点”字样")

    fluctuations = []
    for i in range(3, len(bins)):
        ma = sum(counts[i - 3:i]) / 3.0
        if ma <= 0:
            continue
        x = counts[i]
        z = (x - ma) / math.sqrt(ma)
        if abs(z) >= FLUCT_Z:
            fluctuations.append({
                "year": bins[i]["start"],
                "label": bins[i]["label"],
                "count": x,
                "ma_baseline": round(ma, 6),
                "z": round(z, 6),
                "direction": "up" if z > 0 else "down",
            })

    out = {
        "model": "poisson_two_segment_mle",
        "rate_ratio_ci": "log-scale, SE = sqrt(1/S1 + 1/S2)",
        "fluctuation_rule": "z = (x - MA3_prev)/sqrt(MA3_prev), |z| >= 2",
        "n_bins_used": total_t,
        "excluded_bins": excluded,
        "single_rate_ll": round(single_ll, 6),
        "adopted_tau": adopted,
        "candidates": candidates,
        "fluctuations": fluctuations,
        "warnings": warnings,
    }
    with open(os.path.join(args.work, "changepoints.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("changepoint: %d candidates, adopted_tau=%s, %d fluctuations, %d warnings"
          % (len(candidates), adopted, len(fluctuations), len(warnings)))


if __name__ == "__main__":
    main()
