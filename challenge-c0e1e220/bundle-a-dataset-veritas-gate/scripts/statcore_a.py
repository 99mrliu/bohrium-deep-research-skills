#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statcore_a — dataset-veritas-gate 独立统计核心（仅 Python 标准库）。

设计原则：
  * 零第三方依赖；所有分布函数用正则化不完全 Beta/Gamma 函数实现
    （连分式 + 级数，Numerical Recipes 风格，自写实现）。
  * scipy 仅在 ``--selftest`` 交叉校验时可选导入；缺失时自动跳过，
    不影响任何统计结果。
  * 所有函数把 ``None`` 当作缺失值处理（过滤后计算）。

覆盖：描述统计、D'Agostino K²、Levene(median)、Student t / Welch t、
Mann-Whitney U（tie 校正）、单因素 ANOVA、Welch ANOVA、Kruskal-Wallis
（tie 校正）、Hedges g、η²/ω²/ε²、Welch 均值差 CI、Hodges-Lehmann、
百分位 bootstrap CI（seed=20240501）、Holm 校正。
"""
import math
import random

BOOTSTRAP_SEED = 20240501
BOOTSTRAP_B = 2000

# ------------------------------------------------------------------
# 基础工具
# ------------------------------------------------------------------

def clean(xs):
    """过滤 None/NaN，返回纯 float 列表。"""
    out = []
    for x in xs:
        if x is None:
            continue
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if v != v:  # NaN
            continue
        out.append(v)
    return out


def vmean(xs):
    xs = clean(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def vvar(xs, ddof=1):
    xs = clean(xs)
    n = len(xs)
    if n < ddof + 1:
        return float("nan")
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def vsd(xs, ddof=1):
    v = vvar(xs, ddof)
    return math.sqrt(v) if v == v else v


def vmedian(xs):
    xs = sorted(clean(xs))
    n = len(xs)
    if n == 0:
        return float("nan")
    mid = n // 2
    return xs[mid] if n % 2 else 0.5 * (xs[mid - 1] + xs[mid])


def vquantile(xs, q):
    """R type-7 线性插值分位数。"""
    xs = sorted(clean(xs))
    n = len(xs)
    if n == 0:
        return float("nan")
    if n == 1:
        return xs[0]
    h = q * (n - 1)
    lo = int(math.floor(h))
    hi = min(lo + 1, n - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def vskew(xs):
    xs = clean(xs)
    n = len(xs)
    if n < 3:
        return float("nan")
    m = sum(xs) / n
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0
    m3 = sum((x - m) ** 3 for x in xs) / n
    return m3 / m2 ** 1.5


def vkurt_excess(xs):
    xs = clean(xs)
    n = len(xs)
    if n < 4:
        return float("nan")
    m = sum(xs) / n
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0
    m4 = sum((x - m) ** 4 for x in xs) / n
    return m4 / m2 ** 2 - 3.0


def rankdata(xs):
    """平均秩（ties 取均值）。输入不含 None（调用方先 clean）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _tie_sum(vals):
    """sum(t^3 - t) over tie groups。"""
    vals = sorted(vals)
    total = 0.0
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        t = j - i + 1
        if t > 1:
            total += t ** 3 - t
        i = j + 1
    return total


def summarize(xs):
    """描述统计字典；空数据返回 None。"""
    xs = clean(xs)
    n = len(xs)
    if n == 0:
        return None
    return {
        "n": n,
        "mean": vmean(xs),
        "sd": vsd(xs),
        "median": vmedian(xs),
        "q1": vquantile(xs, 0.25),
        "q3": vquantile(xs, 0.75),
        "min": xs[0] if isinstance(xs[0], float) else float(min(xs)),
        "max": float(max(xs)),
        "skewness": vskew(xs) if n >= 3 else None,
    }


# ------------------------------------------------------------------
# 特殊函数：正则化不完全 Beta / Gamma
# ------------------------------------------------------------------

def _beta_cont_frac(a, b, x):
    """不完全 Beta 的连分式部分（Lentz 算法）。"""
    MAXIT, EPS, TINY = 300, 3.0e-14, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < EPS:
            break
    return h


