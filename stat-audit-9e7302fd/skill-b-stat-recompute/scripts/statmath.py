#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statmath.py — 纯标准库统计分布数值内核。

提供:
  - 正则化不完全 Beta 函数 I_x(a,b)（连分式）
  - 正则化上不完全 Gamma 函数 Q(a,x)（级数 + 连分式）
  - t / F / χ² / 正态分布的双侧 p 值
  - 标准正态逆 CDF（Acklam 有理逼近），用于把握度/样本量反算

直接运行 `python3 statmath.py` 执行自检；任何一项失败即以非零码退出。
所有函数对非法输入抛出 ValueError，由调用方捕获并降级为「待复核」。
"""

import math
import sys

_EPS = 3.0e-14
_FPMIN = 1.0e-300
_MAXIT = 300


# ---------------------------------------------------------------- Beta ----
def _betacf(a, b, x):
    """不完全 Beta 的连分式部分（Numerical Recipes 6.4）。"""
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
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betai(a, b, x):
    """正则化不完全 Beta 函数 I_x(a,b)。"""
    if a <= 0.0 or b <= 0.0:
        raise ValueError("betai: a,b 必须为正")
    if x < 0.0 or x > 1.0:
        raise ValueError("betai: x 必须在 [0,1]")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


# --------------------------------------------------------------- Gamma ----
def gammq(a, x):
    """正则化上不完全 Gamma 函数 Q(a,x) = Γ(a,x)/Γ(a)。"""
    if a <= 0.0:
        raise ValueError("gammq: a 必须为正")
    if x < 0.0:
        raise ValueError("gammq: x 必须非负")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        # 级数表示求 P，再取补
        ap = a
        s = 1.0 / a
        d = s
        for _ in range(_MAXIT):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * _EPS:
                break
        p = s * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return 1.0 - p
    # 连分式表示直接求 Q
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
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


# -------------------------------------------------------------- p 值 ------
def t_two_sided_p(t, df):
    """t 分布双侧 p 值。df 必须为正。"""
    if df <= 0:
        raise ValueError("t: df 必须为正")
    x = df / (df + t * t)
    return min(1.0, max(0.0, betai(df / 2.0, 0.5, x)))


def f_sf(f, df1, df2):
    """F 分布上尾（即检验）p 值。"""
    if f < 0 or df1 <= 0 or df2 <= 0:
        raise ValueError("F: 非法参数")
    if f == 0.0:
        return 1.0
    x = df2 / (df2 + df1 * f)
    return min(1.0, max(0.0, betai(df2 / 2.0, df1 / 2.0, x)))


def chi2_sf(x, df):
    """χ² 分布上尾 p 值。"""
    if x < 0 or df <= 0:
        raise ValueError("chi2: 非法参数")
    return min(1.0, max(0.0, gammq(df / 2.0, x / 2.0)))


def norm_two_sided_p(z):
    """标准正态双侧 p 值。"""
    return math.erfc(abs(z) / math.sqrt(2.0))


def r_two_sided_p(r, df):
    """Pearson r 经 t 变换的双侧 p 值。df = n - 2。"""
    if df <= 0:
        raise ValueError("r: df 必须为正")
    if abs(r) >= 1.0:
        return 0.0
    t = abs(r) * math.sqrt(df / (1.0 - r * r))
    return t_two_sided_p(t, df)


# --------------------------------------------------------- 逆正态 CDF -----
# Acklam 有理逼近，最大误差约 1.15e-9（再经一步 Halley 精化）
_A = [-3.969683028665376e+01, 2.209460984245205e+02,
      -2.759285104469687e+02, 1.383577518672690e+02,
      -3.066479806614716e+01, 2.506628277459239e+00]
_B = [-5.447609879822406e+01, 1.615858368580409e+02,
      -1.556989798598866e+02, 6.680131188771972e+01,
      -1.328068155288572e+01]
_C = [-7.784894002430293e-03, -3.223964580411365e-01,
      -2.400758277161838e+00, -2.549732539343734e+00,
      4.374664141464968e+00, 2.938163982698783e+00]
_D = [7.784695709041462e-03, 3.224671290700398e-01,
      2.445134137142996e+00, 3.754408661907416e+00]
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def inv_norm(p):
    """标准正态逆 CDF Φ⁻¹(p)，0 < p < 1。"""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("inv_norm: p 必须在 (0,1) 开区间")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    elif p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
            (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    # 一步 Halley 精化
    e = 0.5 * math.erfc(-x / math.sqrt(2.0)) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    x = x - u / (1.0 + x * u / 2.0)
    return x


# ---------------------------------------------------------------- 自检 ----
def _selftest():
    cases = [
        ("t(2.45,126) 双侧p", lambda: t_two_sided_p(2.45, 126), 0.01566, 5e-4),
        ("F(3.05,2,125) 上尾p", lambda: f_sf(3.05, 2, 125), 0.0509, 5e-4),
        ("χ²(4.2,1) 上尾p", lambda: chi2_sf(4.2, 1), 0.0404, 5e-4),
        ("z=1.96 双侧p", lambda: norm_two_sided_p(1.96), 0.05, 5e-4),
        ("Φ⁻¹(0.975)", lambda: inv_norm(0.975), 1.959964, 1e-5),
    ]
    ok = True
    for name, fn, expect, tol in cases:
        try:
            got = fn()
            good = abs(got - expect) <= tol
            print("%s %s: got=%.6f expect=%.6f tol=%g" %
                  ("PASS" if good else "FAIL", name, got, expect, tol))
            ok = ok and good
        except Exception as exc:  # noqa: BLE001
            print("FAIL %s: 异常 %r" % (name, exc))
            ok = False
    return ok


if __name__ == "__main__":
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    sys.exit(0 if _selftest() else 1)
