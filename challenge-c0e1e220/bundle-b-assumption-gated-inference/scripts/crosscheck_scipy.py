#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crosscheck_scipy — 用 scipy 交叉校验 statcore_b（可选增强脚本）。

scipy 不在场时打印 SKIP 并 exit 0（优雅降级，不影响主流程）。
在场时校验 t/F/χ²/正态 CDF 网格与 t/Welch/ANOVA/KW/Levene/K²/Mann-Whitney
在多组随机数据上的统计量与 p，全部差异 < 1e-6 才 exit 0。
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_b as sb

try:
    import scipy.stats as ss
except ImportError:
    print("SKIP: scipy 不可用，交叉校验跳过（statcore_b 仍可独立运行）")
    sys.exit(0)

MAX = 0.0
FAIL = []


def chk(name, a, b):
    global MAX
    d = abs(a - b)
    MAX = max(MAX, d)
    if d > 1e-6:
        FAIL.append((name, a, b, d))


rng = random.Random(20240501)

# 分布函数网格
for t in [x / 5.0 for x in range(-30, 31)]:
    for v in (1, 2, 5, 10, 30, 100, 500):
        chk("t_cdf", sb.t_cdf(t, v), ss.t.cdf(t, v))
        chk("t_ppf", sb.t_ppf(ss.t.cdf(t, v), v), t)
for f in [0.01 + 0.1 * i for i in range(80)]:
    chk("f_cdf", sb.f_cdf(f, 2, 47), ss.f.cdf(f, 2, 47))
    chk("f_cdf", sb.f_cdf(f, 7, 13), ss.f.cdf(f, 7, 13))
for x in [0.01 + 0.5 * i for i in range(80)]:
    chk("chi2_cdf", sb.chi2_cdf(x, 2), ss.chi2.cdf(x, 2))
    chk("chi2_cdf", sb.chi2_cdf(x, 13), ss.chi2.cdf(x, 13))
for p in [1e-6 + i * (1 - 2e-6) / 60 for i in range(61)]:
    chk("norm_ppf", sb.norm_ppf(p), ss.norm.ppf(p))

# 检验（含 ties 数据）
datasets = []
for _ in range(8):
    n1, n2 = rng.choice([(12, 12), (8, 25), (50, 60), (30, 30)])
    datasets.append(([rng.gauss(0, 1) for _ in range(n1)],
                     [rng.gauss(0.4, 1.3) for _ in range(n2)]))
datasets.append(([1, 1, 2, 3, 3, 3, 4, 5], [2, 2, 3, 4, 4, 5, 5, 6]))
for x, y in datasets:
    a, b = sb.t_student(x, y), ss.ttest_ind(x, y, equal_var=True)
    chk("student_t", a["statistic"], b.statistic); chk("student_p", a["p"], b.pvalue)
    a, b = sb.t_welch(x, y), ss.ttest_ind(x, y, equal_var=False)
    chk("welch_t", a["statistic"], b.statistic); chk("welch_df", a["df"], b.df)
    chk("welch_p", a["p"], b.pvalue)
    a = sb.mannwhitney(x, y)
    b = ss.mannwhitneyu(x, y, method="asymptotic", use_continuity=False)
    chk("mw_p", a["p"], b.pvalue)
    k2 = sb.dagostino_k2(x)
    if k2[0] is not None:
        nt = ss.normaltest(x)
        chk("k2_stat", k2[0], nt.statistic); chk("k2_p", k2[1], nt.pvalue)

for _ in range(6):
    g = [[rng.gauss(0.3 * i, 1 + 0.4 * i) for _ in range(rng.choice([15, 25, 40]))]
         for i in range(3)]
    a, b = sb.anova_classic(g), ss.f_oneway(*g)
    chk("anova_F", a["statistic"], b.statistic); chk("anova_p", a["p"], b.pvalue)
    a, b = sb.kruskal(g), ss.kruskal(*g)
    chk("kw_H", a["statistic"], b.statistic); chk("kw_p", a["p"], b.pvalue)
    a, b = sb.levene_median(g), ss.levene(*g, center="median")
    chk("levene_W", a[0], b.statistic); chk("levene_p", a[3], b.pvalue)
g = [[1, 1, 2, 3], [2, 2, 2, 4, 5], [1, 3, 3, 3, 6]]
chk("kw_ties", sb.kruskal(g)["statistic"], ss.kruskal(*g).statistic)
chk("kw_ties_p", sb.kruskal(g)["p"], ss.kruskal(*g).pvalue)

# Holm 与 statsmodels 口径手算对照
chk("holm", sb.holm([0.01, 0.04, 0.03])[0], 0.03)
chk("holm", sb.holm([0.01, 0.04, 0.03])[1], 0.06)
chk("holm", sb.holm([0.01, 0.04, 0.03])[2], 0.06)

print("scipy %s 交叉校验：最大偏差 = %.3e" % (ss.__version__ if hasattr(ss, "__version__") else "?", MAX))
if FAIL:
    print("FAIL %d 项：" % len(FAIL))
    for f in FAIL[:10]:
        print("  ", f)
    sys.exit(1)
print("PASS: 全部差异 < 1e-6")
sys.exit(0)
