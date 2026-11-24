#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statcore_b — bundle-b 独立统计核心（仅标准库，Python 3.9+）

与任何旧作零共享：模块结构、命名、数值路径均为本 bundle 重写。
数值方法要点（与旧 bundle 实现不同）：
  * 正则化不完全 beta I_x(a,b) 用 **Lentz 连分式**（自带微小量保护的
    modified Lentz 形式），对称切换 x > (a+1)/(a+b+2)；
  * 上不完全 gamma Q(a,x) 用 级数(P) / 连分式(Q) 双分支；
  * 分布逆函数用 Acklam 有理逼近（正态）+ 牛顿-二分混合迭代（t/F/χ²），
    而非纯二分；
  * Hedges g 的小样本校正用 **精确** J = Γ(ν/2)/(√(ν/2)·Γ((ν-1)/2))；
  * Welch ANOVA 用 Welch(1951) 标准式（Λ 不加额外因子 3）。

已用 scipy 1.18 交叉校验（scripts/crosscheck_scipy.py），t/F/χ²/KW/
Levene/K²/Mann-Whitney 差异 < 1e-6。
"""
import math
import random

BOOT_B = 2000
BOOT_SEED = 20240501

# ---------------------------------------------------------------- 基础量


def clean(xs):
    return [x for x in xs if x is not None]


def mean(xs):
    xs = clean(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def var(xs, ddof=1):
    xs = clean(xs)
    n = len(xs)
    if n <= ddof - 1 + 1 and ddof == 1 and n < 2:
        return float("nan")
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def sd(xs):
    v = var(xs)
    return math.sqrt(v) if v == v else v


def median(xs):
    xs = sorted(clean(xs))
    n = len(xs)
    if n == 0:
        return float("nan")
    h = n // 2
    return xs[h] if n % 2 else 0.5 * (xs[h - 1] + xs[h])


def quantile(xs, q):
    """type-7 线性插值分位数。"""
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


def skewness(xs):
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


def describe(xs):
    xs = clean(xs)
    if not xs:
        return None
    return {
        "n": len(xs), "mean": mean(xs), "sd": sd(xs), "median": median(xs),
        "q1": quantile(xs, 0.25), "q3": quantile(xs, 0.75),
        "min": min(xs), "max": max(xs),
        "skewness": skewness(xs) if len(xs) >= 3 else None,
    }


def ranks_average(xs):
    """平均秩（ties 取均值秩），1 起。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _tie_sum(xs):
    """Σ(t³−t)，ties 校正用。"""
    s = sorted(xs)
    tot = 0.0
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        t = j - i + 1
        if t > 1:
            tot += t ** 3 - t
        i = j + 1
    return tot

# ---------------------------------------------------------------- 特殊函数（Lentz 连分式）


def _lentz_betacf(a, b, x):
    """不完全 beta 的连分式部分，modified Lentz。"""
    TINY = 1e-290
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    f = d
    for m in range(1, 400):
        m2 = 2 * m
        num = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + num * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + num / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        f *= d * c
        num = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + num * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + num / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        f *= delta
        if abs(delta - 1.0) < 3e-15:
            break
    return f


