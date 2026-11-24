#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statcore_d.py — bundle-d 独立统计核心（纯标准库实现）。

范围（SPEC 共同统计范围，独立编写，不引用任何外部模块）：
- 分布函数：正则化不完全 beta/gamma -> t / F / chi2 / 正态 CDF 与 t 临界值；
- 描述统计：n、均值、SD、中位数、Q1/Q3、min/max、偏度；
- 假设检验：D'Agostino K^2 正态性（n>=8）、Levene（median 中心）、
  Student t / Welch t / Mann-Whitney U（tie 校正）、
  单因素 ANOVA / Welch ANOVA / Kruskal-Wallis（tie 校正）；
- 效应量：Hedges g（bootstrap percentile CI）、均值差 Welch CI、
  Hodges-Lehmann 中位数差（bootstrap CI）、eta^2 / omega^2 / epsilon^2；
- 多重比较：Holm 校正。

scipy 仅用于本机交叉校验，本模块自身零依赖。
"""
import math
import random

__all__ = [
    "norm_cdf", "t_cdf", "t_ppf", "f_cdf", "chi2_sf",
    "descriptive", "dagostino_k2", "levene_median",
    "student_t", "welch_t", "mann_whitney",
    "anova_oneway", "welch_anova", "kruskal_wallis",
    "hedges_g", "bootstrap_hedges_g_ci", "mean_diff_welch_ci",
    "hodges_lehmann", "bootstrap_hl_ci",
    "eta_squared", "omega_squared", "epsilon_squared_kw",
    "holm_adjust", "rankdata",
]

FPMIN = 1e-300
EPS = 3e-14
MAXIT = 300


# ---------------------------------------------------------------------------
# 分布函数（正则化不完全 beta / gamma）
# ---------------------------------------------------------------------------

def _betacf(a, b, x):
    """不完全 beta 的连分式（Numerical Recipes betacf）。"""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    """正则化不完全 beta 函数 I_x(a, b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def gammainc_p(a, x):
    """正则化下不完全 gamma P(a, x)（级数表示）。"""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(MAXIT):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * EPS:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    return 1.0 - gammainc_q(a, x)


def gammainc_q(a, x):
    """正则化上不完全 gamma Q(a, x)（连分式表示）。"""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - gammainc_p(a, x)
    b = x + 1.0 - a
    c = 1.0 / FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, MAXIT + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def t_cdf(t, df):
    """Student t 分布 CDF。"""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    ib = betai(df / 2.0, 0.5, x)
    if t >= 0.0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


def t_ppf(p, df):
    """t 分布分位数（二分法，供 Welch CI 临界值使用）。"""
    if not 0.0 < p < 1.0:
        return float("nan")
    lo, hi = -1.0, 1.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
        if hi > 1e10:
            break
    while t_cdf(lo, df) > p:
        lo *= 2.0
        if lo < -1e10:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def f_cdf(f, d1, d2):
    """F 分布 CDF。"""
    if f <= 0.0:
        return 0.0
    x = (d1 * f) / (d1 * f + d2)
    return betai(d1 / 2.0, d2 / 2.0, x)


def chi2_sf(x, k):
    """卡方分布生存函数。"""
    if x <= 0.0:
        return 1.0
    return gammainc_q(k / 2.0, x / 2.0)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _mean(xs):
    return sum(xs) / len(xs)


def _variance(xs, ddof=1):
    n = len(xs)
    if n <= ddof - 1 + 1 and ddof >= 1 and n < 2:
        return float("nan")
    m = _mean(xs)
    return sum((v - m) ** 2 for v in xs) / (n - ddof)


def _quantile(sorted_xs, q):
    """线性插值分位数（与 numpy 默认 linear 一致）。"""
    n = len(sorted_xs)
    if n == 1:
        return sorted_xs[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def descriptive(xs):
    """n、均值、SD、中位数、Q1/Q3、min/max、偏度（Fisher g1）。"""
    n = len(xs)
    if n == 0:
        return {"n": 0}
    m = _mean(xs)
    srt = sorted(xs)
    m2 = sum((v - m) ** 2 for v in xs) / n
    sd = math.sqrt(m2 * n / (n - 1)) if n > 1 else 0.0
    if n > 2 and m2 > 0.0:
        m3 = sum((v - m) ** 3 for v in xs) / n
        skew = m3 / (m2 ** 1.5)
    else:
        skew = 0.0
    return {
        "n": n,
        "mean": m,
        "sd": sd,
        "median": _quantile(srt, 0.5),
        "q1": _quantile(srt, 0.25),
        "q3": _quantile(srt, 0.75),
        "min": srt[0],
        "max": srt[-1],
        "skew": skew,
    }


def rankdata(xs):
    """平均秩（处理并列），返回与输入等长的秩列表（1 起）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    n = len(xs)
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _tie_counts(xs):
    counts = {}
    for v in xs:
        counts[v] = counts.get(v, 0) + 1
    return [c for c in counts.values() if c > 1]


# ---------------------------------------------------------------------------
# 正态性与方差齐性
# ---------------------------------------------------------------------------

def dagostino_k2(xs):
    """D'Agostino-Pearson K^2 正态性检验。

    n < 8 返回 None（调用方保守按非正态处理并注明）。
    返回 (K2, p, z_skew, z_kurt)。
    """
    n = len(xs)
    if n < 8:
        return None
    m = _mean(xs)
    m2 = sum((v - m) ** 2 for v in xs) / n
    m3 = sum((v - m) ** 3 for v in xs) / n
    m4 = sum((v - m) ** 4 for v in xs) / n
    if m2 <= 0.0:
        return None
    g1 = m3 / (m2 ** 1.5)
    b2 = m4 / (m2 ** 2)  # 未减 3 的样本峰度（与 scipy normaltest 口径一致）

    # 偏度变换（D'Agostino 1970）
    y = g1 * math.sqrt(((n + 1.0) * (n + 3.0)) / (6.0 * (n - 2.0)))
    beta2 = (3.0 * (n * n + 27.0 * n - 70.0) * (n + 1.0) * (n + 3.0)
             / ((n - 2.0) * (n + 5.0) * (n + 7.0) * (n + 9.0)))
    w2 = -1.0 + math.sqrt(2.0 * (beta2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    alpha = math.sqrt(2.0 / (w2 - 1.0))
    y_over_a = y / alpha
    z1 = delta * math.log(y_over_a + math.sqrt(y_over_a ** 2 + 1.0))

    # 峰度变换（Anscombe & Glynn 1983）
    e_b2 = 3.0 * (n - 1.0) / (n + 1.0)
    var_b2 = (24.0 * n * (n - 2.0) * (n - 3.0)
              / ((n + 1.0) ** 2 * (n + 3.0) * (n + 5.0)))
    x = (b2 - e_b2) / math.sqrt(var_b2)
    sqrt_beta1 = (6.0 * (n * n - 5.0 * n + 2.0) / ((n + 7.0) * (n + 9.0))
                  * math.sqrt(6.0 * (n + 3.0) * (n + 5.0)
                              / (n * (n - 2.0) * (n - 3.0))))
    a = 6.0 + 8.0 / sqrt_beta1 * (2.0 / sqrt_beta1
                                  + math.sqrt(1.0 + 4.0 / sqrt_beta1 ** 2))
    denom = 1.0 + x * math.sqrt(2.0 / (a - 4.0))
    base = (1.0 - 2.0 / a) / denom
    if base >= 0.0:
        term2 = base ** (1.0 / 3.0)
    else:
        term2 = -((-base) ** (1.0 / 3.0))
    z2 = (1.0 - 2.0 / (9.0 * a) - term2) / math.sqrt(2.0 / (9.0 * a))

    k2 = z1 * z1 + z2 * z2
    return k2, chi2_sf(k2, 2.0), z1, z2


def levene_median(groups):
    """Levene 方差齐性检验（median 中心，即 Brown-Forsythe）。"""
    zgroups = []
    for g in groups:
        med = _quantile(sorted(g), 0.5)
        zgroups.append([abs(v - med) for v in g])
    f, df1, df2, p, _, _, _ = anova_oneway(zgroups)
    return f, df1, df2, p


# ---------------------------------------------------------------------------
# 两组检验
# ---------------------------------------------------------------------------

def student_t(a, b):
    n1, n2 = len(a), len(b)
    v1, v2 = _variance(a), _variance(b)
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2.0)
    se = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    t = (_mean(a) - _mean(b)) / se
    df = n1 + n2 - 2.0
    p = 2.0 * (1.0 - t_cdf(abs(t), df))
    return t, df, p


def welch_t(a, b):
    n1, n2 = len(a), len(b)
    v1, v2 = _variance(a), _variance(b)
    se2 = v1 / n1 + v2 / n2
    t = (_mean(a) - _mean(b)) / math.sqrt(se2)
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1.0) + (v2 / n2) ** 2 / (n2 - 1.0))
    p = 2.0 * (1.0 - t_cdf(abs(t), df))
    return t, df, p


def mann_whitney(a, b):
    """Mann-Whitney U（正态近似 + tie 校正 + 连续性校正），双侧。

    返回 (U1, z, p)。符号约定：z > 0 表示 a 组秩次更高。
    """
    n1, n2 = len(a), len(b)
    combined = list(a) + list(b)
    ranks = rankdata(combined)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1.0) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    tie_term = sum(c ** 3 - c for c in _tie_counts(combined))
    var = (n1 * n2 / 12.0) * ((n + 1.0) - tie_term / (n * (n - 1.0)))
    if var <= 0.0:
        return u1, 0.0, 1.0
    sd = math.sqrt(var)
    diff = u1 - mu
    if diff > 0:
        z = (diff - 0.5) / sd
    elif diff < 0:
        z = (diff + 0.5) / sd
    else:
        z = 0.0
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return u1, z, p


# ---------------------------------------------------------------------------
# k 组检验
# ---------------------------------------------------------------------------

def anova_oneway(groups):
    """经典单因素方差分析。返回 (F, df1, df2, p, ss_b, ss_w, ss_t)。"""
    k = len(groups)
    allv = [v for g in groups for v in g]
    n_total = len(allv)
    grand = _mean(allv)
    ss_b = sum(len(g) * (_mean(g) - grand) ** 2 for g in groups)
    ss_t = sum((v - grand) ** 2 for v in allv)
    ss_w = ss_t - ss_b
    df1 = k - 1.0
    df2 = n_total - k
    if df2 <= 0 or ss_w <= 0.0:
        return float("nan"), df1, df2, 1.0, ss_b, ss_w, ss_t
    f = (ss_b / df1) / (ss_w / df2)
    p = 1.0 - f_cdf(f, df1, df2)
    return f, df1, df2, p, ss_b, ss_w, ss_t


def welch_anova(groups):
    """Welch（1951）异方差单因素方差分析。返回 (F, df1, df2, p)。"""
    k = len(groups)
    ns = [len(g) for g in groups]
    vs = [_variance(g) for g in groups]
    ms = [_mean(g) for g in groups]
    ws = [ns[i] / vs[i] for i in range(k)]
    w_sum = sum(ws)
    m_w = sum(ws[i] * ms[i] for i in range(k)) / w_sum
    lam = sum((1.0 - ws[i] / w_sum) ** 2 / (ns[i] - 1.0) for i in range(k))
    df1 = k - 1.0
    num = sum(ws[i] * (ms[i] - m_w) ** 2 for i in range(k)) / df1
    den = 1.0 + (2.0 * (k - 2.0) / (k * k - 1.0)) * lam
    f = num / den
    df2 = (k * k - 1.0) / (3.0 * lam)
    p = 1.0 - f_cdf(f, df1, df2)
    return f, df1, df2, p


def kruskal_wallis(groups):
    """Kruskal-Wallis H（tie 校正）。返回 (H, df, p)。"""
    k = len(groups)
    allv = [v for g in groups for v in g]
    n = len(allv)
    ranks = rankdata(allv)
    pos = 0
    rank_sums = []
    for g in groups:
        rank_sums.append(sum(ranks[pos:pos + len(g)]))
        pos += len(g)
    h = 12.0 / (n * (n + 1.0)) * sum(
        rank_sums[i] ** 2 / len(groups[i]) for i in range(k)) - 3.0 * (n + 1.0)
    tie_term = sum(c ** 3 - c for c in _tie_counts(allv))
    correction = 1.0 - tie_term / (n ** 3 - n) if n > 1 else 1.0
    if correction <= 0.0:
        correction = 1.0
    h = h / correction
    df = k - 1.0
    return h, df, chi2_sf(h, df)


# ---------------------------------------------------------------------------
# 效应量与置信区间
# ---------------------------------------------------------------------------

def hedges_g(a, b):
    """Hedges g = J * (mean_a - mean_b) / s_pooled。"""
    n1, n2 = len(a), len(b)
    v1, v2 = _variance(a), _variance(b)
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2.0))
    if sp == 0.0:
        return 0.0
    d = (_mean(a) - _mean(b)) / sp
    j = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    return j * d


def bootstrap_hedges_g_ci(a, b, B=2000, seed=20240501, alpha=0.05):
    """Hedges g 的 bootstrap percentile CI（固定种子，可复现）。"""
    rng = random.Random(seed)
    n1, n2 = len(a), len(b)
    reps = []
    for _ in range(B):
        ra = [a[rng.randrange(n1)] for _ in range(n1)]
        rb = [b[rng.randrange(n2)] for _ in range(n2)]
        try:
            reps.append(hedges_g(ra, rb))
        except (ZeroDivisionError, ValueError):
            continue
    reps.sort()
    if not reps:
        return None
    return (_quantile(reps, alpha / 2.0), _quantile(reps, 1.0 - alpha / 2.0))


def mean_diff_welch_ci(a, b, alpha=0.05):
    """均值差（a - b）的 Welch t CI。"""
    n1, n2 = len(a), len(b)
    v1, v2 = _variance(a), _variance(b)
    diff = _mean(a) - _mean(b)
    se2 = v1 / n1 + v2 / n2
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1.0) + (v2 / n2) ** 2 / (n2 - 1.0))
    tcrit = t_ppf(1.0 - alpha / 2.0, df)
    half = tcrit * math.sqrt(se2)
    return diff, (diff - half, diff + half)


def _pair_diffs(a, b, rng=None, cap=20000):
    """全部成对差 a_i - b_j；超过 cap 时用 rng 抽样近似。"""
    total = len(a) * len(b)
    if total <= cap or rng is None:
        return [x - y for x in a for y in b]
    return [a[rng.randrange(len(a))] - b[rng.randrange(len(b))]
            for _ in range(cap)]


def hodges_lehmann(a, b, seed=20240501):
    """Hodges-Lehmann 中位数差估计（a - b）。"""
    rng = random.Random(seed)
    diffs = _pair_diffs(a, b, rng)
    diffs.sort()
    return _quantile(diffs, 0.5)


def bootstrap_hl_ci(a, b, B=2000, seed=20240501, alpha=0.05):
    """Hodges-Lehmann 中位数差的 bootstrap percentile CI。"""
    rng = random.Random(seed + 7)
    n1, n2 = len(a), len(b)
    reps = []
    for _ in range(B):
        ra = [a[rng.randrange(n1)] for _ in range(n1)]
        rb = [b[rng.randrange(n2)] for _ in range(n2)]
        diffs = _pair_diffs(ra, rb, rng)
        diffs.sort()
        reps.append(_quantile(diffs, 0.5))
    reps.sort()
    return (_quantile(reps, alpha / 2.0), _quantile(reps, 1.0 - alpha / 2.0))


def eta_squared(ss_b, ss_t):
    return ss_b / ss_t if ss_t > 0.0 else float("nan")


def omega_squared(ss_b, ss_w, ss_t, df2, k):
    """omega^2 = (SS_b - (k-1)*MS_w) / (SS_t + MS_w)。"""
    if df2 <= 0:
        return float("nan")
    ms_w = ss_w / df2
    den = ss_t + ms_w
    if den == 0.0:
        return float("nan")
    return (ss_b - (k - 1.0) * ms_w) / den


def epsilon_squared_kw(h, n, k):
    """Kruskal-Wallis 的 epsilon^2。"""
    if n - k <= 0:
        return float("nan")
    return (h - k + 1.0) / (n - k)


def holm_adjust(pvals):
    """Holm 逐步校正，返回与输入等长的调整后 p 列表。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * pvals[idx]
        running = max(running, val)
        adj[idx] = min(1.0, running)
    return adj


def effect_magnitude(name, value):
    """常用阈值判级：d/g: 0.2/0.5/0.8；eta2/omega2/eps2: 0.01/0.06/0.14。"""
    v = abs(value)
    if name in ("hedges_g", "cohens_d", "g", "d"):
        if v < 0.2:
            return "negligible"
        if v < 0.5:
            return "small"
        if v < 0.8:
            return "medium"
        return "large"
    if v < 0.01:
        return "negligible"
    if v < 0.06:
        return "small"
    if v < 0.14:
        return "medium"
    return "large"
