#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stattool.py — 统计计算与前提裁决工具（stat-assumption-tribunal）

仅使用 Python 3.9+ 标准库。所有推断性结论必须通过显式前提检验；
前提不满足时自动改判（reroute）到非参数备选并说明理由；
每个描述统计量都附带显式口径（ddof、四分位方法、缺失策略、去重策略）。

子命令：
  descriptive    描述统计（含双 ddof、双四分位方法、偏度/峰度、均值 95% CI）
  compare        组间比较裁决（正态性 + 方差齐性 -> t 检验 / Welch / MWU / ANOVA / KW）
  corr           Pearson + Spearman 相关（Pearson 附 t 检验 p 值）
  verify-claims  按本工具口径独立复算 claims.json 中的断言并判定 PASS/FAIL
  selftest       特殊函数数值自检

退出码约定（compare）：0 = 按原请求的参数检验执行；2 = 已改判非参数（劝告性，非失败）；
1 = 无法计算（原因写入 JSON）。其余子命令：0 成功，1 失败/存在 FAIL 断言。
"""

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL_NAME = "stattool"
TOOL_VERSION = "1.0.0"

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "."}

MISSING_POLICY = (
    "drop-nulls-pairwise: 目标列取值为空或属于缺失标记 "
    "{'', 'NA', 'N/A', 'NaN', 'null', 'None', '.'}（大小写不敏感）的行被剔除并计入 n_missing；"
    "其余无法解析为浮点数的取值不静默转换，直接报错退出（exit 1）。"
)
DEDUP_POLICY = (
    "keep-all: 不去重；完全重复的行被保留并计入统计，n_exact_duplicate_rows 单独报告，"
    "是否去重由分析者在结论中显式声明。"
)

FORMULAS = {
    "std_var": "std(ddof=0)=sqrt(sum((x-mean)^2)/n); std(ddof=1)=sqrt(sum((x-mean)^2)/(n-1)); variance 同理。",
    "quartiles": "statistics.quantiles(n=4)：method='inclusive' 与 method='exclusive' 并列报告，标签区分。",
    "skewness": "g1 = m3 / m2^1.5（矩估计，m2/m3 为二阶/三阶中心矩，未做自由度校正）。",
    "excess_kurtosis": "g2 = m4 / m2^2 - 3（超出峰度，正态总体期望约 -6/(n+1)）。",
    "se": "SE = std(ddof=1) / sqrt(n)。",
    "ci95_mean": "mean +/- t_{0.975, n-1} * SE，t 分位数由内置 t 分布 CDF 二分求逆。",
    "dagostino_k2": (
        "D'Agostino-Pearson K^2：对偏度 g1 与超出峰度 g2 分别做正态化变换得 Z1、Z2，"
        "K^2 = Z1^2 + Z2^2，p 值取 chi2(df=2) 上尾。"
    ),
    "brown_forsythe": (
        "Brown-Forsythe：z_ij = |x_ij - median_j|，对 z 做单因素方差分析，"
        "F 服从 F(k-1, N-k)。"
    ),
    "welch_t": "t = (m1-m2)/sqrt(s1^2/n1 + s2^2/n2)，df 取 Welch-Satterthwaite 近似。",
    "student_t": "t = (m1-m2)/(s_p*sqrt(1/n1+1/n2))，s_p 为合并标准差(ddof=1)，df = n1+n2-2。",
    "mann_whitney": (
        "U 基于全体混合秩（并列取平均秩）；var(U) = n1*n2/12 * ((N+1) - sum(t^3-t)/(N*(N-1)))，"
        "正态近似含 0.5 连续性校正，双侧 p；rank_biserial = 2*U1/(n1*n2) - 1，"
        "U1 为按标签排序第一组的 U，正值表示第一组取值偏大。"
    ),
    "kruskal_wallis": "H = 12/(N(N+1))*sum(R_j^2/n_j) - 3(N+1)，并列校正 C = 1 - sum(t^3-t)/(N^3-N)，H' = H/C，p 取 chi2(df=k-1) 上尾。",
    "pearson": "r = cov(x,y)/(sx*sy)（矩估计）；t = r*sqrt((n-2)/(1-r^2))，df = n-2，双侧 p。",
    "spearman": "对 x、y 分别取平均秩后计算 Pearson r。",
}


# ---------------------------------------------------------------------------
# 特殊函数（全部自行实现，仅依赖 math）
# ---------------------------------------------------------------------------

def norm_cdf(x):
    """标准正态 CDF，基于 math.erf。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_sf(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def _betacf(a, b, x):
    """不完全 beta 的连分式（Numerical Recipes 6.4，Lentz 算法）。"""
    maxit, eps, fpmin = 300, 3.0e-15, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    """正则化不完全 beta 函数 I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    """Student-t CDF。"""
    x = df / (df + t * t)
    ib = betai(df / 2.0, 0.5, x)
    return 1.0 - 0.5 * ib if t >= 0.0 else 0.5 * ib


def t_p_two_sided(t, df):
    """双侧 p：P(|T| >= |t|) = I_{df/(df+t^2)}(df/2, 1/2)。"""
    if df <= 0:
        return float("nan")
    return betai(df / 2.0, 0.5, df / (df + t * t))


def f_cdf(f, d1, d2):
    """F 分布 CDF。"""
    if f <= 0.0:
        return 0.0
    return betai(d1 / 2.0, d2 / 2.0, (d1 * f) / (d1 * f + d2))


def f_sf(f, d1, d2):
    if f <= 0.0:
        return 1.0
    # 上尾 = I_{d2/(d2+d1*f)}(d2/2, d1/2)，避免近 1 处的相消
    return betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def _gammainc_p_series(a, x):
    ap = a
    s = 1.0 / a
    delta = s
    for _ in range(1000):
        ap += 1.0
        delta *= x / ap
        s += delta
        if abs(delta) < abs(s) * 3.0e-15:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gammainc_q_cf(a, x):
    fpmin = 1.0e-300
    b = x + 1.0 - a
    c = 1.0 / fpmin
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < fpmin:
            d = fpmin
        c = b + an / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3.0e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammainc_p(a, x):
    """正则化下不完全伽马 P(a,x)。"""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        return _gammainc_p_series(a, x)
    return 1.0 - _gammainc_q_cf(a, x)


def gammainc_q(a, x):
    """正则化上不完全伽马 Q(a,x) = 1 - P(a,x)。"""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gammainc_p_series(a, x)
    return _gammainc_q_cf(a, x)


def chi2_cdf(x, k):
    return gammainc_p(k / 2.0, x / 2.0)


def chi2_sf(x, k):
    return gammainc_q(k / 2.0, x / 2.0)


def t_ppf(p, df):
    """t 分布分位数，对 t_cdf 二分求逆。"""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    lo, hi = -1.0, 1.0
    while t_cdf(lo, df) > p:
        lo *= 2.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# 基础统计量
# ---------------------------------------------------------------------------

def rankdata(vals):
    """平均秩（从 1 起），返回 (ranks, tie_counts)。"""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    ties = []
    i = 0
    n = len(vals)
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        if j > i:
            ties.append(j - i + 1)
        i = j + 1
    return ranks, ties


def moments(xs):
    n = len(xs)
    mean = statistics.fmean(xs)
    m2 = statistics.fmean([(x - mean) ** 2 for x in xs])
    m3 = statistics.fmean([(x - mean) ** 3 for x in xs])
    m4 = statistics.fmean([(x - mean) ** 4 for x in xs])
    return mean, m2, m3, m4


def skew_kurt(xs):
    """矩估计偏度 g1 与超出峰度 g2；零方差返回 (0.0, 0.0, True)。"""
    mean, m2, m3, m4 = moments(xs)
    if m2 <= 0.0:
        return 0.0, 0.0, True
    g1 = m3 / (m2 ** 1.5)
    g2 = m4 / (m2 * m2) - 3.0
    return g1, g2, False


def dagostino_k2(xs):
    """D'Agostino-Pearson K^2 正态性检验；要求 n >= 8。零方差返回 None。"""
    n = len(xs)
    if n < 8:
        raise ValueError("dagostino_k2 requires n>=8")
    g1, g2, zero_var = skew_kurt(xs)
    if zero_var:
        return None
    nf = float(n)
    # 偏度正态化
    y = g1 * math.sqrt((nf + 1.0) * (nf + 3.0) / (6.0 * (nf - 2.0)))
    b2 = (3.0 * (nf * nf + 27.0 * nf - 70.0) * (nf + 1.0) * (nf + 3.0)
          / ((nf - 2.0) * (nf + 5.0) * (nf + 7.0) * (nf + 9.0)))
    w2 = -1.0 + math.sqrt(2.0 * (b2 - 1.0))
    delta = 1.0 / math.sqrt(0.5 * math.log(w2))
    alpha = math.sqrt(2.0 / (w2 - 1.0))
    z1 = delta * math.asinh(y / alpha)
    # 峰度正态化
    eg2 = -6.0 / (nf + 1.0)
    varg2 = (24.0 * nf * (nf - 2.0) * (nf - 3.0)
             / ((nf + 1.0) ** 2 * (nf + 3.0) * (nf + 5.0)))
    x = (g2 - eg2) / math.sqrt(varg2)
    sb1 = (6.0 * (nf * nf - 5.0 * nf + 2.0) / ((nf + 7.0) * (nf + 9.0))
           * math.sqrt(6.0 * (nf + 3.0) * (nf + 5.0) / (nf * (nf - 2.0) * (nf - 3.0))))
    a = 6.0 + (8.0 / sb1) * (2.0 / sb1 + math.sqrt(1.0 + 4.0 / (sb1 * sb1)))
    denom = 1.0 + x * math.sqrt(2.0 / (a - 4.0))
    if denom <= 0.0:
        # 有符号立方根保护
        ratio = (1.0 - 2.0 / a) / denom
        cub = -((-ratio) ** (1.0 / 3.0)) if ratio < 0 else ratio ** (1.0 / 3.0)
    else:
        cub = ((1.0 - 2.0 / a) / denom) ** (1.0 / 3.0)
    z2 = ((1.0 - 2.0 / (9.0 * a)) - cub) / math.sqrt(2.0 / (9.0 * a))
    k2 = z1 * z1 + z2 * z2
    p = chi2_sf(k2, 2.0)
    return {"z1_skew": z1, "z2_kurt": z2, "k2": k2, "p": p, "g1": g1, "g2": g2}


def desc_block(xs):
    """单样本描述统计块，口径全部显式标注。"""
    n = len(xs)
    mean = statistics.fmean(xs)
    var0 = statistics.pvariance(xs)
    var1 = statistics.variance(xs) if n >= 2 else None
    std0 = math.sqrt(var0)
    std1 = math.sqrt(var1) if var1 is not None else None
    g1, g2, zero_var = skew_kurt(xs)
    q_inc = statistics.quantiles(xs, n=4, method="inclusive")
    q_exc = statistics.quantiles(xs, n=4, method="exclusive") if n >= 4 else None
    se = std1 / math.sqrt(n) if std1 is not None else None
    tcrit = t_ppf(0.975, n - 1) if n >= 2 else None
    ci = [mean - tcrit * se, mean + tcrit * se] if se is not None else None
    return {
        "n": n,
        "mean": mean,
        "median": statistics.median(xs),
        "std_ddof0": std0,
        "std_ddof1": std1,
        "variance_ddof0": var0,
        "variance_ddof1": var1,
        "min": min(xs),
        "max": max(xs),
        "q1_inclusive": q_inc[0],
        "q2_inclusive": q_inc[1],
        "q3_inclusive": q_inc[2],
        "q1_exclusive": q_exc[0] if q_exc else None,
        "q2_exclusive": q_exc[1] if q_exc else None,
        "q3_exclusive": q_exc[2] if q_exc else None,
        "skewness_moment_g1": g1,
        "excess_kurtosis_moment_g2": g2,
        "zero_variance": zero_var,
        "se_mean": se,
        "ci95_mean_t": ci,
    }


# ---------------------------------------------------------------------------
# 组间检验
# ---------------------------------------------------------------------------

def welch_ttest(g1, g2):
    n1, n2 = len(g1), len(g2)
    m1, m2 = statistics.fmean(g1), statistics.fmean(g2)
    v1, v2 = statistics.variance(g1), statistics.variance(g2)
    se2 = v1 / n1 + v2 / n2
    if se2 <= 0.0:
        return None
    t = (m1 - m2) / math.sqrt(se2)
    df = se2 * se2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p = t_p_two_sided(t, df)
    diff = m1 - m2
    tcrit = t_ppf(0.975, df)
    ci = [diff - tcrit * math.sqrt(se2), diff + tcrit * math.sqrt(se2)]
    return {"t": t, "df": df, "p": p, "mean_diff": diff, "ci95_diff": ci}


def student_ttest(g1, g2):
    n1, n2 = len(g1), len(g2)
    m1, m2 = statistics.fmean(g1), statistics.fmean(g2)
    v1, v2 = statistics.variance(g1), statistics.variance(g2)
    df = n1 + n2 - 2
    sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / df
    if sp2 <= 0.0:
        return None
    se = math.sqrt(sp2 * (1.0 / n1 + 1.0 / n2))
    t = (m1 - m2) / se
    p = t_p_two_sided(t, df)
    diff = m1 - m2
    tcrit = t_ppf(0.975, df)
    ci = [diff - tcrit * se, diff + tcrit * se]
    d = diff / math.sqrt(sp2)
    return {"t": t, "df": df, "p": p, "mean_diff": diff, "ci95_diff": ci, "cohens_d": d}


def mann_whitney_u(g1, g2):
    """精确并列校正的正态近似（含 0.5 连续性校正），双侧 p。"""
    n1, n2 = len(g1), len(g2)
    combined = g1 + g2
    n = n1 + n2
    ranks, ties = rankdata(combined)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u_stat = min(u1, u2)
    tie_term = sum(t ** 3 - t for t in ties)
    var_u = (n1 * n2 / 12.0) * ((n + 1.0) - tie_term / (n * (n - 1.0)))
    if var_u <= 0.0:
        return None
    mu = n1 * n2 / 2.0
    z = (u_stat - mu + 0.5) / math.sqrt(var_u)
    p = 2.0 * norm_sf(abs(z))
    rank_biserial = 2.0 * u1 / (n1 * n2) - 1.0
    return {
        "u_stat": u_stat, "u1": u1, "u2": u2, "z": z, "p": p,
        "rank_biserial": rank_biserial, "n_tie_groups": len(ties),
        "tie_correction_applied": bool(ties),
    }


def brown_forsythe(groups):
    """Levene 检验的中位数版本；groups = list of lists。返回 (F, df1, df2, p)。"""
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    zgroups = []
    for g in groups:
        med = statistics.median(g)
        zgroups.append([abs(x - med) for x in g])
    zmeans = [statistics.fmean(z) for z in zgroups]
    zgrand = statistics.fmean([z for zg in zgroups for z in zg])
    ssb = sum(len(zg) * (zm - zgrand) ** 2 for zg, zm in zip(zgroups, zmeans))
    ssw = sum(sum((z - zm) ** 2 for z in zg) for zg, zm in zip(zgroups, zmeans))
    df1, df2 = k - 1, n_total - k
    if ssw <= 0.0 or df2 <= 0:
        return None
    f = (ssb / df1) / (ssw / df2)
    p = f_sf(f, df1, df2)
    return {"f": f, "df1": df1, "df2": df2, "p": p}


def anova_oneway(groups):
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    means = [statistics.fmean(g) for g in groups]
    grand = statistics.fmean([x for g in groups for x in g])
    ssb = sum(len(g) * (m - grand) ** 2 for g, m in zip(groups, means))
    ssw = sum(sum((x - m) ** 2 for x in g) for g, m in zip(groups, means))
    sst = ssb + ssw
    df1, df2 = k - 1, n_total - k
    if ssw <= 0.0 or df2 <= 0:
        return None
    f = (ssb / df1) / (ssw / df2)
    p = f_sf(f, df1, df2)
    return {"f": f, "df1": df1, "df2": df2, "p": p,
            "eta_squared": ssb / sst if sst > 0 else None}


def kruskal_wallis(groups):
    k = len(groups)
    labels_n = [len(g) for g in groups]
    combined = [x for g in groups for x in g]
    n = len(combined)
    ranks, ties = rankdata(combined)
    h = 0.0
    pos = 0
    for ni in labels_n:
        rj = sum(ranks[pos:pos + ni])
        h += rj * rj / ni
        pos += ni
    h = 12.0 / (n * (n + 1.0)) * h - 3.0 * (n + 1.0)
    tie_term = sum(t ** 3 - t for t in ties)
    corr = 1.0 - tie_term / (n ** 3 - n) if n > 1 else 1.0
    if corr <= 0.0:
        return None
    h = h / corr
    p = chi2_sf(h, k - 1)
    eta2 = (h - k + 1.0) / (n - k) if n > k else None
    return {"h": h, "df": k - 1, "p": p, "eta_squared_h": eta2,
            "tie_correction_applied": bool(ties), "n_tie_groups": len(ties)}


def pearson_corr(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0.0 or syy <= 0.0:
        return None
    r = sxy / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    if abs(r) >= 1.0:
        t, p = None, 0.0
    else:
        t = r * math.sqrt((n - 2) / (1.0 - r * r))
        p = t_p_two_sided(t, n - 2)
    return {"r": r, "t": t, "df": n - 2, "p_two_sided": p}


def spearman_corr(xs, ys):
    rx, _ = rankdata(xs)
    ry, _ = rankdata(ys)
    res = pearson_corr(rx, ry)
    if res is None:
        return None
    return {"rho": res["r"], "t": res["t"], "df": res["df"], "p_two_sided": res["p_two_sided"]}


# ---------------------------------------------------------------------------
# I/O 与公共输出骨架
# ---------------------------------------------------------------------------

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rdr = csv.DictReader(fh)
        rows = list(rdr)
        fields = list(rdr.fieldnames or [])
    return fields, rows


def parse_value(token):
    """返回 float，或 None（缺失标记）；无法解析则抛 ValueError（不静默转换）。"""
    if token is None:
        return None
    s = str(token).strip()
    if s.lower() in MISSING_TOKENS:
        return None
    try:
        v = float(s)
    except ValueError:
        raise ValueError("non-numeric token %r is not a recognized missing marker" % s)
    if math.isnan(v) or math.isinf(v):
        return None if math.isnan(v) else (_ for _ in ()).throw(
            ValueError("infinite value not allowed"))
    return v


def envelope(command, csv_path=None, rows=None):
    env = {
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "python": sys.version.split()[0],
        "command": command,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
    }
    if csv_path is not None:
        env["input"] = {
            "csv": str(csv_path),
            "sha256": sha256_of(csv_path),
            "row_count": len(rows) if rows is not None else None,
        }
    return env


def emit(obj, out_path=None, exit_code=0):
    text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    print(text)
    return exit_code


def emit_error(command, reason, detail=None, out_path=None, csv_path=None, rows=None):
    env = envelope(command, csv_path, rows)
    env["status"] = "error"
    env["reason"] = reason
    if detail is not None:
        env["detail"] = detail
    return emit(env, out_path, exit_code=1)


def extract_column(rows, col, fields, group_col=None, group_filter=None):
    """抽取数值列；返回 (values, n_missing, kept_rows)。错误抛 ValueError。"""
    if col not in fields:
        raise ValueError("column %r not found; available: %s" % (col, ", ".join(fields)))
    if group_col is not None and group_col not in fields:
        raise ValueError("group column %r not found; available: %s"
                         % (group_col, ", ".join(fields)))
    vals, kept = [], []
    n_missing = 0
    for row in rows:
        if group_col is not None and group_filter is not None:
            gval = (row.get(group_col) or "").strip()
            if gval != group_filter:
                continue
        v = parse_value(row.get(col))
        if v is None:
            n_missing += 1
            continue
        vals.append(v)
        kept.append(row)
    return vals, n_missing, kept


def count_exact_duplicates(rows, fields):
    seen = {}
    for row in rows:
        key = tuple(row.get(f) for f in fields)
        seen[key] = seen.get(key, 0) + 1
    return sum(c - 1 for c in seen.values() if c > 1)


# ---------------------------------------------------------------------------
# 子命令：descriptive
# ---------------------------------------------------------------------------

def cmd_descriptive(args):
    command = "descriptive"
    try:
        fields, rows = read_table(args.csv)
    except OSError as e:
        return emit_error(command, "cannot read csv: %s" % e, out_path=args.out)
    try:
        if args.group:
            if args.group not in fields:
                raise ValueError("group column %r not found; available: %s"
                                 % (args.group, ", ".join(fields)))
            if args.col not in fields:
                raise ValueError("column %r not found; available: %s"
                                 % (args.col, ", ".join(fields)))
            group_labels = []
            n_missing_group = 0
            for row in rows:
                gv = (row.get(args.group) or "").strip()
                if gv.lower() in MISSING_TOKENS:
                    n_missing_group += 1
                    continue
                if gv not in group_labels:
                    group_labels.append(gv)
            group_labels = sorted(group_labels)
            env = envelope(command, args.csv, rows)
            env.update({
                "column": args.col,
                "group_column": args.group,
                "missing_policy": MISSING_POLICY,
                "dedup_policy": DEDUP_POLICY,
                "n_rows_total": len(rows),
                "n_exact_duplicate_rows": count_exact_duplicates(rows, fields),
                "n_missing_group_label": n_missing_group,
                "groups": {},
                "overall": None,
                "formulas": FORMULAS,
            })
            total_missing = 0
            all_vals = []
            for glabel in group_labels:
                vals, n_miss, _ = extract_column(rows, args.col, fields,
                                                 args.group, glabel)
                total_missing += n_miss
                all_vals.extend(vals)
                if len(vals) < 1:
                    env["groups"][glabel] = {"n": 0, "n_missing": n_miss,
                                             "note": "all values missing"}
                    continue
                if len(vals) < 3:
                    env["groups"][glabel] = {
                        "n": len(vals), "n_missing": n_miss,
                        "note": "n<3: only n/mean/range reported",
                        "mean": statistics.fmean(vals),
                        "min": min(vals), "max": max(vals),
                    }
                    continue
                blk = desc_block(vals)
                blk["n_missing"] = n_miss
                env["groups"][glabel] = blk
            env["n_missing_total"] = total_missing + n_missing_group
            if len(all_vals) >= 3:
                env["overall"] = desc_block(all_vals)
            elif all_vals:
                env["overall"] = {"n": len(all_vals), "mean": statistics.fmean(all_vals),
                                  "note": "n<3 overall"}
            return emit(env, args.out, 0)
        else:
            vals, n_missing, _ = extract_column(rows, args.col, fields)
            if not vals:
                return emit_error(command, "all values missing in column %r" % args.col,
                                  out_path=args.out, csv_path=args.csv, rows=rows)
            if len(vals) < 3:
                return emit_error(command,
                                  "n=%d < 3: descriptive statistics refused" % len(vals),
                                  out_path=args.out, csv_path=args.csv, rows=rows)
            if statistics.pvariance(vals) == 0.0:
                return emit_error(command,
                                  "constant column %r: zero variance" % args.col,
                                  out_path=args.out, csv_path=args.csv, rows=rows)
            env = envelope(command, args.csv, rows)
            env.update({
                "column": args.col,
                "group_column": None,
                "missing_policy": MISSING_POLICY,
                "dedup_policy": DEDUP_POLICY,
                "n_rows_total": len(rows),
                "n_missing": n_missing,
                "n_exact_duplicate_rows": count_exact_duplicates(rows, fields),
                "statistics": desc_block(vals),
                "formulas": FORMULAS,
            })
            return emit(env, args.out, 0)
    except ValueError as e:
        return emit_error(command, str(e), out_path=args.out,
                          csv_path=args.csv, rows=rows)


# ---------------------------------------------------------------------------
# 子命令：compare（前提裁决）
# ---------------------------------------------------------------------------

def normality_check(vals, alpha, small_n_rule_n=20):
    """返回 check 字典。规则：
    n>=8: D'Agostino-Pearson K^2，p<alpha 判不通过；
    n<small_n_rule_n: 附加 |g1|>1 或 |g2|>2 经验规则判不通过。
    """
    n = len(vals)
    g1, g2, zero_var = skew_kurt(vals)
    if zero_var:
        return {"name": "normality", "statistic": None, "df": None, "p": None,
                "pass": False, "threshold": "zero variance group",
                "note": "constant group cannot be normal in a usable sense"}
    if n < 8:
        return {"name": "normality", "statistic": None, "df": None, "p": None,
                "pass": None, "threshold": "n>=8 required for K^2",
                "note": "n=%d too small for D'Agostino-Pearson" % n,
                "g1": g1, "g2": g2}
    k2 = dagostino_k2(vals)
    rule_hit = (n < small_n_rule_n) and (abs(g1) > 1.0 or abs(g2) > 2.0)
    passed = (k2["p"] >= alpha) and not rule_hit
    return {
        "name": "normality_dagostino_pearson_k2",
        "statistic": k2["k2"], "df": 2, "p": k2["p"],
        "pass": passed,
        "threshold": "p >= alpha=%.4f AND (n>=%d OR (|g1|<=1 AND |g2|<=2))"
                     % (alpha, small_n_rule_n),
        "g1": g1, "g2": g2,
        "small_n_rule_triggered": rule_hit,
    }


def cmd_compare(args):
    command = "compare"
    try:
        fields, rows = read_table(args.csv)
    except OSError as e:
        return emit_error(command, "cannot read csv: %s" % e, out_path=args.out)
    alpha = args.alpha
    try:
        if args.group not in fields:
            raise ValueError("group column %r not found; available: %s"
                             % (args.group, ", ".join(fields)))
        if args.value not in fields:
            raise ValueError("value column %r not found; available: %s"
                             % (args.value, ", ".join(fields)))
        groups = {}
        n_missing_value = 0
        n_missing_group = 0
        for row in rows:
            gv = (row.get(args.group) or "").strip()
            if gv.lower() in MISSING_TOKENS:
                n_missing_group += 1
                continue
            v = parse_value(row.get(args.value))
            if v is None:
                n_missing_value += 1
                continue
            groups.setdefault(gv, []).append(v)
        labels = sorted(groups.keys())
        k = len(labels)
        if k < 2:
            return emit_error(command, "need >=2 groups, got %d" % k,
                              out_path=args.out, csv_path=args.csv, rows=rows)
        sizes = {lb: len(groups[lb]) for lb in labels}
        too_small = {lb: n for lb, n in sizes.items() if n < 3}
        if too_small:
            return emit_error(command,
                              "group(s) with n<3 cannot be compared: %s" % too_small,
                              out_path=args.out, csv_path=args.csv, rows=rows)

        env = envelope(command, args.csv, rows)
        env.update({
            "value_column": args.value,
            "group_column": args.group,
            "missing_policy": MISSING_POLICY,
            "dedup_policy": DEDUP_POLICY,
            "n_missing_value": n_missing_value,
            "n_missing_group_label": n_missing_group,
            "n_exact_duplicate_rows": count_exact_duplicates(rows, fields),
            "group_sizes": sizes,
            "requested_analysis": ("two-sample t-test (parametric)" if k == 2
                                   else "one-way ANOVA (parametric)"),
            "assumptions_meta": {
                "alpha": alpha,
                "normality_method": "dagostino_pearson_k2 (n>=8) plus |g1|>1/|g2|>2 rule for n<20",
                "variance_method": "brown_forsythe (Levene with medians)",
                "tie_correction": True,
                "min_n_per_group_for_parametric": 8,
            },
            "prerequisite_checks": [],
            "formulas": FORMULAS,
        })

        gvals = [groups[lb] for lb in labels]
        min_n = min(sizes.values())

        # --- 前提 1：样本量 ---
        size_ok = min_n >= 8
        env["prerequisite_checks"].append({
            "name": "min_group_size",
            "statistic": float(min_n), "df": None, "p": None,
            "pass": size_ok, "threshold": "min n per group >= 8",
        })

        # --- 前提 2：逐组正态性 ---
        norm_results = {}
        normality_ok = size_ok
        for lb, gv in zip(labels, gvals):
            chk = normality_check(gv, alpha)
            norm_results[lb] = chk
            env["prerequisite_checks"].append(
                dict(chk, group=lb))
            if chk["pass"] is False:
                normality_ok = False
        # --- 前提 3：方差齐性（Brown-Forsythe）---
        bf = brown_forsythe(gvals)
        if bf is not None:
            var_ok = bf["p"] >= alpha
            env["prerequisite_checks"].append({
                "name": "variance_homogeneity_brown_forsythe",
                "statistic": bf["f"], "df": [bf["df1"], bf["df2"]], "p": bf["p"],
                "pass": var_ok, "threshold": "p >= alpha=%.4f" % alpha,
            })
        else:
            var_ok = False
            env["prerequisite_checks"].append({
                "name": "variance_homogeneity_brown_forsythe",
                "statistic": None, "df": None, "p": None, "pass": False,
                "threshold": "computable",
                "note": "within-group absolute deviations all zero",
            })

        reroute_reason = None
        if not size_ok:
            reroute_reason = ("min group n=%d < 8: normal-approximation parametric "
                              "tests refused; rerouted to rank-based test" % min_n)
        elif not normality_ok:
            bad = [lb for lb, c in norm_results.items() if c["pass"] is False]
            reroute_reason = ("normality check failed for group(s) %s "
                              "(D'Agostino-Pearson K^2 and/or small-n skew/kurt rule); "
                              "p-value of t-test/ANOVA would not be defensible; "
                              "rerouted to rank-based test" % bad)

        if k == 2:
            g1v, g2v = gvals
            if reroute_reason is None:
                # 参数路径：Welch 为主，Student 并列报告
                welch = welch_ttest(g1v, g2v)
                student = student_ttest(g1v, g2v)
                if welch is None or student is None:
                    return emit_error(command, "zero variance: t-tests not computable",
                                      out_path=args.out, csv_path=args.csv, rows=rows)
                env["chosen_test"] = "welch_t_test"
                env["reroute_reason"] = None
                env["variance_note"] = (
                    None if var_ok else
                    "Brown-Forsythe rejected equal variances: Welch is the defensible "
                    "choice; Student t reported for reference only")
                env["results"] = {
                    "statistic": welch["t"], "df": welch["df"],
                    "p_value": welch["p"],
                    "effect_size": {"name": "cohens_d_pooled_reference",
                                    "value": student["cohens_d"]},
                    "ci95": welch["ci95_diff"],
                    "mean_diff": welch["mean_diff"],
                    "group_order": labels,
                }
                env["secondary_results"] = {
                    "student_t_test": {
                        "statistic": student["t"], "df": student["df"],
                        "p_value": student["p"], "ci95": student["ci95_diff"],
                    }
                }
                return emit(env, args.out, 0)
            else:
                mwu = mann_whitney_u(g1v, g2v)
                if mwu is None:
                    return emit_error(command,
                                      "all values tied: Mann-Whitney not computable",
                                      out_path=args.out, csv_path=args.csv, rows=rows)
                env["chosen_test"] = "mann_whitney_u"
                env["reroute_reason"] = reroute_reason
                env["results"] = {
                    "statistic": mwu["u_stat"], "df": None,
                    "p_value": mwu["p"],
                    "effect_size": {"name": "rank_biserial_correlation",
                                    "value": mwu["rank_biserial"]},
                    "ci95": None,
                    "z": mwu["z"], "u1": mwu["u1"], "u2": mwu["u2"],
                    "n_tie_groups": mwu["n_tie_groups"],
                    "group_order": labels,
                    "sign_convention": ("rank_biserial = 2*U1/(n1*n2)-1, U1 of first "
                                        "label in sorted order (%r); positive = first "
                                        "group larger" % labels[0]),
                }
                return emit(env, args.out, 2)
        else:
            if reroute_reason is None and var_ok:
                res = anova_oneway(gvals)
                if res is None:
                    return emit_error(command, "ANOVA not computable (zero within SS)",
                                      out_path=args.out, csv_path=args.csv, rows=rows)
                env["chosen_test"] = "anova_oneway"
                env["reroute_reason"] = None
                env["results"] = {
                    "statistic": res["f"], "df": [res["df1"], res["df2"]],
                    "p_value": res["p"],
                    "effect_size": {"name": "eta_squared", "value": res["eta_squared"]},
                    "ci95": None,
                }
                return emit(env, args.out, 0)
            else:
                if reroute_reason is None and not var_ok:
                    reroute_reason = ("variance homogeneity rejected for k>2 groups; "
                                      "rerouted to Kruskal-Wallis")
                kw = kruskal_wallis(gvals)
                if kw is None:
                    return emit_error(command,
                                      "all values tied: Kruskal-Wallis not computable",
                                      out_path=args.out, csv_path=args.csv, rows=rows)
                env["chosen_test"] = "kruskal_wallis"
                env["reroute_reason"] = reroute_reason
                env["results"] = {
                    "statistic": kw["h"], "df": kw["df"],
                    "p_value": kw["p"],
                    "effect_size": {"name": "eta_squared_h",
                                    "value": kw["eta_squared_h"]},
                    "ci95": None,
                    "n_tie_groups": kw["n_tie_groups"],
                    "group_order": labels,
                }
                return emit(env, args.out, 2)
    except ValueError as e:
        return emit_error(command, str(e), out_path=args.out,
                          csv_path=args.csv, rows=rows)


# ---------------------------------------------------------------------------
# 子命令：corr
# ---------------------------------------------------------------------------

def cmd_corr(args):
    command = "corr"
    try:
        fields, rows = read_table(args.csv)
    except OSError as e:
        return emit_error(command, "cannot read csv: %s" % e, out_path=args.out)
    try:
        for c in (args.x, args.y):
            if c not in fields:
                raise ValueError("column %r not found; available: %s"
                                 % (c, ", ".join(fields)))
        xs, ys = [], []
        n_missing = 0
        for row in rows:
            vx = parse_value(row.get(args.x))
            vy = parse_value(row.get(args.y))
            if vx is None or vy is None:
                n_missing += 1
                continue
            xs.append(vx)
            ys.append(vy)
        n = len(xs)
        if n < 3:
            return emit_error(command, "n=%d < 3 after pairwise drop" % n,
                              out_path=args.out, csv_path=args.csv, rows=rows)
        pr = pearson_corr(xs, ys)
        sr = spearman_corr(xs, ys)
        if pr is None or sr is None:
            return emit_error(command, "constant column: correlation undefined",
                              out_path=args.out, csv_path=args.csv, rows=rows)
        env = envelope(command, args.csv, rows)
        env.update({
            "x": args.x, "y": args.y,
            "missing_policy": MISSING_POLICY + "（两列成对剔除）",
            "dedup_policy": DEDUP_POLICY,
            "n_rows_total": len(rows),
            "n_used": n,
            "n_missing_pairwise": n_missing,
            "n_exact_duplicate_rows": count_exact_duplicates(rows, fields),
            "pearson": pr,
            "spearman": sr,
            "formulas": {"pearson": FORMULAS["pearson"],
                         "spearman": FORMULAS["spearman"]},
        })
        return emit(env, args.out, 0)
    except ValueError as e:
        return emit_error(command, str(e), out_path=args.out,
                          csv_path=args.csv, rows=rows)


# ---------------------------------------------------------------------------
# 子命令：verify-claims
# ---------------------------------------------------------------------------

P_KINDS = {"ttest_p", "welch_p", "student_p", "mwu_p", "pearson_p"}


def recompute_claim(claim, fields, rows):
    """按本工具口径独立复算单条断言；返回 recomputed value 或抛 ValueError。"""
    kind = claim.get("kind")
    col = claim.get("column")
    gspec = claim.get("group")  # 形如 "col:value" 的行过滤
    group_col = group_val = None
    if gspec:
        if ":" not in gspec:
            raise ValueError("group filter must be 'col:value', got %r" % gspec)
        group_col, group_val = gspec.split(":", 1)

    def col_vals(c):
        vals, _, _ = extract_column(rows, c, fields, group_col, group_val)
        if len(vals) < 1:
            raise ValueError("no usable values for column %r" % c)
        return vals

    if kind == "n":
        return float(len(col_vals(col)))
    if kind == "mean":
        return statistics.fmean(col_vals(col))
    if kind == "median":
        return statistics.median(col_vals(col))
    if kind == "std":
        ddof = int(claim.get("ddof", 1))
        vals = col_vals(col)
        if ddof == 0:
            return math.sqrt(statistics.pvariance(vals))
        return statistics.stdev(vals)
    if kind == "variance":
        ddof = int(claim.get("ddof", 1))
        vals = col_vals(col)
        return statistics.pvariance(vals) if ddof == 0 else statistics.variance(vals)
    if kind == "min":
        return min(col_vals(col))
    if kind == "max":
        return max(col_vals(col))
    if kind == "skewness":
        return skew_kurt(col_vals(col))[0]
    if kind == "excess_kurtosis":
        return skew_kurt(col_vals(col))[1]
    if kind in ("q1", "q2", "q3"):
        method = claim.get("quartile_method", "inclusive")
        vals = col_vals(col)
        q = statistics.quantiles(vals, n=4, method=method)
        return q[{"q1": 0, "q2": 1, "q3": 2}[kind]]
    if kind in ("pearson_r", "pearson_p", "spearman_r"):
        xs, ys = [], []
        xcol, ycol = claim.get("x"), claim.get("y")
        if not xcol or not ycol:
            raise ValueError("corr claims need x and y fields")
        for row in rows:
            vx = parse_value(row.get(xcol))
            vy = parse_value(row.get(ycol))
            if vx is None or vy is None:
                continue
            xs.append(vx)
            ys.append(vy)
        res = pearson_corr(xs, ys) if kind.startswith("pearson") else spearman_corr(xs, ys)
        if res is None:
            raise ValueError("correlation not computable (constant column)")
        if kind == "pearson_r":
            return res["r"]
        if kind == "pearson_p":
            return res["p_two_sided"]
        return res["rho"]
    if kind in ("ttest_p", "welch_p", "student_p", "mwu_p"):
        gcol = claim.get("group_col")
        if not gcol:
            raise ValueError("%s claims need group_col" % kind)
        groups = {}
        for row in rows:
            gv = (row.get(gcol) or "").strip()
            if gv.lower() in MISSING_TOKENS:
                continue
            v = parse_value(row.get(col))
            if v is None:
                continue
            groups.setdefault(gv, []).append(v)
        labels = sorted(groups.keys())
        if len(labels) != 2:
            raise ValueError("%s requires exactly 2 groups, got %d" % (kind, len(labels)))
        g1v, g2v = groups[labels[0]], groups[labels[1]]
        if kind in ("ttest_p", "welch_p"):
            method = claim.get("method", "welch" if kind != "student_p" else "student")
            res = welch_ttest(g1v, g2v) if method == "welch" else student_ttest(g1v, g2v)
        elif kind == "student_p":
            res = student_ttest(g1v, g2v)
        else:
            res = mann_whitney_u(g1v, g2v)
        if res is None:
            raise ValueError("test not computable")
        return res["p"]
    raise ValueError("unsupported claim kind %r" % kind)


def close_enough(kind, claimed, recomputed):
    if kind in P_KINDS:
        return abs(claimed - recomputed) <= 1e-3
    scale = max(abs(claimed), abs(recomputed), 1e-12)
    return abs(claimed - recomputed) / scale <= 1e-6


def cmd_verify_claims(args):
    command = "verify-claims"
    try:
        fields, rows = read_table(args.csv)
    except OSError as e:
        return emit_error(command, "cannot read csv: %s" % e, out_path=args.out)
    try:
        with open(args.claims, encoding="utf-8") as fh:
            claims = json.load(fh)
        if not isinstance(claims, list):
            raise ValueError("claims file must be a JSON list")
    except (OSError, ValueError) as e:
        return emit_error(command, "cannot read claims: %s" % e, out_path=args.out)

    env = envelope(command, args.csv, rows)
    env["claims_file"] = str(args.claims)
    env["tolerance"] = {"relative": 1e-6, "p_value_abs": 1e-3,
                        "note": "p 值按绝对容差 1e-3，其余按相对容差 1e-6"}
    env["verdicts"] = []
    n_fail = 0
    for claim in claims:
        cid = claim.get("id")
        try:
            recomputed = recompute_claim(claim, fields, rows)
            claimed = float(claim.get("value"))
            ok = close_enough(claim.get("kind"), claimed, recomputed)
            verdict = {"id": cid, "kind": claim.get("kind"),
                       "claimed": claimed, "recomputed": recomputed,
                       "verdict": "PASS" if ok else "FAIL"}
        except (ValueError, TypeError) as e:
            n_fail += 1
            verdict = {"id": cid, "kind": claim.get("kind"),
                       "verdict": "FAIL", "reason": "recompute error: %s" % e}
        if verdict["verdict"] == "FAIL":
            n_fail += 0  # 已在下方统一计数
        env["verdicts"].append(verdict)
    n_fail = sum(1 for v in env["verdicts"] if v["verdict"] == "FAIL")
    env["summary"] = {"total": len(env["verdicts"]),
                      "pass": len(env["verdicts"]) - n_fail, "fail": n_fail}
    env["status"] = "ok" if n_fail == 0 else "claims_failed"
    return emit(env, args.out, 0 if n_fail == 0 else 1)


# ---------------------------------------------------------------------------
# 子命令：selftest
# ---------------------------------------------------------------------------

def _check(name, got, want, tol):
    ok = abs(got - want) <= tol
    return {"name": name, "got": got, "expected": want, "tol": tol,
            "verdict": "PASS" if ok else "FAIL"}


def cmd_selftest(args):
    checks = []
    # 正态 CDF 已知点
    checks.append(_check("norm_cdf(1.959963984540054)=0.975",
                         norm_cdf(1.959963984540054), 0.975, 1e-12))
    checks.append(_check("norm_cdf(0)=0.5", norm_cdf(0.0), 0.5, 1e-15))
    # t 大自由度 ≈ 正态
    for x in (0.5, 1.0, 1.96, 2.576):
        checks.append(_check("t_cdf(%g, df=10000) ~ norm_cdf" % x,
                             t_cdf(x, 10000.0), norm_cdf(x), 1e-4))
    # t 分布已知分位数
    checks.append(_check("t_ppf(0.975, df=10)",
                         t_ppf(0.975, 10.0), 2.2281388519649385, 1e-9))
    # chi2 已知点：chi2_1 的 0.95 分位 = 3.841458820984124
    checks.append(_check("chi2_cdf(3.841458820984124, k=1)=0.95",
                         chi2_cdf(3.841458820984124, 1.0), 0.95, 1e-9))
    # chi2_2 的 0.95 分位 = 5.991464547107979
    checks.append(_check("chi2_cdf(5.991464547107979, k=2)=0.95",
                         chi2_cdf(5.991464547107979, 2.0), 0.95, 1e-9))
    # chi2_sf 与 1-cdf 一致性（尾部）
    checks.append(_check("chi2_sf tail consistency k=5 x=20",
                         chi2_sf(20.0, 5.0), 1.0 - chi2_cdf(20.0, 5.0), 1e-12))
    # F(1,df) = t^2 一致性：F_cdf(t^2,1,df) = 1 - 2*t_sf(t)
    df, tv = 17.0, 2.11
    checks.append(_check("F_cdf(t^2,1,17) == two-sided t consistency",
                         f_cdf(tv * tv, 1.0, df),
                         1.0 - t_p_two_sided(tv, df), 1e-10))
    # F 已知点：F(3.84,1,大df) ≈ chi2_1 0.95 分位 -> f_cdf(3.8416,1,1e6) ≈ 0.95
    checks.append(_check("f_cdf(3.841458820984124,1,1e8)~0.95",
                         f_cdf(3.841458820984124, 1.0, 1e8), 0.95, 1e-6))
    # betai 恒等：I_x(1,1)=x
    checks.append(_check("betai(1,1,0.3)=0.3", betai(1.0, 1.0, 0.3), 0.3, 1e-14))
    # gammainc 恒等：P(1,x)=1-e^-x
    checks.append(_check("gammainc_p(1,2)=1-e^-2",
                         gammainc_p(1.0, 2.0), 1.0 - math.exp(-2.0), 1e-14))
    # MWU 手算点：g1=[1,2], g2=[3,4] -> U=0, z 含连续性校正
    mwu = mann_whitney_u([1.0, 2.0], [3.0, 4.0])
    checks.append(_check("MWU U([1,2],[3,4])=0", mwu["u_stat"], 0.0, 1e-12))
    checks.append(_check("MWU rank_biserial([1,2],[3,4])=-1",
                         mwu["rank_biserial"], -1.0, 1e-12))
    # Spearman 完全单调
    sp = spearman_corr([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    checks.append(_check("spearman perfect monotone rho=1", sp["rho"], 1.0, 1e-12))
    # D'Agostino K^2 对正态样本不应极端（固定种子）
    import random
    rng = random.Random(42)
    sample = [rng.gauss(0, 1) for _ in range(200)]
    k2res = dagostino_k2(sample)
    checks.append(_check("dagostino K2 p on N(0,1) seed=42 > 0.01",
                         k2res["p"], 0.5, 0.49))

    n_fail = sum(1 for c in checks if c["verdict"] == "FAIL")
    env = envelope("selftest")
    env["checks"] = checks
    env["summary"] = {"total": len(checks), "pass": len(checks) - n_fail,
                      "fail": n_fail}
    env["status"] = "ok" if n_fail == 0 else "selftest_failed"
    return emit(env, args.out, 0 if n_fail == 0 else 1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="stattool",
        description="统计计算与前提裁决工具（stdlib-only）。前提不满足即改判并说明理由。")
    sub = p.add_subparsers(dest="subcommand", required=True)

    d = sub.add_parser("descriptive", help="描述统计（口径显式）")
    d.add_argument("--csv", required=True)
    d.add_argument("--col", required=True)
    d.add_argument("--group", default=None)
    d.add_argument("--out", default=None)
    d.set_defaults(func=cmd_descriptive)

    c = sub.add_parser("compare", help="组间比较前提裁决")
    c.add_argument("--csv", required=True)
    c.add_argument("--group", required=True)
    c.add_argument("--value", required=True)
    c.add_argument("--alpha", type=float, default=0.05)
    c.add_argument("--out", default=None)
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("corr", help="Pearson + Spearman 相关")
    r.add_argument("--csv", required=True)
    r.add_argument("--x", required=True)
    r.add_argument("--y", required=True)
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_corr)

    v = sub.add_parser("verify-claims", help="独立复算断言")
    v.add_argument("--claims", required=True)
    v.add_argument("--csv", required=True)
    v.add_argument("--out", default=None)
    v.set_defaults(func=cmd_verify_claims)

    s = sub.add_parser("selftest", help="特殊函数数值自检")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_selftest)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