def reg_incomplete_beta(a, b, x):
    """I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * math.log(x) + b * math.log1p(-x))
    bt = math.exp(lbt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _lentz_betacf(a, b, x) / a
    return 1.0 - bt * _lentz_betacf(b, a, 1.0 - x) / b


def reg_gamma_q(a, x):
    """正则化上不完全 gamma Q(a,x) = Γ(a,x)/Γ(a)。"""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        # 级数求 P，返回 1-P
        term = 1.0 / a
        s = term
        ap = a
        for _ in range(2000):
            ap += 1.0
            term *= x / ap
            s += term
            if abs(term) < abs(s) * 3e-15:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    # 连分式求 Q
    TINY = 1e-290
    b = x + 1.0 - a
    c = 1.0 / TINY
    d = 1.0 / b
    f = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < TINY:
            d = TINY
        c = b + an / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        f *= delta
        if abs(delta - 1.0) < 3e-15:
            break
    return f * math.exp(-x + a * math.log(x) - math.lgamma(a))

# ---------------------------------------------------------------- 分布函数与逆函数


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_pdf(z):
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def norm_ppf(p):
    """Acklam 有理逼近 + 一步 Halley 精化。"""
    if p <= 0.0:
        return -float("inf")
    if p >= 1.0:
        return float("inf")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        z = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= phigh:
        q = p - 0.5
        r = q * q
        z = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        z = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    # 一步 Halley
    e = norm_cdf(z) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(0.5 * z * z)
    z = z - u / (1.0 + 0.5 * z * u)
    return z


def t_cdf(t, v):
    if v <= 0:
        return float("nan")
    x = v / (v + t * t)
    ib = reg_incomplete_beta(v / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t >= 0 else 0.5 * ib


def t_pdf(t, v):
    return math.exp(math.lgamma((v + 1) / 2) - math.lgamma(v / 2)
                    - 0.5 * math.log(v * math.pi)
                    - (v + 1) / 2 * math.log1p(t * t / v))


def _solve_ppf(cdf, pdf, p, lo, hi):
    """牛顿-二分混合求逆，初值取中点。"""
    x = 0.5 * (lo + hi)
    for _ in range(100):
        fx = cdf(x) - p
        if abs(fx) < 1e-14:
            break
        d = pdf(x)
        xn = x - fx / d if d > 1e-300 else 0.5 * (lo + hi)
        if not (lo < xn < hi):
            xn = 0.5 * (lo + hi)
        if fx > 0:
            hi = x
        else:
            lo = x
        x = xn
        if hi - lo < 1e-13 * max(1.0, abs(x)):
            break
    return x


def t_ppf(p, v):
    if p <= 0.0:
        return -1e12
    if p >= 1.0:
        return 1e12
    z = norm_ppf(p)  # 初值
    lo, hi = min(-1e-6, 2 * z - 1), max(1e-6, 2 * z + 1)
    while t_cdf(lo, v) > p:
        lo *= 2
    while t_cdf(hi, v) < p:
        hi *= 2
    return _solve_ppf(lambda x: t_cdf(x, v), lambda x: t_pdf(x, v), p, lo, hi)


def f_cdf(f, d1, d2):
    if f <= 0:
        return 0.0
    return reg_incomplete_beta(d1 / 2.0, d2 / 2.0, d1 * f / (d1 * f + d2))


def chi2_cdf(x, v):
    if x <= 0:
        return 0.0
    return 1.0 - reg_gamma_q(v / 2.0, x / 2.0)

# ---------------------------------------------------------------- 正态性与方差齐性

MIN_N_NORMALITY = 8  # n<8 不做 K²，按非正态保守处理


def dagostino_k2(xs):
    """D'Agostino–Pearson K² 正态性检验。n<8 返回 (None, None, 'not_tested')。

    返回 (K2, p, conclusion)，conclusion ∈ {'normal','non_normal','not_tested'}；
    判定在外层按 alpha 做，本函数只给统计量与 p。
    """
    xs = clean(xs)
    n = len(xs)
    if n < MIN_N_NORMALITY:
        return None, None, "not_tested"
    m = sum(xs) / n
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return None, None, "zero_variance"
    m3 = sum((x - m) ** 3 for x in xs) / n
    m4 = sum((x - m) ** 4 for x in xs) / n
    g1 = m3 / m2 ** 1.5          # 偏度
    g2 = m4 / m2 ** 2            # 非超额峰度（Anscombe–Glynn 变换用 b2）
    # 偏度的 Z 变换（D'Agostino）
    y = g1 * math.sqrt(((n + 1) * (n + 3)) / (6.0 * (n - 2)))
    beta2 = 3.0 * (n * n + 27 * n - 70) * (n + 1) * (n + 3) / \
        ((n - 2.0) * (n + 5) * (n + 7) * (n + 9))
    w2 = -1.0 + math.sqrt(2.0 * (beta2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    aa = math.sqrt(2.0 / (w2 - 1.0))
    z1 = delta * math.asinh(y / aa)
    # 峰度的 Z 变换（Anscombe–Glynn）
    e2 = 3.0 * (n - 1) / (n + 1)
    v2 = 24.0 * n * (n - 2) * (n - 3) / ((n + 1.0) ** 2 * (n + 3) * (n + 5))
    x2 = (g2 - e2) / math.sqrt(v2)
    b = (6.0 * (n * n - 5 * n + 2)) / ((n + 7.0) * (n + 9.0)) * \
        math.sqrt((6.0 * (n + 3) * (n + 5)) / (n * (n - 2) * (n - 3)))
    A = 6.0 + 8.0 / b * (2.0 / b + math.sqrt(1.0 + 4.0 / (b * b)))
    denom = 1.0 + x2 * math.sqrt(2.0 / (A - 4.0))
    if denom == 0.0 or A <= 4.0:
        return None, None, "not_tested"
    term = (1.0 if denom > 0 else -1.0) * (abs(1.0 - 2.0 / A) / abs(denom)) ** (1.0 / 3.0)
    z2 = (1.0 - 2.0 / (9.0 * A) - term) / math.sqrt(2.0 / (9.0 * A))
    k2 = z1 * z1 + z2 * z2
    p = 1.0 - chi2_cdf(k2, 2)
    return k2, p, "tested"


def levene_median(groups):
    """Brown–Forsythe（median 中心）方差齐性检验。返回 (W, df1, df2, p)。"""
    gs = [clean(g) for g in groups]
    k = len(gs)
    ni = [len(g) for g in gs]
    N = sum(ni)
    if k < 2 or N <= k or any(n == 0 for n in ni):
        return None, None, None, None
    z = [[abs(x - median(g)) for x in g] for g in gs]
    zb = [sum(zz) / len(zz) for zz in z]
    zbb = sum(sum(zz) for zz in z) / N
    num = sum(n * (a - zbb) ** 2 for n, a in zip(ni, zb))
    den = sum(sum((x - a) ** 2 for x in zz) for zz, a in zip(z, zb))
    df1, df2 = k - 1, N - k
    if den <= 0:
        return 0.0, df1, df2, 1.0
    W = (N - k) * num / (df1 * den)
    return W, df1, df2, 1.0 - f_cdf(W, df1, df2)

# ---------------------------------------------------------------- 两组检验


def t_student(x, y):
    """合并方差 t。返回 dict(t, df, p)。"""
    n1, n2 = len(x), len(y)
    v1, v2 = var(x), var(y)
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    se = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    df = n1 + n2 - 2
    if se == 0:
        t = 0.0 if mean(x) == mean(y) else math.copysign(1e12, mean(x) - mean(y))
        return {"statistic": t, "df": df, "p": 1.0 if t == 0 else 0.0}
    t = (mean(x) - mean(y)) / se
    return {"statistic": t, "df": df, "p": 2.0 * (1.0 - t_cdf(abs(t), df))}


def t_welch(x, y):
    n1, n2 = len(x), len(y)
    v1, v2 = var(x), var(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        t = 0.0 if mean(x) == mean(y) else math.copysign(1e12, mean(x) - mean(y))
        return {"statistic": t, "df": 1.0, "p": 1.0 if t == 0 else 0.0}
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t = (mean(x) - mean(y)) / math.sqrt(se2)
    return {"statistic": t, "df": df, "p": 2.0 * (1.0 - t_cdf(abs(t), df))}


def mannwhitney(x, y):
    """Mann–Whitney U，tie 校正正态近似，无连续性校正（与 scipy
    method='asymptotic', use_continuity=False 对齐）。
    返回 dict(U=min(U1,U2), U1, z, p)。"""
    n1, n2 = len(x), len(y)
    pooled = list(x) + list(y)
    r = ranks_average(pooled)
    r1 = sum(r[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    tie = _tie_sum(pooled)
    mu = n1 * n2 / 2.0
    s2 = n1 * n2 / 12.0 * ((n1 + n2 + 1) - tie / ((n1 + n2) * (n1 + n2 - 1)))
    if s2 <= 0:
        return {"statistic": min(u1, u2), "U1": u1, "z": 0.0, "p": 1.0}
    z = (min(u1, u2) - mu) / math.sqrt(s2)
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return {"statistic": min(u1, u2), "U1": u1, "z": z, "p": p}

# ---------------------------------------------------------------- k 组检验


def anova_classic(groups):
    gs = [clean(g) for g in groups]
    k = len(gs)
    ni = [len(g) for g in gs]
    N = sum(ni)
    ms = [mean(g) for g in gs]
    gm = sum(m * n for m, n in zip(ms, ni)) / N
    ssb = sum(n * (m - gm) ** 2 for n, m in zip(ni, ms))
    ssw = sum(sum((x - m) ** 2 for x in g) for g, m in zip(gs, ms))
    df1, df2 = k - 1, N - k
    if df2 <= 0 or ssw <= 0:
        return {"statistic": None, "df": [df1, df2], "p": None,
                "ss_between": ssb, "ss_within": ssw, "ss_total": ssb + ssw}
    F = (ssb / df1) / (ssw / df2)
    return {"statistic": F, "df": [df1, df2], "p": 1.0 - f_cdf(F, df1, df2),
            "ss_between": ssb, "ss_within": ssw, "ss_total": ssb + ssw}


def anova_welch(groups):
    """Welch(1951) 异方差 ANOVA。Λ = Σ(1−w_i/W)²/(n_i−1)；
    F' = [Σw_i(x̄_i−x̄_w)²/(k−1)] / [1 + 2(k−2)Λ/(k²−1)]；df2 = (k²−1)/(3Λ)。"""
    gs = [clean(g) for g in groups]
    k = len(gs)
    ni = [len(g) for g in gs]
    ms = [mean(g) for g in gs]
    vs = [var(g) for g in gs]
    if any(v <= 0 for v in vs):
        return {"statistic": None, "df": [k - 1, None], "p": None}
    w = [n / v for n, v in zip(ni, vs)]
    W = sum(w)
    xw = sum(wi * m for wi, m in zip(w, ms)) / W
    lam = sum((1.0 - wi / W) ** 2 / (n - 1) for wi, n in zip(w, ni))
    df1 = k - 1
    df2 = (k * k - 1) / (3.0 * lam) if lam > 0 else float("inf")
    F = (sum(wi * (m - xw) ** 2 for wi, m in zip(w, ms)) / df1) / \
        (1.0 + 2.0 * (k - 2) * lam / (k * k - 1))
    return {"statistic": F, "df": [df1, df2], "p": 1.0 - f_cdf(F, df1, df2)}


