#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statcore_e — stats-run-gates 独立统计核心（纯标准库，零第三方依赖）。

本模块为 bundle-e 独立编写，不引用任何其他 bundle 的文件。
分布函数基于正则化不完全 Beta/Gamma（连分式 + 级数，Numerical Recipes 思路）；
本机可用 scipy 交叉校验（pipeline 在 scipy 存在时自动做抽样比对并记录，缺失时静默跳过）。

确定性约定（见 references/determinism.md）：
- 所有 bootstrap 使用 random.Random(20240501)，每个结局变量独立播种；
- 输出 JSON 一律 sort_keys=True；任何集合迭代前先排序；
- p 值显示规则：p < 0.0001 记为 "p < 0.0001"，否则保留 4 位小数。
"""
import math
import random

BOOTSTRAP_SEED = 20240501
BOOTSTRAP_B = 2000
MISSING_TOKENS = {"", "NA", "N/A", "NaN", "null", "-", "nan"}
STATUS_ENUM = ("complete", "partial", "failed")


# ------------------------------------------------------------- 基础量
def vmean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def vvar(xs, sample=True):
    n = len(xs)
    if n < (2 if sample else 1):
        return float("nan")
    m = vmean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - 1 if sample else n)


def vsd(xs, sample=True):
    v = vvar(xs, sample)
    return math.sqrt(v) if v == v else v


def vmedian(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    h = n // 2
    return s[h] if n % 2 else (s[h - 1] + s[h]) / 2.0


def vquantile(xs, q):
    """线性插值分位数（R type-7 口径）。"""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    if n == 1:
        return s[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return s[lo] + (pos - lo) * (s[hi] - s[lo])


def vskew(xs):
    n = len(xs)
    if n < 3:
        return float("nan")
    m = vmean(xs)
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0
    m3 = sum((x - m) ** 3 for x in xs) / n
    return m3 / (m2 ** 1.5)


def vkurt_excess(xs):
    n = len(xs)
    if n < 4:
        return float("nan")
    m = vmean(xs)
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0
    m4 = sum((x - m) ** 4 for x in xs) / n
    return m4 / m2 ** 2 - 3.0


def describe_series(xs):
    """描述统计字典；n=0 返回 None。键序固定（输出时再 sort_keys）。"""
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {
        "n": len(xs),
        "mean": vmean(xs),
        "sd": vsd(xs),
        "median": vmedian(xs),
        "q1": vquantile(xs, 0.25),
        "q3": vquantile(xs, 0.75),
        "min": min(xs),
        "max": max(xs),
        "skewness": vskew(xs) if len(xs) >= 3 else None,
    }


def rank_average(xs):
    """平均秩（ties 取均值），1 起始。"""
    order = sorted(range(len(xs)), key=lambda i: (xs[i], i))
    ranks = [0.0] * len(xs)
    k = 0
    while k < len(order):
        j = k
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[k]]:
            j += 1
        avg = (k + j) / 2.0 + 1.0
        for t in range(k, j + 1):
            ranks[order[t]] = avg
        k = j + 1
    return ranks


def _tie_sum(vals):
    s = sorted(vals)
    tot = 0.0
    k = 0
    while k < len(s):
        j = k
        while j + 1 < len(s) and s[j + 1] == s[k]:
            j += 1
        t = j - k + 1
        if t > 1:
            tot += t ** 3 - t
        k = j + 1
    return tot


# ------------------------------------------------------------- 特殊函数
def _beta_cf(a, b, x):
    """不完全 Beta 的连分式部分（Lentz 口径）。"""
    MAXIT, EPS, TINY = 300, 3e-14, 1e-300
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
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def reg_beta(a, b, x):
    """正则化不完全 Beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _beta_cf(a, b, x) / a
    return 1.0 - bt * _beta_cf(b, a, 1.0 - x) / b


def _gamma_q(a, x):
    """正则化上不完全 Gamma Q(a,x)。"""
    if x < 0 or a <= 0:
        return float("nan")
    if x == 0:
        return 1.0
    if x < a + 1.0:
        ap = a
        term = 1.0 / a
        s = term
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            s += term
            if abs(term) < abs(s) * 3e-14:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b = x + 1.0 - a
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1.0) < 3e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