def beta_regularized(x, a, b):
    """I_x(a, b)：正则化不完全 Beta 函数。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_cont_frac(a, b, x) / a
    return 1.0 - front * _beta_cont_frac(b, a, 1.0 - x) / b


def gamma_q(a, x):
    """Q(a, x) = Γ(a,x)/Γ(a)：正则化上不完全 Gamma。"""
    if a <= 0 or x < 0:
        return float("nan")
    if x == 0:
        return 1.0
    if x < a + 1.0:
        # 级数求 P，再取 1-P
        ap = a
        term = 1.0 / a
        total = term
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 3.0e-14:
                break
        return 1.0 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # 连分式求 Q
    TINY = 1.0e-300
    b = x + 1.0 - a
    c = 1.0 / TINY
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < TINY:
            d = TINY
        c = b + an / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1.0) < 3.0e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


# ------------------------------------------------------------------
# 分布 CDF / PPF
# ------------------------------------------------------------------

def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_ppf(p):
    if p <= 0.0:
        return -1.0e12
    if p >= 1.0:
        return 1.0e12
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def t_cdf(t, df):
    x = df / (df + t * t)
    ib = beta_regularized(x, df / 2.0, 0.5)
    return 1.0 - 0.5 * ib if t >= 0 else 0.5 * ib


def t_ppf(p, df):
    if p <= 0.0:
        return -1.0e12
    if p >= 1.0:
        return 1.0e12
    lo, hi = -1.0e6, 1.0e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def f_cdf(f, d1, d2):
    if f <= 0.0:
        return 0.0
    return beta_regularized(d1 * f / (d1 * f + d2), d1 / 2.0, d2 / 2.0)


def f_ppf(p, d1, d2):
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0e12
    lo, hi = 0.0, 1.0e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f_cdf(mid, d1, d2) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def chi2_cdf(x, df):
    if x <= 0.0:
        return 0.0
    return 1.0 - gamma_q(df / 2.0, x / 2.0)


def chi2_sf(x, df):
    if x <= 0.0:
        return 1.0
    return gamma_q(df / 2.0, x / 2.0)


# ------------------------------------------------------------------
# 正态性 / 方差齐性
# ------------------------------------------------------------------

def dagostino_k2(xs):
    """D'Agostino-Pearson K² 综合正态性检验。

    返回 (K2, p)；n<8 返回 (None, None)（调用方按保守非正态处理）。
    """
    xs = clean(xs)
    n = len(xs)
    if n < 8:
        return None, None
    g1 = vskew(xs)
    g2 = vkurt_excess(xs) + 3.0  # 非超额峰度（Anscombe-Glynn 口径）
    # 偏度变换 (D'Agostino)
    y = g1 * math.sqrt(((n + 1) * (n + 3)) / (6.0 * (n - 2)))
    b2 = 3.0 * (n * n + 27 * n - 70) * (n + 1) * (n + 3) / \
        ((n - 2.0) * (n + 5) * (n + 7) * (n + 9))
    w2 = -1.0 + math.sqrt(2.0 * (b2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    a = math.sqrt(2.0 / (w2 - 1.0))
    z1 = delta * math.log(y / a + math.sqrt((y / a) ** 2 + 1.0))
    # 峰度变换 (Anscombe-Glynn)
    mu2 = 3.0 * (n - 1) / (n + 1)
    var2 = 24.0 * n * (n - 2) * (n - 3) / ((n + 1.0) ** 2 * (n + 3) * (n + 5))
    x2 = (g2 - mu2) / math.sqrt(var2)
    b = (6.0 * (n * n - 5 * n + 2)) / ((n + 7.0) * (n + 9.0)) * \
        math.sqrt((6.0 * (n + 3) * (n + 5)) / (n * (n - 2) * (n - 3)))
    A = 6.0 + 8.0 / b * (2.0 / b + math.sqrt(1.0 + 4.0 / (b * b)))
    if A <= 4.0:
        return None, None
    denom = 1.0 + x2 * math.sqrt(2.0 / (A - 4.0))
    if denom == 0.0:
        return None, None
    term = (1.0 if denom > 0 else -1.0) * (abs(1.0 - 2.0 / A) / abs(denom)) ** (1.0 / 3.0)
    z2 = (1.0 - 2.0 / (9.0 * A) - term) / math.sqrt(2.0 / (9.0 * A))
    k2 = z1 * z1 + z2 * z2
    return k2, chi2_sf(k2, 2)


def levene_median(groups):
    """Levene / Brown-Forsythe（median 中心）。返回 (W, df1, df2, p)。"""
    groups = [clean(g) for g in groups]
    k = len(groups)
    zs = [[abs(x - vmedian(g)) for x in g] for g in groups]
    ni = [len(z) for z in zs]
    n_total = sum(ni)
    if k < 2 or n_total <= k:
        return None, None, None, None
    zb_i = [sum(z) / n for z, n in zip(zs, ni)]
    zb = sum(sum(z) for z in zs) / n_total
    num = sum(n * (a - zb) ** 2 for n, a in zip(ni, zb_i))
    den = sum(sum((x - a) ** 2 for x in z) for z, a in zip(zs, zb_i))
    df1, df2 = k - 1, n_total - k
    if den <= 0:
        return 0.0, df1, df2, 1.0
    w = (n_total - k) * num / (df1 * den)
    return w, df1, df2, 1.0 - f_cdf(w, df1, df2)


# ------------------------------------------------------------------
# 两组检验
# ------------------------------------------------------------------

def ttest_pooled(x, y):
    """Student 独立样本 t（方差齐假设）。返回 (t, df, p)。"""
    x, y = clean(x), clean(y)
    n1, n2 = len(x), len(y)
    m1, m2 = vmean(x), vmean(y)
    v1, v2 = vvar(x), vvar(y)
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    se = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    df = n1 + n2 - 2
    if se == 0:
        t = 0.0 if m1 == m2 else math.copysign(1.0e12, m1 - m2)
        return t, df, 1.0 if m1 == m2 else 0.0
    t = (m1 - m2) / se
    return t, df, 2.0 * t_cdf(-abs(t), df)


def ttest_welch(x, y):
    """Welch 独立样本 t。返回 (t, df, p)。"""
    x, y = clean(x), clean(y)
    n1, n2 = len(x), len(y)
    m1, m2 = vmean(x), vmean(y)
    v1, v2 = vvar(x), vvar(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        t = 0.0 if m1 == m2 else math.copysign(1.0e12, m1 - m2)
        return t, 1, 1.0 if m1 == m2 else 0.0
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t = (m1 - m2) / math.sqrt(se2)
    return t, df, 2.0 * t_cdf(-abs(t), df)


def mannwhitney(x, y):
    """Mann-Whitney U（tie 校正正态近似，双侧）。返回 dict。"""
    x, y = clean(x), clean(y)
    n1, n2 = len(x), len(y)
    pooled = x + y
    ranks = rankdata(pooled)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    tie = _tie_sum(pooled)
    mu = n1 * n2 / 2.0
    sigma2 = n1 * n2 / 12.0 * ((n1 + n2 + 1) - tie / ((n1 + n2) * (n1 + n2 - 1)))
    if sigma2 <= 0:
        return {"U": u, "z": 0.0, "p": 1.0, "n1": n1, "n2": n2}
    # 连续性校正（与 scipy.stats.mannwhitneyu 默认一致）
    delta = abs(u - mu)
    z = (delta - 0.5) / math.sqrt(sigma2) if delta > 0.5 else 0.0
    p = 2.0 * norm_cdf(-z)
    return {"U": u, "z": z, "p": p, "n1": n1, "n2": n2}


# ------------------------------------------------------------------
# k 组检验
# ------------------------------------------------------------------

def anova_classic(groups):
    """单因素方差分析。返回 (F, df1, df2, p, ssb, ssw)。"""
    groups = [clean(g) for g in groups]
    k = len(groups)
    ni = [len(g) for g in groups]
    n_total = sum(ni)
    means = [vmean(g) for g in groups]
    gm = sum(m * n for m, n in zip(means, ni)) / n_total
    ssb = sum(n * (m - gm) ** 2 for n, m in zip(ni, means))
    ssw = sum(sum((x - vmean(g)) ** 2 for x in g) for g in groups)
    df1, df2 = k - 1, n_total - k
    if df2 <= 0 or ssw <= 0:
        return None, df1, df2, None, ssb, ssw
    f = (ssb / df1) / (ssw / df2)
    return f, df1, df2, 1.0 - f_cdf(f, df1, df2), ssb, ssw


def anova_welch(groups):
    """Welch 方差分析（方差不齐）。

    F' = A/(1 + 2(k-2)Λ/(k²-1))，Λ = Σ(1-wi/W)²/(ni-1)，
    df2 = (k²-1)/(3Λ)。k=2 时退化为 Welch t：F'=t²、df2 相同。
    返回 (F, df1, df2, p)。
    """
    groups = [clean(g) for g in groups]
    k = len(groups)
    ni = [len(g) for g in groups]
    means = [vmean(g) for g in groups]
    vari = [vvar(g) for g in groups]
    if any(v <= 0 or v != v for v in vari):
        return None, k - 1, None, None
    wi = [n / v for n, v in zip(ni, vari)]
    w_sum = sum(wi)
    xw = sum(w * m for w, m in zip(wi, means)) / w_sum
    a_num = sum(w * (m - xw) ** 2 for w, m in zip(wi, means)) / (k - 1)
    lam = sum((1.0 - w / w_sum) ** 2 / (n - 1) for w, n in zip(wi, ni))
    df1 = k - 1
    df2 = (k * k - 1) / (3.0 * lam) if lam > 0 else 1.0e9
    f = a_num / (1.0 + 2.0 * (k - 2) * lam / (k * k - 1))
    return f, df1, df2, 1.0 - f_cdf(f, df1, df2)


def kruskal(groups):
    """Kruskal-Wallis H（tie 校正）。返回 (H, df, p)。"""
    groups = [clean(g) for g in groups]
    k = len(groups)
    ni = [len(g) for g in groups]
    n_total = sum(ni)
    pooled = [x for g in groups for x in g]
    ranks = rankdata(pooled)
    r_sums = []
    pos = 0
    for n in ni:
        r_sums.append(sum(ranks[pos:pos + n]))
        pos += n
    h = 12.0 / (n_total * (n_total + 1)) * sum(r ** 2 / n for r, n in zip(r_sums, ni)) - 3.0 * (n_total + 1)
    tie = _tie_sum(pooled)
    corr = 1.0 - tie / (n_total ** 3 - n_total)
    if corr <= 0:
        return None, k - 1, None
    h = h / corr
    df = k - 1
    return h, df, chi2_sf(h, df)


# ------------------------------------------------------------------
# 效应量
# ------------------------------------------------------------------

def hedges_g(x, y):
    """Hedges g（小样本校正的标准化均值差，合并 SD 口径）。"""
    x, y = clean(x), clean(y)
    n1, n2 = len(x), len(y)
    sp2 = ((n1 - 1) * vvar(x) + (n2 - 1) * vvar(y)) / (n1 + n2 - 2)
    if sp2 <= 0:
        return None
    d = (vmean(x) - vmean(y)) / math.sqrt(sp2)
    j = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    return j * d


def eta_squared(groups):
    """η² = SS_between / SS_total。"""
    groups = [clean(g) for g in groups]
    ni = [len(g) for g in groups]
    means = [vmean(g) for g in groups]
    gm = sum(m * n for m, n in zip(means, ni)) / sum(ni)
    ssb = sum(n * (m - gm) ** 2 for n, m in zip(ni, means))
    ssw = sum(sum((x - vmean(g)) ** 2 for x in g) for g in groups)
    sst = ssb + ssw
    return ssb / sst if sst > 0 else None


def omega_squared(groups):
    """ω²（基于经典 ANOVA 的偏差校正效应量）。"""
    f, df1, df2, _, _, _ = anova_classic(groups)
    if f is None:
        return None
    return (df1 * (f - 1.0)) / (df1 * f + df2 + 1.0)


def epsilon_squared_kw(h, n, k):
    """Kruskal-Wallis 的 ε²。"""
    if h is None or n <= k:
        return None
    return (h - k + 1.0) / (n - k)


def rank_biserial(x, y):
    """rank-biserial r = 1 - 2U/(n1·n2)；>0 表示 x 组整体秩更高。"""
    x, y = clean(x), clean(y)
    res = mannwhitney(x, y)
    return 1.0 - 2.0 * res["U"] / (len(x) * len(y))


# ------------------------------------------------------------------
# 置信区间
# ------------------------------------------------------------------

def ci_welch_diff(x, y, alpha=0.05):
    """Welch 均值差 CI。返回 (lo, hi, df, diff)。"""
    x, y = clean(x), clean(y)
    n1, n2 = len(x), len(y)
    v1, v2 = vvar(x), vvar(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        return None, None, None, None
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    tcrit = t_ppf(1.0 - alpha / 2.0, df)
    diff = vmean(x) - vmean(y)
    half = tcrit * math.sqrt(se2)
    return diff - half, diff + half, df, diff


def hodges_lehmann(x, y, alpha=0.05):
    """Hodges-Lehmann 位置差（两两差中位数）+ 正态近似区间。"""
    x, y = clean(x), clean(y)
    diffs = sorted(a - b for a in x for b in y)
    n = len(diffs)
    if n == 0:
        return None, None, None
    est = vmedian(diffs)
    k = int(math.floor(0.5 * n - norm_ppf(1.0 - alpha / 2.0) * math.sqrt(n / 4.0)))
    k = max(0, min(n - 1, k))
    return est, diffs[k], diffs[n - 1 - k]


def ci_bootstrap(func, samples, B=BOOTSTRAP_B, alpha=0.05, seed=BOOTSTRAP_SEED):
    """百分位 bootstrap CI。samples 为传给 func 的样本元组。

    使用固定 seed 的独立 Random 实例，结果完全可复现。
    返回 (lo, hi, B_used)。
    """
    rng = random.Random(seed)
    stats = []
    samples = [clean(s) for s in samples]
    for _ in range(B):
        try:
            draw = []
            for s in samples:
                n = len(s)
                idx = [rng.randrange(n) for _ in range(n)]
                draw.append([s[i] for i in idx])
            val = func(*draw)
            if val is not None and val == val:
                stats.append(val)
        except Exception:
            continue
    if len(stats) < B // 2:
        return None, None, len(stats)
    stats.sort()
    lo = stats[int((alpha / 2.0) * len(stats))]
    hi = stats[min(len(stats) - 1, int((1.0 - alpha / 2.0) * len(stats)))]
    return lo, hi, len(stats)


# ------------------------------------------------------------------
# 多重比较
# ------------------------------------------------------------------

def holm(pvals):
    """Holm 逐步校正；None 原样保留。返回与输入等长列表。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: (pvals[i] is None, pvals[i] or 0.0))
    adj = [None] * m
    running = 0.0
    for rank, idx in enumerate(order):
        p = pvals[idx]
        if p is None:
            continue
        val = min(1.0, (m - rank) * p)
        running = max(running, val)
        adj[idx] = running
    return adj