def kruskal(groups):
    """Kruskal–Wallis H，tie 校正。返回 dict(H, df, p)。"""
    gs = [clean(g) for g in groups]
    k = len(gs)
    ni = [len(g) for g in gs]
    N = sum(ni)
    pooled = [x for g in gs for x in g]
    r = ranks_average(pooled)
    rs, pos = [], 0
    for n in ni:
        rs.append(sum(r[pos:pos + n]))
        pos += n
    H = 12.0 / (N * (N + 1)) * sum(R * R / n for R, n in zip(rs, ni)) - 3.0 * (N + 1)
    c = 1.0 - _tie_sum(pooled) / (N ** 3 - N)
    if c <= 0:
        return {"statistic": None, "df": k - 1, "p": None}
    H = H / c
    return {"statistic": H, "df": k - 1, "p": 1.0 - chi2_cdf(H, k - 1)}

# ---------------------------------------------------------------- 效应量


def hedges_g(x, y):
    """Hedges g，精确小样本校正 J(ν)=Γ(ν/2)/(√(ν/2)Γ((ν−1)/2))，ν=n1+n2−2。
    方向：mean(x) − mean(y)。"""
    n1, n2 = len(x), len(y)
    nu = n1 + n2 - 2
    sp = math.sqrt(((n1 - 1) * var(x) + (n2 - 1) * var(y)) / nu)
    if sp == 0:
        return None
    d = (mean(x) - mean(y)) / sp
    J = math.exp(math.lgamma(nu / 2.0) - math.lgamma((nu - 1) / 2.0)
                 - 0.5 * math.log(nu / 2.0))
    return J * d


