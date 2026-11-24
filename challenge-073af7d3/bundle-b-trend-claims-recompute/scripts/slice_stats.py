#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slice_stats.py -- 年度（或 N 年窗）切片计数 + 泊松 95% CI + 右删失检测。

输入：<work>/canon.jsonl（build_corpus.py 产物，或任何同 schema 文件）。
输出：<work>/slices.json、<work>/slices.csv。

泊松计数 CI 方法（见 references/statistics_notes.md）：
    Garwood 精确区间，卡方分位数用 Wilson-Hilferty 近似（标准库无卡方分位数）：
        lower = 0.5 * chi2_quantile(alpha/2,   2n)      （n=0 时 lower=0）
        upper = 0.5 * chi2_quantile(1-alpha/2, 2(n+1))
        chi2_quantile(p, k) ≈ k * (1 - 2/(9k) + z_p * sqrt(2/(9k)))^3
    z_p 由 statistics.NormalDist().inv_cdf 给出（标准库，确定性）。
    JSON 字段：ci95_lo / ci95_hi，方法标识 ci_method = "garwood-wilson-hilferty"。

右删失规则（censoring 40% 规则）：
    最后一个 bin 计数 < 0.4 * 前 3 个 bin 计数的中位数  →  partial_year_suspect = true。
"""
import argparse
import json
import math
import os
import statistics
import sys

ND = statistics.NormalDist()
ALPHA = 0.05
CI_METHOD = "garwood-wilson-hilferty"
CENSOR_RATIO = 0.4


def chi2_quantile(p, k):
    """Wilson-Hilferty 近似卡方分位数；下尾近 0 处截断为 0。"""
    if k <= 0:
        return 0.0
    z = ND.inv_cdf(p)
    t = 1.0 - 2.0 / (9.0 * k) + z * math.sqrt(2.0 / (9.0 * k))
    if t <= 0.0:
        return 0.0
    return k * t ** 3


def poisson_ci(n, alpha=ALPHA):
    """Garwood 区间（卡方分位数用 WH 近似）。返回 (lo, hi)。"""
    lo = 0.0 if n == 0 else 0.5 * chi2_quantile(alpha / 2.0, 2 * n)
    hi = 0.5 * chi2_quantile(1.0 - alpha / 2.0, 2 * (n + 1))
    return round(lo, 6), round(hi, 6)


def load_canon(work):
    path = os.path.join(work, "canon.jsonl")
    if not os.path.isfile(path):
        sys.exit("ERROR: %s 不存在；请先运行 build_corpus.py" % path)
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    ap = argparse.ArgumentParser(description="年度/窗口切片计数 + 泊松 CI + 删失检测")
    ap.add_argument("--work", required=True)
    ap.add_argument("--window", type=int, default=1,
                    help="窗口年数 N（默认 1 = 年度）。跨度 <8 年时建议 2 或 3。")
    args = ap.parse_args()
    if args.window < 1:
        sys.exit("ERROR: --window 必须 >= 1")

    records = load_canon(args.work)
    years = [r.get("year") for r in records if isinstance(r.get("year"), int)]
    n_missing = len(records) - len(years)
    notes = []
    if n_missing:
        notes.append("missing_year_excluded: %d 条记录无年份，未计入切片（未补零）" % n_missing)

    bins = []
    if years:
        y0, y1 = min(years), max(years)
        counts = {}
        for y in years:
            counts[y] = counts.get(y, 0) + 1
        start = y0
        while start <= y1:
            end = min(start + args.window - 1, y1)
            c = sum(counts.get(y, 0) for y in range(start, end + 1))
            lo, hi = poisson_ci(c)
            label = str(start) if start == end else "%d-%d" % (start, end)
            bins.append({"label": label, "start": start, "end": end,
                         "count": c, "ci95_lo": lo, "ci95_hi": hi})
            start = end + 1
    else:
        notes.append("empty: 没有任何带年份的记录")

    # 右删失检测
    partial, censoring = False, None
    if len(bins) >= 4:
        prev3 = [b["count"] for b in bins[-4:-1]]
        med = statistics.median(prev3)
        threshold = round(CENSOR_RATIO * med, 6)
        last = bins[-1]
        partial = last["count"] < threshold
        censoring = {"final_label": last["label"], "final_count": last["count"],
                     "median_prev3": med, "threshold": threshold,
                     "rule": "final_count < %.2f * median(prev 3 bins)" % CENSOR_RATIO}
        if partial:
            notes.append("partial_year_suspect: 末段 %s 计数 %d < 阈值 %s，"
                         "疑似右删失（数据截取），禁止单独据此主张衰退"
                         % (last["label"], last["count"], threshold))
    elif bins:
        notes.append("too_few_bins_for_censoring_check: bin 数 <4，跳过删失检测")

    out = {
        "mode": "annual" if args.window == 1 else "window",
        "window": args.window,
        "ci_method": CI_METHOD,
        "ci_level": 0.95,
        "n_records": len(records),
        "n_missing_year": n_missing,
        "bins": bins,
        "partial_year_suspect": partial,
        "censoring": censoring,
        "notes": notes,
    }
    with open(os.path.join(args.work, "slices.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with open(os.path.join(args.work, "slices.csv"), "w", encoding="utf-8") as f:
        f.write("label,start,end,count,ci95_lo,ci95_hi\n")
        for b in bins:
            f.write("%s,%d,%d,%d,%s,%s\n" % (b["label"], b["start"], b["end"],
                                             b["count"], b["ci95_lo"], b["ci95_hi"]))
    print("slice_stats: %d bins (%s mode), partial_year_suspect=%s -> slices.json/csv"
          % (len(bins), out["mode"], partial))


if __name__ == "__main__":
    main()
