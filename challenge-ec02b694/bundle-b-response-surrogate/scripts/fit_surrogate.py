#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fit_surrogate.py -- 仅用标准库的最小二乘响应面（RSM）代理模型拟合。

方法：
  - 因子编码到 [-1, 1]（coded = 2*(x - mid) / (max - min)）；
  - 线性或完全二次 RSM（含全部二阶交互），正规方程 + 高斯消元（部分主元）求解；
  - 要求 n >= p + 2（p 为含截距的参数个数），否则拒绝拟合并走诚实降级路径；
  - 正规方程奇异（主元 < 1e-12）时拒绝拟合，同样走降级路径并说明；
  - 降级路径 = 均值/最近邻预测 + 显式放大的不确定区间，
    并在输出中写明 "样本不足，预测仅供假设"；
  - LOO-CV 通过逐点重拟合实现（某折奇异时该折退化为均值预测并计数）。

输出 surrogate.json：模型模式、系数（编码变量）、R2、LOO-CV RMSE、
残差诊断摘要、有效域（各维 min/max 盒）、不确定度模型说明、降级说明。

用法：
  python3 fit_surrogate.py --csv history.csv --factors temp_C,time_h \
      --response conversion_pct --model auto --out surrogate.json
"""
import argparse
import csv
import json
import math
import os
import sys

PIVOT_TOL = 1e-12
# 95% 双侧 t 分位数表（df -> t）；df>120 用 1.96 近似
T_TABLE = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
           7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
           13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
           19: 2.093, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000,
           120: 1.980}
MISSING = ("", "-", "na", "n/a", "nan", "none", "null", "?")


def t_crit(df):
    """95% 双侧 t 临界值；df<1 时返回 None（无法构造区间）。"""
    if df is None or df < 1:
        return None
    keys = sorted(T_TABLE)
    for k in keys:
        if df <= k:
            return T_TABLE[k]
    return 1.96


def solve_linear(A, b):
    """高斯消元（部分主元）解 Ax=b；奇异返回 None。"""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < PIVOT_TOL:
            return None
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            if f == 0.0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        if abs(M[i][i]) < PIVOT_TOL:
            return None
        s = M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / M[i][i]
    return x


def invert_matrix(A):
    """Gauss-Jordan 求逆；奇异返回 None。"""
    n = len(A)
    M = [list(A[i]) + [1.0 if j == i else 0.0 for j in range(n)] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < PIVOT_TOL:
            return None
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        M[col] = [v / d for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0.0:
                f = M[r][col]
                M[r] = [M[r][c] - f * M[col][c] for c in range(2 * n)]
    return [row[n:] for row in M]


def quadratic_terms(k):
    """完全二次模型的项表（编码变量）。返回 [(name, powers_tuple), ...]。"""
    terms = [("1", tuple([0] * k))]
    for i in range(k):
        p = [0] * k
        p[i] = 1
        terms.append(("x%d" % i, tuple(p)))
    for i in range(k):
        p = [0] * k
        p[i] = 2
        terms.append(("x%d^2" % i, tuple(p)))
    for i in range(k):
        for j in range(i + 1, k):
            p = [0] * k
            p[i] = 1
            p[j] = 1
            terms.append(("x%d*x%d" % (i, j), tuple(p)))
    return terms


def linear_terms(k):
    terms = [("1", tuple([0] * k))]
    for i in range(k):
        p = [0] * k
        p[i] = 1
        terms.append(("x%d" % i, tuple(p)))
    return terms


def eval_term(powers, x):
    v = 1.0
    for pw, xi in zip(powers, x):
        v *= xi ** pw
    return v


def design_matrix(terms, X):
    return [[eval_term(p, x) for _, p in terms] for x in X]


def fit_ols(terms, X, y):
    """返回 dict(beta, yhat, residuals, inv_xtx, sigma2, df) 或 None（奇异）。"""
    F = design_matrix(terms, X)
    n = len(F)
    p = len(terms)
    xtx = [[sum(F[r][i] * F[r][j] for r in range(n)) for j in range(p)] for i in range(p)]
    xty = [sum(F[r][i] * y[r] for r in range(n)) for i in range(p)]
    beta = solve_linear(xtx, xty)
    if beta is None:
        return None
    yhat = [sum(beta[j] * F[r][j] for j in range(p)) for r in range(n)]
    residuals = [y[r] - yhat[r] for r in range(n)]
    df = n - p
    sigma2 = (sum(e * e for e in residuals) / df) if df > 0 else None
    inv = invert_matrix(xtx)
    return {"beta": beta, "yhat": yhat, "residuals": residuals,
            "inv_xtx": inv, "sigma2": sigma2, "df": df}


def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], [dict(r) for r in reader]


def parse_dataset(header, rows, factors, response, warnings_):
    """抽取数值矩阵；跳过坏行并计数。返回 (X, y, used_rows)。"""
    X, y, used = [], [], 0
    for idx, row in enumerate(rows):
        vals = []
        ok = True
        for f in factors:
            v = str(row.get(f, "")).strip()
            if v.lower() in MISSING:
                ok = False
                break
            try:
                vals.append(float(v))
            except ValueError:
                ok = False
                break
        rv = str(row.get(response, "")).strip()
        if ok and (rv.lower() in MISSING or rv == ""):
            ok = False
        if ok:
            try:
                rval = float(rv)
            except ValueError:
                ok = False
        if not ok:
            warnings_.append("第 %d 行因子/响应缺失或非数值，已跳过" % (idx + 2))
            continue
        X.append(vals)
        y.append(rval)
        used += 1
    return X, y, used


def code_params(X):
    """返回每维 (lo, hi)；退化维 (lo==hi) 单独标记。"""
    k = len(X[0])
    params = []
    for j in range(k):
        col = [x[j] for x in X]
        params.append((min(col), max(col)))
    return params


def encode(x, params):
    out = []
    for xi, (lo, hi) in zip(x, params):
        if hi - lo < 1e-15:
            out.append(0.0)
        else:
            out.append(2.0 * (xi - 0.5 * (lo + hi)) / (hi - lo))
    return out


def fallback_payload(reason, factors, response, X, y, domain, warnings_):
    """诚实降级路径：均值/最近邻 + 显式放大区间。"""
    n = len(y)
    mean = sum(y) / n if n else None
    var = (sum((v - mean) ** 2 for v in y) / (n - 1)) if (n > 1 and mean is not None) else None
    std = math.sqrt(var) if var is not None else None
    payload = {
        "schema_version": "1.0",
        "generated_by": "fit_surrogate.py",
        "mode": "fallback",
        "fallback_reason": reason,
        "fallback_notice": "样本不足或设计矩阵奇异，无法拟合响应面；"
                           "以下预测仅供提出假设，不得作为可执行事实，"
                           "任何候选条件都必须经实测确认。",
        "factors": factors,
        "response": response,
        "n_used": n,
        "estimator": "mean / nearest-neighbor",
        "mean_response": mean,
        "std_response": std,
        # 区间放大：至少 3*std；std 不可估时用数据极差
        "interval_model": "prediction interval = estimate +/- max(3*std, 0.5*range)；"
                          "样本不足时不存在可信的模型化不确定度，故按探索性尺度显式放大",
        "data_range": ([min(y), max(y)] if n else None),
        "training_points": [{"x": X[i], "y": y[i]} for i in range(n)],
        "valid_domain": domain,
        "warnings": warnings_,
    }
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="标准库 OLS 响应面代理模型拟合（含诚实降级）")
    parser.add_argument("--csv", dest="csv_path", required=True, help="历史实验 CSV")
    parser.add_argument("--factors", required=True, help="逗号分隔的因子列名")
    parser.add_argument("--response", required=True, help="响应指标列名")
    parser.add_argument("--model", default="auto", choices=["auto", "linear", "quadratic"],
                        help="auto: 样本够则二次，否则线性，否则降级")
    parser.add_argument("--out", default="surrogate.json", help="输出路径")
    args = parser.parse_args(argv)

    warnings_ = []
    out_path = args.out
    factors = [f.strip() for f in args.factors.split(",") if f.strip()]
    response = args.response.strip()
    exit_code = 0

    try:
        if not factors or not response:
            raise ValueError("factors 与 response 均不能为空")
        header, rows = read_rows(args.csv_path)
        missing_cols = [c for c in factors + [response] if c not in header]
        if missing_cols:
            raise ValueError("CSV 缺少列: %s（实际列: %s）" % (", ".join(missing_cols), ", ".join(header)))
        X_raw, y, n_used = parse_dataset(header, rows, factors, response, warnings_)
        n = len(y)
        k = len(factors)

        domain = {"factors": factors,
                  "box": {factors[j]: [min(x[j] for x in X_raw), max(x[j] for x in X_raw)]
                          for j in range(k)} if X_raw else {}}

        if n == 0:
            payload = fallback_payload("没有任何可用数据行", factors, response, X_raw, y, domain, warnings_)
            exit_code = 1
        else:
            # 退化维检测
            params = code_params(X_raw)
            for j, (lo, hi) in enumerate(params):
                if hi - lo < 1e-15:
                    warnings_.append("因子 %s 在训练数据中为常数（%g），其效应不可识别，编码置 0"
                                     % (factors[j], lo))
            Xc = [encode(x, params) for x in X_raw]

            terms_q = quadratic_terms(k)
            terms_l = linear_terms(k)
            if args.model == "quadratic":
                candidates = [("quadratic", terms_q), ("linear", terms_l)]
            elif args.model == "linear":
                candidates = [("linear", terms_l)]
            else:
                candidates = [("quadratic", terms_q), ("linear", terms_l)]

            chosen = None
            reject_reasons = []
            for name, terms in candidates:
                p = len(terms)
                if n < p + 2:
                    reject_reasons.append("%s 模型需要 n >= p+2 = %d，实际 n = %d" % (name, p + 2, n))
                    continue
                fit = fit_ols(terms, Xc, y)
                if fit is None:
                    reject_reasons.append("%s 模型正规方程奇异（主元 < %g），拒绝拟合" % (name, PIVOT_TOL))
                    continue
                chosen = (name, terms, fit)
                break

            if chosen is None:
                reason = ("；".join(reject_reasons)) or "无可用模型"
                payload = fallback_payload(reason, factors, response, X_raw, y, domain, warnings_)
                exit_code = 1
            else:
                name, terms, fit = chosen
                p = len(terms)
                ybar = sum(y) / n
                ss_res = sum(e * e for e in fit["residuals"])
                ss_tot = sum((v - ybar) ** 2 for v in y)
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else None

                # LOO-CV：逐点重拟合
                loo_err2 = []
                loo_singular = 0
                for i in range(n):
                    Xl = Xc[:i] + Xc[i + 1:]
                    yl = y[:i] + y[i + 1:]
                    if len(yl) < p + 1:
                        pred_i = sum(yl) / len(yl)
                        loo_singular += 1
                    else:
                        fl = fit_ols(terms, Xl, yl)
                        if fl is None:
                            pred_i = sum(yl) / len(yl)
                            loo_singular += 1
                        else:
                            row = design_matrix(terms, [Xc[i]])[0]
                            pred_i = sum(fl["beta"][j] * row[j] for j in range(p))
                    loo_err2.append((y[i] - pred_i) ** 2)
                loo_rmse = math.sqrt(sum(loo_err2) / len(loo_err2))

                res = fit["residuals"]
                resid_diag = {
                    "mean": sum(res) / n,
                    "std": math.sqrt(sum(e * e for e in res) / n),
                    "max_abs": max(abs(e) for e in res),
                    "note": "标准库实现未做正式正态性/异方差检验；请结合散点人工检查残差-预测值图",
                }

                payload = {
                    "schema_version": "1.0",
                    "generated_by": "fit_surrogate.py",
                    "mode": "rsm",
                    "model_type": name,
                    "factors": factors,
                    "response": response,
                    "n_used": n,
                    "n_skipped": len(rows) - n_used,
                    "coding": {factors[j]: {"min": params[j][0], "max": params[j][1],
                                            "formula": "coded = 2*(x-mid)/(max-min)"}
                               for j in range(k)},
                    "terms": [t for t, _ in terms],
                    "term_powers": [list(pows) for _, pows in terms],
                    "coefficients": {t: b for (t, _), b in zip(terms, fit["beta"])},
                    "r_squared": r2,
                    "loo_cv": {"rmse": loo_rmse, "n_folds": n,
                               "folds_fallback_to_mean": loo_singular,
                               "method": "leave-one-out by refitting (standard library)"},
                    "residual_diagnostics": resid_diag,
                    "sigma2": fit["sigma2"],
                    "df_error": fit["df"],
                    "t_crit_95": t_crit(fit["df"]),
                    "inv_xtx": fit["inv_xtx"],
                    "valid_domain": domain,
                    "uncertainty_model": {
                        "in_domain": "95% 预测区间 = yhat +/- t(0.975, df) * sqrt(sigma2 * (1 + x0' (X'X)^-1 x0))；"
                                     "x0 为候选点的编码特征向量",
                        "no_inverse": "若 (X'X)^-1 不可得，用 sigma2*(1+1/n) 近似并标记",
                        "out_of_domain": "候选点越出有效域盒时 extrapolation=true，区间按 (1+3*相对越界距离) 显式放大，"
                                         "且该预测仅为待确认假设",
                    },
                    "warnings": warnings_,
                }
                if fit["sigma2"] is None:
                    payload["warnings"].append("误差自由度为 0，sigma2 不可估，区间将退化")
                if fit["inv_xtx"] is None:
                    payload["warnings"].append("(X'X)^-1 求逆失败，预测区间退化为近似形式")
                if loo_singular:
                    payload["warnings"].append("LOO-CV 中 %d 折因奇异/样本不足退化为均值预测" % loo_singular)
    except Exception as exc:  # noqa: BLE001 - 绝不 traceback
        payload = {
            "schema_version": "1.0",
            "generated_by": "fit_surrogate.py",
            "mode": "fallback",
            "fallback_reason": "脚本内部异常（已降级）: %r" % (exc,),
            "fallback_notice": "拟合失败；以下仅供提出假设，不得作为可执行事实。",
            "factors": [f.strip() for f in args.factors.split(",") if f.strip()],
            "response": args.response,
            "n_used": 0,
            "estimator": "none",
            "mean_response": None,
            "std_response": None,
            "training_points": [],
            "valid_domain": {"factors": [], "box": {}},
            "warnings": ["输入不可用时输出此占位 surrogate.json"],
        }
        exit_code = 2

    try:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("写出 %s 失败: %s\n" % (out_path, exc))
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    if payload.get("mode") == "rsm":
        sys.stderr.write("fit_surrogate: mode=rsm(%s) n=%d R2=%s LOO-RMSE=%.4g -> %s\n"
                         % (payload["model_type"], payload["n_used"],
                            ("%.4f" % payload["r_squared"]) if payload["r_squared"] is not None else "NA",
                            payload["loo_cv"]["rmse"], out_path))
    else:
        sys.stderr.write("fit_surrogate: mode=fallback reason=%s -> %s\n"
                         % (payload.get("fallback_reason"), out_path))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