def rank_biserial_from_u(u1, n1, n2):
    """r = 2U1/(n1n2) − 1；正值表示第一组取值倾向更大。"""
    return 2.0 * u1 / (n1 * n2) - 1.0


def eta_omega(groups):
    """返回 (η², ω²)，基于经典 ANOVA 的 SS 口径：
    η²=SSb/SSt；ω²=(SSb−(k−1)MSw)/(SSt+MSw)。"""
    a = anova_classic(groups)
    ssb, ssw, sst = a["ss_between"], a["ss_within"], a["ss_total"]
    k = len(groups)
    if sst <= 0 or ssw <= 0:
        return None, None
    msw = ssw / (sum(len(clean(g)) for g in groups) - k)
    eta2 = ssb / sst
    omega2 = (ssb - (k - 1) * msw) / (sst + msw)
    return eta2, omega2


def epsilon_squared_kw(H, n, k):
    """KW 的 ε² = (H−k+1)/(n−k)。"""
    if H is None or n <= k:
        return None
    return (H - k + 1) / (n - k)

# ---------------------------------------------------------------- 置信区间


def bootstrap_hedges_g(x, y, B=BOOT_B, seed=BOOT_SEED, alpha=0.05):
    """百分位 bootstrap CI for Hedges g。
    确定性协议（审计按此重算）：rng=random.Random(seed)；每个 replicate 依次
    对 group1、group2 用 rng.randrange(n) 有放回抽 n 个；无法计算（合并 sd=0）
    的 replicate 跳过；有效 replicate 数 m；排序后
    lo=s[floor(α/2·m)]，hi=s[ceil((1−α/2)·m)−1]（下标截断到合法范围）。"""
    rng = random.Random(seed)
    stats = []
    n1, n2 = len(x), len(y)
    for _ in range(B):
        bx = [x[rng.randrange(n1)] for _ in range(n1)]
        by = [y[rng.randrange(n2)] for _ in range(n2)]
        g = hedges_g(bx, by)
        if g is not None and g == g:
            stats.append(g)
    m = len(stats)
    if m < B // 2:
        return None, None, m
    stats.sort()
    lo_i = min(m - 1, max(0, int(math.floor((alpha / 2.0) * m))))
    hi_i = min(m - 1, max(0, int(math.ceil((1 - alpha / 2.0) * m)) - 1))
    return stats[lo_i], stats[hi_i], m


