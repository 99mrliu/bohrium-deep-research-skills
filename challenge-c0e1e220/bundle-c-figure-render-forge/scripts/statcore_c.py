#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statcore_c.py — bundle C (figure-render-forge) 独立 stdlib 统计核心。

零第三方依赖（仅 math / random）。覆盖 SPEC 共同统计范围：
- 分布函数：正则化不完全 beta/gamma → t / F / chi2 / 正态 CDF 与逆函数
- 描述统计：n / 均值 / SD / 中位数 / Q1 / Q3 / min / max / 偏度
- 假设检验：D'Agostino K²（n>=8）、Levene（median 中心）、
  Student t / Welch t / Mann-Whitney U（tie 校正 + 连续性校正）、
  单因素 ANOVA / Welch ANOVA / Kruskal-Wallis（tie 校正）
- 效应量与区间：Hedges g（bootstrap B=2000, percentile CI）、
  均值差 Welch CI、Hodges-Lehmann 中位数差（bootstrap CI）、
  eta² / omega² / epsilon²、Holm 多重比较校正
- 作图辅助：五数概括 + Tukey 1.5*IQR 相邻值须、ECDF 点列、OLS 参考线

所有随机性经 random.Random(seed) 显式固定，跨平台确定性复现。
数值方法对照 scipy 1.18 交叉校验（见 examples/run_example.sh 与开发记录）。
"""
from __future__ import annotations

import math
import random

SEED = 20240501          # 全局默认种子（SPEC 指定）
BOOT_B = 2000            # Hedges g bootstrap 次数
HL_BOOT_B = 1000         # Hodges-Lehmann bootstrap 次数（代价更高）
HL_MAX_CELLS = 30000     # n1*n2 超过则跳过 HL bootstrap CI

_EPS = 3.0e-14
_FPMIN = 1.0e-300
_MAXIT = 300


# ---------------------------------------------------------------- 分布函数

def _betacf(a, b, x):
    """不完全 beta 的连分式（Numerical Recipes betacf）。"""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            break
    return h


def reg_beta(a, b, x):
    """正则化不完全 beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)  # = -ln B(a,b)
    bt = math.exp(a * math.log(x) + b * math.log(1.0 - x) + lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _gammaincc_q(a, x):
    """上不完全 gamma Q(a,x) 的连分式（x >= a+1 时直接求上尾，避免 1-P 抵消）。"""
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAXIT + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def reg_gamma_p(a, x):
    """正则化下不完全 gamma P(a,x)。"""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:  # 级数表示
        ap = a
        s = 1.0 / a
        d = s
        for _ in range(_MAXIT):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * _EPS:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    return 1.0 - _gammaincc_q(a, x)


def reg_gamma_q(a, x):
    """正则化上不完全 gamma Q(a,x)（直接求上尾）。"""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - reg_gamma_p(a, x)
    return _gammaincc_q(a, x)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """二分法求标准正态分位数（精度 ~1e-12，足够 p 值与 CI 使用）。"""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def t_cdf(t, v):
    if v <= 0:
        return math.nan
    x = v / (v + t * t)
    ib = reg_beta(v / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t >= 0 else 0.5 * ib


def t_sf(t, v):
    """直接求上尾（避免 1-CDF 在大 |t| 时抵消为 0）。"""
    if v <= 0:
        return math.nan
    ib = reg_beta(v / 2.0, 0.5, v / (v + t * t))
    return 0.5 * ib if t >= 0 else 1.0 - 0.5 * ib


def t_ppf(p, v):
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    lo, hi = -1.0, 1.0
    while t_cdf(hi, v) < p:
        hi *= 2.0
        if hi > 1e12:
            break
    while t_cdf(lo, v) > p:
        lo *= 2.0
        if lo < -1e12:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, v) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def f_cdf(f, d1, d2):
    if f <= 0.0:
        return 0.0
    return reg_beta(d1 / 2.0, d2 / 2.0, (d1 * f) / (d1 * f + d2))


def f_sf(f, d1, d2):
    """直接求上尾：I_{d2/(d1*f+d2)}(d2/2, d1/2)，避免 1-CDF 在大 F 时抵消为 0。"""
    if f <= 0.0:
        return 1.0
    return reg_beta(d2 / 2.0, d1 / 2.0, d2 / (d1 * f + d2))


def chi2_cdf(x, k):
    if x <= 0.0:
        return 0.0
    return reg_gamma_p(k / 2.0, x / 2.0)


def chi2_sf(x, k):
    return reg_gamma_q(k / 2.0, x / 2.0)


# ---------------------------------------------------------------- 基础工具

def mean(xs):
    return math.fsum(xs) / len(xs)


def variance(xs, ddof=1):
    n = len(xs)
    if n <= ddof - 1:
        return math.nan
    m = mean(xs)
    return math.fsum((x - m) ** 2 for x in xs) / (n - ddof)


def sd(xs, ddof=1):
    v = variance(xs, ddof)
    return math.sqrt(v) if v == v else v


def percentile(sorted_xs, q):
    """线性插值分位数（与 numpy 默认 'linear' 一致），sorted_xs 已排序，q∈[0,100]。"""
    n = len(sorted_xs)
    if n == 0:
        return math.nan
    if n == 1:
        return sorted_xs[0]
    h = (n - 1) * q / 100.0
    lo = int(math.floor(h))
    frac = h - lo
    hi = min(lo + 1, n - 1)
    return sorted_xs[lo] + frac * (sorted_xs[hi] - sorted_xs[lo])


def median(xs):
    return percentile(sorted(xs), 50.0)


def central_moment(xs, k, m=None):
    if m is None:
        m = mean(xs)
    return math.fsum((x - m) ** k for x in xs) / len(xs)


def skewness(xs):
    """g1 = m3 / m2^1.5（bias=True，与 scipy.stats.skew 默认一致）。"""
    m2 = central_moment(xs, 2)
    if m2 <= 0:
        return 0.0
    return central_moment(xs, 3) / m2 ** 1.5


def descriptive(xs):
    """SPEC 描述统计口径。"""
    xs = list(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0}
    s = sorted(xs)
    return {
        "n": n,
        "mean": mean(xs),
        "sd": sd(xs) if n > 1 else 0.0,
        "median": percentile(s, 50.0),
        "q1": percentile(s, 25.0),
        "q3": percentile(s, 75.0),
        "min": s[0],
        "max": s[-1],
        "skew": skewness(xs) if n > 2 else 0.0,
    }


def five_number(xs):
    """箱线图几何：Q1/中位/Q3 + Tukey 1.5*IQR 相邻值须（whisker 为界内极值）。"""
    s = sorted(xs)
    q1 = percentile(s, 25.0)
    med = percentile(s, 50.0)
    q3 = percentile(s, 75.0)
    iqr = q3 - q1
    lo_f = q1 - 1.5 * iqr
    hi_f = q3 + 1.5 * iqr
    whisk_lo = min((v for v in s if v >= lo_f), default=s[0])
    whisk_hi = max((v for v in s if v <= hi_f), default=s[-1])
    fliers = [v for v in s if v < whisk_lo or v > whisk_hi]
    return {"q1": q1, "median": med, "q3": q3, "iqr": iqr,
            "whisk_lo": whisk_lo, "whisk_hi": whisk_hi, "fliers": fliers}


def rankdata(xs):
    """平均秩（ties 取均值）。返回 (ranks, tie_counts)。"""
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    tie_counts = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        if j > i:
            tie_counts.append(j - i + 1)
        i = j + 1
    return ranks, tie_counts


# ---------------------------------------------------------------- 正态性 / 方差齐性

def dagostino_k2(xs):
    """D'Agostino-Pearson K² 正态性检验（与 scipy.stats.normaltest 同公式）。

    n<8 返回 None（上游按保守非正态处理）。返回 dict(K2, p, z_skew, z_kurt)。
    """
    n = len(xs)
    if n < 8:
        return None
    m2 = central_moment(xs, 2)
    if m2 <= 0:
        return {"K2": 0.0, "p": 1.0, "z_skew": 0.0, "z_kurt": 0.0, "note": "zero variance"}
    g1 = central_moment(xs, 3) / m2 ** 1.5
    b2 = central_moment(xs, 4) / m2 ** 2  # 非 Fisher 峰度

    # skewtest Z1
    y = g1 * math.sqrt(((n + 1.0) * (n + 3.0)) / (6.0 * (n - 2.0)))
    beta2 = (3.0 * (n * n + 27.0 * n - 70.0) * (n + 1.0) * (n + 3.0)
             / ((n - 2.0) * (n + 5.0) * (n + 7.0) * (n + 9.0)))
    w2 = -1.0 + math.sqrt(2.0 * (beta2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    alpha = math.sqrt(2.0 / (w2 - 1.0))
    if y == 0.0:
        z1 = 0.0
    else:
        ya = y / alpha
        z1 = delta * math.log(ya + math.sqrt(ya * ya + 1.0))

    # kurtosistest Z2
    e = 3.0 * (n - 1.0) / (n + 1.0)
    varb2 = 24.0 * n * (n - 2.0) * (n - 3.0) / ((n + 1.0) ** 2 * (n + 3.0) * (n + 5.0))
    x = (b2 - e) / math.sqrt(varb2)
    sb1 = (6.0 * (n * n - 5.0 * n + 2.0) / ((n + 7.0) * (n + 9.0))
           * math.sqrt(6.0 * (n + 3.0) * (n + 5.0) / (n * (n - 2.0) * (n - 3.0))))
    a = 6.0 + (8.0 / sb1) * (2.0 / sb1 + math.sqrt(1.0 + 4.0 / (sb1 * sb1)))
    term1 = 1.0 - 2.0 / (9.0 * a)
    d0 = 1.0 + x * math.sqrt(2.0 / (a - 4.0))
    if d0 == 0.0:
        return None  # 检验统计量未定义（scipy 同样返回 nan）
    term2 = math.copysign((abs((1.0 - 2.0 / a) / d0)) ** (1.0 / 3.0), d0)
    z2 = (term1 - term2) / math.sqrt(2.0 / (9.0 * a))

    k2 = z1 * z1 + z2 * z2
    p = math.exp(-0.5 * k2)  # chi2_sf(2) 闭式
    return {"K2": k2, "p": p, "z_skew": z1, "z_kurt": z2}


def levene_median(groups):
    """Levene 方差齐性检验（median 中心，Brown-Forsythe）。返回 dict(W, df1, df2, p)。"""
    zs = []
    for g in groups:
        med = median(g)
        zs.append([abs(v - med) for v in g])
    return anova_oneway(zs, stat_name="W")


# ---------------------------------------------------------------- 两组检验

def t_student(x, y):
    n1, n2 = len(x), len(y)
    m1, m2 = mean(x), mean(y)
    v1, v2 = variance(x), variance(y)
    df = n1 + n2 - 2
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / df
    t = (m1 - m2) / math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    p = 2.0 * t_sf(abs(t), df)
    return {"t": t, "df": float(df), "p": p, "mean_diff": m1 - m2}


def t_welch(x, y):
    n1, n2 = len(x), len(y)
    m1, m2 = mean(x), mean(y)
    v1, v2 = variance(x), variance(y)
    se2 = v1 / n1 + v2 / n2
    t = (m1 - m2) / math.sqrt(se2)
    df = se2 * se2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p = 2.0 * t_sf(abs(t), df)
    return {"t": t, "df": df, "p": p, "mean_diff": m1 - m2,
            "se": math.sqrt(se2)}


def welch_ci_mean_diff(x, y, alpha=0.05):
    r = t_welch(x, y)
    tcrit = t_ppf(1.0 - alpha / 2.0, r["df"])
    lo = r["mean_diff"] - tcrit * r["se"]
    hi = r["mean_diff"] + tcrit * r["se"]
    return {"estimate": r["mean_diff"], "lo": lo, "hi": hi,
            "level": 1.0 - alpha, "method": "Welch CI (mean diff)"}


def mann_whitney_u(x, y):
    """Mann-Whitney U，渐近正态 + tie 校正 + 连续性校正（对 scipy method='asymptotic'）。"""
    n1, n2 = len(x), len(y)
    combined = list(x) + list(y)
    ranks, ties = rankdata(combined)
    r1 = math.fsum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1.0) / 2.0
    u2 = n1 * n2 - u1
    n = n1 + n2
    mu = n1 * n2 / 2.0
    tie_term = math.fsum(t ** 3 - t for t in ties)
    varu = n1 * n2 / 12.0 * ((n + 1.0) - tie_term / (n * (n - 1.0)))
    sdu = math.sqrt(varu)
    z = (u1 - mu)
    if z > 0:
        z -= 0.5
    elif z < 0:
        z += 0.5
    z /= sdu
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return {"U1": u1, "U2": u2, "z": z, "p": p, "n_tie_groups": len(ties)}


def hedges_g(x, y):
    n1, n2 = len(x), len(y)
    v1, v2 = variance(x), variance(y)
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if sp == 0:
        return 0.0
    d = (mean(x) - mean(y)) / sp
    j = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    return j * d


def hedges_g_bootstrap_ci(x, y, alpha=0.05, B=BOOT_B, seed=SEED):
    """percentile bootstrap CI（B=2000, seed=20240501）。"""
    rng = random.Random(seed)
    x, y = list(x), list(y)
    boots = []
    for _ in range(B):
        xb = rng.choices(x, k=len(x))
        yb = rng.choices(y, k=len(y))
        if variance(xb) == 0 and variance(yb) == 0:
            continue
        boots.append(hedges_g(xb, yb))
    boots.sort()
    lo = percentile(boots, 100.0 * alpha / 2.0)
    hi = percentile(boots, 100.0 * (1.0 - alpha / 2.0))
    return {"estimate": hedges_g(x, y), "lo": lo, "hi": hi,
            "level": 1.0 - alpha, "method": "Hedges g, bootstrap percentile (B=%d, seed=%d)" % (B, seed),
            "B": len(boots)}


def hodges_lehmann(x, y, alpha=0.05, B=HL_BOOT_B, seed=SEED):
    """两样本位移的 Hodges-Lehmann 估计（全部两两差的中位数）+ bootstrap CI。"""
    x, y = list(x), list(y)
    diffs = sorted(a - b for a in x for b in y)
    est = percentile(diffs, 50.0)
    out = {"estimate": est, "level": 1.0 - alpha,
           "method": "Hodges-Lehmann median of pairwise diffs"}
    if len(diffs) <= HL_MAX_CELLS:
        rng = random.Random(seed + 101)
        boots = []
        for _ in range(B):
            xb = rng.choices(x, k=len(x))
            yb = rng.choices(y, k=len(y))
            bd = sorted(a - b for a in xb for b in yb)
            boots.append(percentile(bd, 50.0))
        boots.sort()
        out["lo"] = percentile(boots, 100.0 * alpha / 2.0)
        out["hi"] = percentile(boots, 100.0 * (1.0 - alpha / 2.0))
        out["method"] += " + bootstrap CI (B=%d)" % B
    else:
        out["lo"] = None
        out["hi"] = None
        out["note"] = "n1*n2=%d > %d，跳过 bootstrap CI" % (len(diffs), HL_MAX_CELLS)
    return out


# ---------------------------------------------------------------- k 组检验

def anova_oneway(groups, stat_name="F"):
    """经典单因素 ANOVA。返回 dict(F/W, df1, df2, p, ss_between, ss_within, ms_within)。"""
    k = len(groups)
    ns = [len(g) for g in groups]
    N = sum(ns)
    means = [mean(g) for g in groups]
    grand = math.fsum(ns[i] * means[i] for i in range(k)) / N
    ss_b = math.fsum(ns[i] * (means[i] - grand) ** 2 for i in range(k))
    ss_w = math.fsum(math.fsum((v - means[i]) ** 2 for v in groups[i]) for i in range(k))
    df1 = k - 1
    df2 = N - k
    ms_b = ss_b / df1
    ms_w = ss_w / df2
    f = ms_b / ms_w if ms_w > 0 else math.inf
    p = f_sf(f, df1, df2)
    return {stat_name: f, "df1": float(df1), "df2": float(df2), "p": p,
            "ss_between": ss_b, "ss_within": ss_w, "ms_within": ms_w,
            "ss_total": ss_b + ss_w}


def welch_anova(groups):
    """Welch (1951) 异方差 ANOVA。k=2 时 F == Welch t²。"""
    k = len(groups)
    ns = [len(g) for g in groups]
    means = [mean(g) for g in groups]
    vs = [variance(g) for g in groups]
    ws = [ns[i] / vs[i] for i in range(k)]
    sw = math.fsum(ws)
    xw = math.fsum(ws[i] * means[i] for i in range(k)) / sw
    a = math.fsum(ws[i] * (means[i] - xw) ** 2 for i in range(k)) / (k - 1.0)
    c = math.fsum((1.0 - ws[i] / sw) ** 2 / (ns[i] - 1.0) for i in range(k))
    f = a / (1.0 + (2.0 * (k - 2.0) / (k * k - 1.0)) * c)
    df1 = float(k - 1)
    df2 = (k * k - 1.0) / (3.0 * c)
    return {"F": f, "df1": df1, "df2": df2, "p": f_sf(f, df1, df2)}


def kruskal_wallis(groups):
    """Kruskal-Wallis H + tie 校正。"""
    k = len(groups)
    ns = [len(g) for g in groups]
    N = sum(ns)
    combined = [v for g in groups for v in g]
    ranks, ties = rankdata(combined)
    h = 0.0
    pos = 0
    for i in range(k):
        ri = math.fsum(ranks[pos:pos + ns[i]])
        h += ri * ri / ns[i]
        pos += ns[i]
    h = 12.0 / (N * (N + 1.0)) * h - 3.0 * (N + 1.0)
    tie_term = math.fsum(t ** 3 - t for t in ties)
    corr = 1.0 - tie_term / (N ** 3 - N)
    if corr > 0:
        h /= corr
    df = float(k - 1)
    return {"H": h, "df": df, "p": chi2_sf(h, df), "tie_correction": corr}


# ---------------------------------------------------------------- 效应量（k 组）

def eta_squared(anova_res):
    return anova_res["ss_between"] / anova_res["ss_total"]


def omega_squared(anova_res, k):
    return ((anova_res["ss_between"] - (k - 1) * anova_res["ms_within"])
            / (anova_res["ss_total"] + anova_res["ms_within"]))


def epsilon_squared_kw(h, n, k):
    return (h - k + 1.0) / (n - k)


# ---------------------------------------------------------------- 多重比较

def holm_adjust(pvals):
    """Holm 校正，保持输入顺序返回校正后 p。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        val = min((m - rank) * pvals[idx], 1.0)
        running = max(running, val)
        adj[idx] = running
    return adj


# ---------------------------------------------------------------- 作图辅助

def ecdf_points(xs):
    """ECDF 阶梯点列 [(x, F)]，含 (min,0) 起点，供 SVG polyline 使用。"""
    s = sorted(xs)
    n = len(s)
    pts = []
    for i, v in enumerate(s):
        f = (i + 1) / n
        if pts and pts[-1][0] == v:
            pts[-1] = (v, f)
        else:
            pts.append((v, f))
    return [(s[0], 0.0)] + pts if n else []


def ols_line(xs, ys):
    """最小二乘参考线 y = a + b*x，返回 dict(slope, intercept, r)。"""
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    sxy = math.fsum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    syy = math.fsum((y - my) ** 2 for y in ys)
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0
    return {"slope": b, "intercept": a, "r": r}


def golden_jitter(i, width):
    """确定性黄金比抖动偏移（无随机数，双通道一致）。"""
    return (((i * 0.6180339887498949) % 1.0) - 0.5) * width


def p_fmt(p):
    """p 值格式化：4 位小数，<0.0001 记法。"""
    if p != p:
        return "p=NA"
    if p < 0.0001:
        return "p<0.0001"
    return "p=%.4f" % p