# ------------------------------------------------------------------
# 可选 scipy 交叉校验（python3 statcore_a.py --selftest）
# ------------------------------------------------------------------

def _selftest():
    print("== statcore_a selftest ==")
    ok = True
    try:
        import scipy.stats as st  # noqa
    except Exception:
        print("scipy 不可用：跳过交叉校验（核心功能不受影响）")
        st = None
    import random as _r
    rng = _r.Random(7)
    a = [rng.gauss(10, 2) for _ in range(40)]
    b = [rng.gauss(11, 3) for _ in range(35)]
    c = [rng.gauss(9.5, 2.5) for _ in range(30)]
    if st:
        checks = []
        t1, df1, p1 = ttest_pooled(a, b)
        st1 = st.ttest_ind(a, b, equal_var=True)
        checks.append(("ttest_pooled t", t1, st1.statistic))
        checks.append(("ttest_pooled p", p1, st1.pvalue))
        t2, df2, p2 = ttest_welch(a, b)
        st2 = st.ttest_ind(a, b, equal_var=False)
        checks.append(("ttest_welch t", t2, st2.statistic))
        checks.append(("ttest_welch df", df2, st2.df))
        checks.append(("ttest_welch p", p2, st2.pvalue))
        mw = mannwhitney(a, b)
        stm = st.mannwhitneyu(a, b)
        checks.append(("mannwhitney p", mw["p"], stm.pvalue))
        f, d1, d2, p, _, _ = anova_classic([a, b, c])
        sta = st.f_oneway(a, b, c)
        checks.append(("anova F", f, sta.statistic))
        checks.append(("anova p", p, sta.pvalue))
        h, hk, hp = kruskal([a, b, c])
        stk = st.kruskal(a, b, c)
        checks.append(("kruskal H", h, stk.statistic))
        checks.append(("kruskal p", hp, stk.pvalue))
        w, ld1, ld2, lp = levene_median([a, b, c])
        stl = st.levene(a, b, c, center="median")
        checks.append(("levene W", w, stl.statistic))
        checks.append(("levene p", lp, stl.pvalue))
        k2, kp = dagostino_k2(a)
        std = st.normaltest(a)
        checks.append(("dagostino K2", k2, std.statistic))
        checks.append(("dagostino p", kp, std.pvalue))
        for name, mine, ref in checks:
            diff = abs(mine - ref)
            rel = diff / max(1.0, abs(ref))
            flag = "OK " if rel < 1e-6 else "FAIL"
            if rel >= 1e-6:
                ok = False
            print(f"  [{flag}] {name}: ours={mine:.10g} scipy={ref:.10g} rel={rel:.2e}")
        # Welch ANOVA k=2 必须退化为 Welch t
        f2, wdf1, wdf2, _ = anova_welch([a, b])
        tt, tdf, _ = ttest_welch(a, b)
        print(f"  welch_anova(k=2) F={f2:.8f} vs t^2={tt*tt:.8f}, df2={wdf2:.4f} vs {tdf:.4f}")
        if abs(f2 - tt * tt) > 1e-6 or abs(wdf2 - tdf) > 1e-6:
            ok = False
            print("  [FAIL] welch_anova k=2 退化校验")
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("statcore_a：统计核心模块（用 --selftest 运行 scipy 交叉校验）")