def welch_mean_diff_ci(x, y, alpha=0.05):
    """均值差 Welch CI。返回 (diff, lo, hi, df)。"""
    n1, n2 = len(x), len(y)
    v1, v2 = var(x), var(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        return None, None, None, None
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    tcrit = t_ppf(1.0 - alpha / 2.0, df)
    d = mean(x) - mean(y)
    half = tcrit * math.sqrt(se2)
    return d, d - half, d + half, df


def hodges_lehmann(x, y, alpha=0.05):
    """两两差中位数（位置位移估计）+ 大样本分位区间。
    返回 (est, lo, hi)。方向：x − y。"""
    diffs = sorted(a - b for a in x for b in y)
    m = len(diffs)
    if m == 0:
        return None, None, None
    est = median(diffs)
    z = norm_ppf(1.0 - alpha / 2.0)
    k = int(math.floor(0.5 * m - z * math.sqrt(m / 4.0)))
    k = max(0, min(m - 1, k))
    return est, diffs[k], diffs[m - 1 - k]

# ---------------------------------------------------------------- 多重比较


def holm(pvals):
    """Holm step-down。输入 p 列表，输出等长校正 p（保持原顺序）。
    p_adj(i) = max over rank≤rank(i) of min(1, (m−rank)·p_(rank))。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [None] * m
    running = 0.0
    for rank, idx in enumerate(order):
        val = min(1.0, (m - rank) * pvals[idx])
        running = max(running, val)
        adj[idx] = running
    return adj