# ------------------------------------------------------------- 分布函数
def cdf_t(t, df):
    x = df / (df + t * t)
    ib = reg_beta(df / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t >= 0 else 0.5 * ib


def cdf_f(f, d1, d2):
    if f <= 0:
        return 0.0
    return reg_beta(d1 / 2.0, d2 / 2.0, d1 * f / (d1 * f + d2))


def cdf_chi2(x, df):
    if x <= 0:
        return 0.0
    return 1.0 - _gamma_q(df / 2.0, x / 2.0)


def cdf_norm(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _ppf_bisect(cdf, p, lo, hi, args):
    if p <= 0:
        return lo
    if p >= 1:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if cdf(mid, *args) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ppf_t(p, df):
    return _ppf_bisect(cdf_t, p, -1e7, 1e7, (df,))


def ppf_norm(p):
    if p <= 0:
        return -1e12
    if p >= 1:
        return 1e12
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if cdf_norm(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ------------------------------------------------------------- 假设检验
def dagostino_k2(xs):
    """D'Agostino-Pearson K^2 正态性检验。n<8 返回 (None, None)（调用方按非正态保守处理）。"""
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n < 8:
        return None, None
    g1 = vskew(xs)
    g2 = vkurt_excess(xs) + 3.0
    y = g1 * math.sqrt(((n + 1) * (n + 3)) / (6.0 * (n - 2)))
    b2 = 3.0 * (n ** 2 + 27 * n - 70) * (n + 1) * (n + 3) / \
        ((n - 2.0) * (n + 5) * (n + 7) * (n + 9))
    w2 = -1.0 + math.sqrt(2.0 * (b2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    a = math.sqrt(2.0 / (w2 - 1.0))
    z1 = delta * math.log(y / a + math.sqrt((y / a) ** 2 + 1.0))
    e2 = 3.0 * (n - 1) / (n + 1)
    v2 = 24.0 * n * (n - 2) * (n - 3) / ((n + 1.0) ** 2 * (n + 3) * (n + 5))
    x2 = (g2 - e2) / math.sqrt(v2)
    b = (6.0 * (n * n - 5 * n + 2)) / ((n + 7.0) * (n + 9.0)) * \
        math.sqrt((6.0 * (n + 3) * (n + 5)) / (n * (n - 2) * (n - 3)))
    biga = 6.0 + 8.0 / b * (2.0 / b + math.sqrt(1.0 + 4.0 / (b * b)))
    if biga <= 4.0:
        return None, None
    denom = 1.0 + x2 * math.sqrt(2.0 / (biga - 4.0))
    if denom == 0.0:
        return None, None
    t2 = (1.0 if denom > 0 else -1.0) * (abs(1.0 - 2.0 / biga) / abs(denom)) ** (1.0 / 3.0)
    z2 = (1.0 - 2.0 / (9.0 * biga) - t2) / math.sqrt(2.0 / (9.0 * biga))
    k2 = z1 * z1 + z2 * z2
    return k2, 1.0 - cdf_chi2(k2, 2)


def levene_median(groups):
    """Levene/Brown-Forsythe（median 中心）。返回 (W, df1, df2, p)。"""
    k = len(groups)
    zs = [[abs(x - vmedian(g)) for x in g] for g in groups]
    ni = [len(z) for z in zs]
    n_all = sum(ni)
    if k < 2 or n_all <= k:
        return None, None, None, None
    zbars = [vmean(z) for z in zs]
    zbar = sum(sum(z) for z in zs) / n_all
    num = sum(n * (zb - zbar) ** 2 for n, zb in zip(ni, zbars))
    den = sum(sum((z - zb) ** 2 for z in zz) for zz, zb in zip(zs, zbars))
    df1, df2 = k - 1, n_all - k
    if den <= 0:
        return 0.0, df1, df2, 1.0
    w = (n_all - k) * num / (df1 * den)
    return w, df1, df2, 1.0 - cdf_f(w, df1, df2)


def t_student(x, y):
    n1, n2 = len(x), len(y)
    m1, m2 = vmean(x), vmean(y)
    v1, v2 = vvar(x), vvar(y)
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    se = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    df = n1 + n2 - 2
    if se == 0:
        return (0.0 if m1 == m2 else math.copysign(1e12, m1 - m2)), df, (1.0 if m1 == m2 else 0.0)
    t = (m1 - m2) / se
    return t, df, 2.0 * (1.0 - cdf_t(abs(t), df))


def t_welch(x, y):
    n1, n2 = len(x), len(y)
    m1, m2 = vmean(x), vmean(y)
    v1, v2 = vvar(x), vvar(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        return (0.0 if m1 == m2 else math.copysign(1e12, m1 - m2)), 1.0, (1.0 if m1 == m2 else 0.0)
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t = (m1 - m2) / math.sqrt(se2)
    return t, df, 2.0 * (1.0 - cdf_t(abs(t), df))


def u_mannwhitney(x, y):
    """Mann-Whitney U（tie 校正正态近似）。返回 (U, z, p)。"""
    n1, n2 = len(x), len(y)
    comb = list(x) + list(y)
    r = rank_average(comb)
    r1 = sum(r[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u = min(u1, n1 * n2 - u1)
    tie = _tie_sum(comb)
    mu = n1 * n2 / 2.0
    sig2 = n1 * n2 / 12.0 * ((n1 + n2 + 1) - tie / ((n1 + n2) * (n1 + n2 - 1)))
    if sig2 <= 0:
        return u, 0.0, 1.0
    z = (u - mu) / math.sqrt(sig2)
    return u, z, 2.0 * (1.0 - cdf_norm(abs(z)))


def f_anova(groups):
    """经典单因素 ANOVA。返回 (F, df1, df2, p, ssb, ssw)。"""
    k = len(groups)
    ni = [len(g) for g in groups]
    n_all = sum(ni)
    means = [vmean(g) for g in groups]
    gm = sum(m * n for m, n in zip(means, ni)) / n_all
    ssb = sum(n * (m - gm) ** 2 for n, m in zip(ni, means))
    ssw = sum(sum((x - m) ** 2 for x in g) for g, m in zip(groups, means))
    df1, df2 = k - 1, n_all - k
    if df2 <= 0 or ssw <= 0:
        return None, df1, df2, None, ssb, ssw
    f = (ssb / df1) / (ssw / df2)
    return f, df1, df2, 1.0 - cdf_f(f, df1, df2), ssb, ssw


def f_welch_anova(groups):
    """Welch ANOVA（方差不齐）。返回 (F, df1, df2, p)。"""
    k = len(groups)
    ni = [len(g) for g in groups]
    means = [vmean(g) for g in groups]
    vi = [vvar(g) for g in groups]
    wi = [n / v for n, v in zip(ni, vi)]
    sw = sum(wi)
    xw = sum(w * m for w, m in zip(wi, means)) / sw
    num = sum(w * (m - xw) ** 2 for w, m in zip(wi, means)) / (k - 1)
    s_corr = sum((1.0 - w / sw) ** 2 / (n - 1) for w, n in zip(wi, ni))
    df1 = k - 1
    df2 = (k * k - 1) / (3.0 * s_corr) if s_corr > 0 else 1e9
    f = num / (1.0 + 2.0 * (k - 2) * s_corr / (k * k - 1))
    return f, df1, df2, 1.0 - cdf_f(f, df1, df2)


def h_kruskal(groups):
    """Kruskal-Wallis H（tie 校正）。返回 (H, df, p)。"""
    k = len(groups)
    comb = [x for g in groups for x in g]
    r = rank_average(comb)
    ni = [len(g) for g in groups]
    n_all = sum(ni)
    pos = 0
    rsum = []
    for n in ni:
        rsum.append(sum(r[pos:pos + n]))
        pos += n
    h = 12.0 / (n_all * (n_all + 1)) * sum(rs ** 2 / n for rs, n in zip(rsum, ni)) - 3 * (n_all + 1)
    c = 1.0 - _tie_sum(comb) / (n_all ** 3 - n_all)
    if c <= 0:
        return None, k - 1, None
    h = h / c
    return h, k - 1, 1.0 - cdf_chi2(h, k - 1)


# ------------------------------------------------------------- 效应量
def hedges_g(x, y):
    """Hedges g = J * Cohen d（x 组减 y 组方向）。任一组方差为 0 且均值不等返回 None。"""
    n1, n2 = len(x), len(y)
    sp2 = ((n1 - 1) * vvar(x) + (n2 - 1) * vvar(y)) / (n1 + n2 - 2)
    if sp2 <= 0:
        return None
    d = (vmean(x) - vmean(y)) / math.sqrt(sp2)
    j = 1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)
    return j * d


def rank_biserial_from_u(x, y):
    n1, n2 = len(x), len(y)
    u, _, _ = u_mannwhitney(x, y)
    return 1.0 - 2.0 * u / (n1 * n2)


def eta_squared(groups):
    _, _, _, _, ssb, ssw = f_anova(groups)
    sst = ssb + ssw
    return ssb / sst if sst > 0 else None


def omega_squared(groups):
    f, df1, df2, _, _, _ = f_anova(groups)
    if f is None:
        return None
    return (df1 * (f - 1)) / (df1 * f + df2 + 1)


def epsilon_squared_kw(groups):
    h, df, _ = h_kruskal(groups)
    n_all = sum(len(g) for g in groups)
    if h is None or n_all - len(groups) <= 0:
        return None
    return (h - len(groups) + 1) / (n_all - len(groups))


# ------------------------------------------------------------- 置信区间
def bootstrap_percentile(stat_fn, samples, B=BOOTSTRAP_B, alpha=0.05, seed=BOOTSTRAP_SEED):
    """分层百分位 bootstrap CI：每组内独立有放回重抽样。
    返回 (lo, hi, B_used)；有效重抽样不足一半返回 (None, None, n_valid)。"""
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        try:
            res = [[a[rng.randrange(len(a))] for _ in range(len(a))] for a in samples]
            s = stat_fn(*res)
            if s is not None and s == s and math.isfinite(s):
                vals.append(s)
        except Exception:
            continue
    if len(vals) < B // 2:
        return None, None, len(vals)
    vals.sort()
    lo = vals[int((alpha / 2.0) * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2.0) * len(vals)))]
    return lo, hi, len(vals)


def welch_mean_diff_ci(x, y, alpha=0.05):
    """均值差（x - y）Welch CI。返回 (lo, hi, df)。"""
    n1, n2 = len(x), len(y)
    v1, v2 = vvar(x), vvar(y)
    se2 = v1 / n1 + v2 / n2
    if se2 == 0:
        return None, None, None
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    tcrit = ppf_t(1 - alpha / 2.0, df)
    diff = vmean(x) - vmean(y)
    return diff - tcrit * math.sqrt(se2), diff + tcrit * math.sqrt(se2), df


def hodges_lehmann_diff(x, y):
    """Hodges-Lehmann 中位数差（x - y）及正态近似区间。返回 (est, lo, hi)。"""
    diffs = sorted(a - b for a in x for b in y)
    n = len(diffs)
    if n == 0:
        return None, None, None
    est = vmedian(diffs)
    k = int(math.floor(0.5 * n - ppf_norm(0.975) * math.sqrt(n / 4.0)))
    k = max(0, min(n - 1, k))
    return est, diffs[k], diffs[n - 1 - k]


# ------------------------------------------------------------- 多重比较
def holm_adjust(pvals):
    """Holm 逐步校正，保持原顺序；None 原样保留。"""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: (pvals[i] is None, pvals[i] if pvals[i] is not None else 0.0))
    adj = [None] * m
    run_max = 0.0
    for rank, idx in enumerate(order):
        p = pvals[idx]
        if p is None:
            continue
        run_max = max(run_max, min(1.0, (m - rank) * p))
        adj[idx] = run_max
    return adj


# ------------------------------------------------------------- 显示格式（G6 门检共用）
def fmt_p(p):
    """p 值规范写法：p < 0.0001 或 p = 0.0123（4 位）。"""
    if p is None:
        return "p = NA"
    if p < 0.0001:
        return "p < 0.0001"
    return "p = %.4f" % p


def fmt_effect(kind, v):
    """效应量规范写法：kind = 0.1234（4 位）。"""
    if v is None:
        return "%s = NA" % kind
    return "%s = %.4f" % (kind, v)


def fmt_fixed(v, nd=4):
    if v is None:
        return "NA"
    return ("%.*f" % (nd, v))


EFFECT_MAGNITUDE = {
    "hedges_g": [(0.2, "可忽略"), (0.5, "小"), (0.8, "中"), (float("inf"), "大")],
    "eta2": [(0.01, "可忽略"), (0.06, "小"), (0.14, "中"), (float("inf"), "大")],
    "omega2": [(0.01, "可忽略"), (0.06, "小"), (0.14, "中"), (float("inf"), "大")],
    "eps2": [(0.01, "可忽略"), (0.06, "小"), (0.14, "中"), (float("inf"), "大")],
    "rank_biserial": [(0.1, "可忽略"), (0.3, "小"), (0.5, "中"), (float("inf"), "大")],
}


def effect_magnitude(kind, v):
    if v is None:
        return "不可判定"
    a = abs(v)
    for thr, lab in EFFECT_MAGNITUDE.get(kind, []):
        if a < thr:
            return lab
    return "不可判定"
