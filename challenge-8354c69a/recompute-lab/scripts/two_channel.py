#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""two_channel.py — 双通道独立复算库（pure stdlib）。

原则：每个统计量用两条**实现路径不同**的算法各算一遍，差异超容差即报
DISAGREE——报数之前先证明这个数算不错。

通道设计（同输入、不同算法）：
  mean:    A=sum/n(单次遍历)        B=增量式在线均值
  var:     A=二阶矩 E[x²]-E[x]²     B=两遍法(先均值后偏差平方和)
  median:  A=排序取中               B=Quickselect
  slope:   A=正规方程闭式解          B=协方差/方差比
  auc_trapz: A=梯形(逐项累加)        B=梯形(成对平均×步长)
  max/argmax: A=一次遍历            B=排序取首

CLI:
  python3 two_channel.py series --file data.csv --col 1
  python3 two_channel.py fit --file data.csv --xcol 0 --ycol 1
输出: JSON 复算账本（每量: A值/B值/相对差/绝对差/verdict）。
"""
import argparse
import json
import math
import random
import re
import sys

ABS_TOL = 1e-9
REL_TOL = 1e-9


# ---- 通道 A/B 实现 -------------------------------------------------------

def mean_a(xs):
    return sum(xs) / len(xs)


def mean_b(xs):
    m = 0.0
    for i, x in enumerate(xs, 1):
        m += (x - m) / i
    return m


def var_a(xs):  # 总体方差, 二阶矩法
    n = len(xs)
    s1 = sum(xs)
    s2 = sum(x * x for x in xs)
    return s2 / n - (s1 / n) ** 2


def var_b(xs):  # 两遍法
    m = mean_b(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def median_a(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _qselect(a, k):
    pivot = a[random.Random(0).randrange(len(a))]
    lo = [x for x in a if x < pivot]
    eq = [x for x in a if x == pivot]
    if k < len(lo):
        return _qselect(lo, k)
    if k < len(lo) + len(eq):
        return pivot
    return _qselect([x for x in a if x > pivot], k - len(lo) - len(eq))


def median_b(xs):
    n = len(xs)
    if n % 2:
        return _qselect(list(xs), n // 2)
    return (_qselect(list(xs), n // 2 - 1) + _qselect(list(xs), n // 2)) / 2


def slope_a(xs, ys):  # 闭式解
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    return (n * sxy - sx * sy) / (n * sxx - sx * sx)


def slope_b(xs, ys):  # 协方差/方差
    mx, my = mean_b(xs), mean_b(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    return cov / vx


def auc_a(xs, ys):
    return sum((xs[i + 1] - xs[i]) * (ys[i + 1] + ys[i]) / 2
               for i in range(len(xs) - 1))


def auc_b(xs, ys):
    total = 0.0
    for i in range(len(xs) - 1):
        total += (xs[i + 1] - xs[i]) * (ys[i] + ys[i + 1]) * 0.5
    return total


def max_a(xs):
    best, bi = xs[0], 0
    for i, x in enumerate(xs):
        if x > best:
            best, bi = x, i
    return best, bi


def max_b(xs):
    order = sorted(range(len(xs)), key=lambda i: -xs[i])
    return xs[order[0]], order[0]


# ---- 判定 ----------------------------------------------------------------

def verdict(va, vb, abs_tol=ABS_TOL, rel_tol=REL_TOL):
    d = abs(va - vb)
    scale = max(abs(va), abs(vb), 1e-300)
    rel = d / scale
    ok = d <= abs_tol or rel <= rel_tol
    return {"A": va, "B": vb, "abs_diff": d, "rel_diff": rel,
            "verdict": "AGREE" if ok else "DISAGREE",
            "tolerance": {"abs": abs_tol, "rel": rel_tol}}


def read_cols(path, xcol=None, ycol=1):
    rows = []
    for line in open(path, encoding="utf-8", errors="replace"):
        t = line.strip()
        if not t or t[0] in "#;%":
            continue
        try:
            vals = [float(v) for v in re.split(r"[,\s\t]+", t) if v]
        except ValueError:
            continue
        if vals:
            rows.append(vals)
    if xcol is None:
        return [r[ycol] for r in rows if len(r) > ycol]
    return ([r[xcol] for r in rows if len(r) > max(xcol, ycol)],
            [r[ycol] for r in rows if len(r) > max(xcol, ycol)])


def cmd_series(a):
    ys = read_cols(a.file, ycol=a.col)
    if len(ys) < 2:
        sys.exit("数据点不足")
    ledger = {
        "file": a.file, "col": a.col, "n": len(ys),
        "quantities": {
            "mean": verdict(mean_a(ys), mean_b(ys)),
            "variance_pop": verdict(var_a(ys), var_b(ys)),
            "median": verdict(median_a(ys), median_b(ys)),
        },
    }
    ma, ia = max_a(ys)
    mb, ib = max_b(ys)
    ledger["quantities"]["max"] = verdict(ma, mb)
    ledger["quantities"]["argmax_agree"] = (ia == ib)
    bad = [k for k, v in ledger["quantities"].items()
           if isinstance(v, dict) and v.get("verdict") == "DISAGREE"]
    ledger["summary"] = {"n_quantities": len(ledger["quantities"]),
                         "disagree": bad,
                         "overall": "AGREE" if not bad else "DISAGREE"}
    print(json.dumps(ledger, ensure_ascii=False, indent=2))


def cmd_fit(a):
    xs, ys = read_cols(a.file, xcol=a.xcol, ycol=a.ycol)
    if len(xs) < 3:
        sys.exit("数据点不足")
    s = verdict(slope_a(xs, ys), slope_b(xs, ys))
    au = verdict(auc_a(xs, ys), auc_b(xs, ys))
    mx = mean_a(xs)
    intercept = mean_a(ys) - s["A"] * mx
    ledger = {"file": a.file, "n": len(xs),
              "quantities": {"slope": s, "auc_trapz": au,
                             "intercept_from_A": intercept},
              "summary": {"overall": "AGREE" if s["verdict"] == "AGREE"
                          and au["verdict"] == "AGREE" else "DISAGREE"}}
    print(json.dumps(ledger, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("series")
    p.add_argument("--file", required=True)
    p.add_argument("--col", type=int, default=1)
    p.set_defaults(fn=cmd_series)
    p = sub.add_parser("fit")
    p.add_argument("--file", required=True)
    p.add_argument("--xcol", type=int, default=0)
    p.add_argument("--ycol", type=int, default=1)
    p.set_defaults(fn=cmd_fit)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
