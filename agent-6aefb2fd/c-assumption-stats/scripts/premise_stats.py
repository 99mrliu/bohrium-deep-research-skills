#!/usr/bin/env python3
"""premise_stats.py — 前提先行的统计裁决引擎。

两个子命令：

  group    组间差异检验：对 (分组列 × 数值特征) 的每个组合，先做前提检验
           （各组 Shapiro-Wilk 正态性 + Levene 方差齐性），再按决策树选择：
             全满足 & 2 组   → Student t（方差齐）/ Welch t（不齐）
             全满足 & ≥3 组  → 单因素 ANOVA + 两两 t（Bonferroni）
             任一不满足      → Mann-Whitney（2 组）/ Kruskal-Wallis + Dunn（≥3 组，Bonferroni）
           报告 p、效应量（η²/Cohen's d/ε²/r）、前提结论、多重比较校正口径，
           并按效应量给出"区分度排序"（wine 类任务的 Top 指标表）。

  regress  连续目标分析：Spearman 相关矩阵 + 标准化 OLS（numpy 实现，β、R²、
           调整 R²、VIF、残差 Shapiro 正态性），附"相关≠因果"口径声明。

输出：--out 目录下 statistics_group.json / statistics_regression.json + 打印摘要。
依赖：pandas、numpy、scipy。确定性（Shapiro n>500 时固定随机子抽样 seed=0）。
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

RNG = np.random.default_rng(0)


def shapiro_p(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3:
        return None
    if len(x) > 500:
        x = RNG.choice(x, 500, replace=False)
    return float(stats.shapiro(x).pvalue)


def cohen_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else 0.0


def eta_squared(groups):
    allv = np.concatenate(groups)
    gm = allv.mean()
    ss_b = sum(len(g) * (g.mean() - gm) ** 2 for g in groups)
    ss_t = float(((allv - gm) ** 2).sum())
    return float(ss_b / ss_t) if ss_t > 0 else 0.0


def dunn_posthoc(groups, names, alpha):
    """Dunn 检验 + Bonferroni。返回两两比较列表。"""
    combined = np.concatenate(groups)
    ranks = stats.rankdata(combined)
    N = len(combined)
    # 结校正
    _, counts = np.unique(combined, return_counts=True)
    tie = (counts ** 3 - counts).sum()
    sigma_base = (N * (N + 1) / 12.0) - tie / (12.0 * (N - 1))
    offs, rsums, ns = 0, [], []
    for g in groups:
        n = len(g)
        rsums.append(ranks[offs:offs + n].mean())
        ns.append(n)
        offs += n
    pairs, k = [], len(groups) * (len(groups) - 1) // 2
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            se = np.sqrt(sigma_base * (1.0 / ns[i] + 1.0 / ns[j]))
            z = (rsums[i] - rsums[j]) / se if se > 0 else 0.0
            p = 2 * stats.norm.sf(abs(z))
            pairs.append({"pair": [names[i], names[j]], "z": round(float(z), 4),
                          "p_bonferroni": round(min(p * k, 1.0), 6),
                          "significant": bool(p * k < alpha)})
    return pairs


def group_compare(df, group_col, features, alpha):
    out = {"mode": "group_compare", "group_column": group_col, "alpha": alpha,
           "features": {}, "discrimination_ranking": []}
    levels = sorted(df[group_col].dropna().unique().tolist())
    out["group_levels"] = [str(x) for x in levels]
    fam = max(1, len(features))
    out["multiple_testing"] = {"family": "features", "size": fam,
                               "bonferroni_alpha": round(alpha / fam, 6)}
    ranking = []
    for f in features:
        groups = [df.loc[df[group_col] == lv, f].dropna().to_numpy(dtype=float)
                  for lv in levels]
        groups = [g for g in groups]
        rec = {"n_per_group": {str(lv): int(len(g)) for lv, g in zip(levels, groups)}}
        if any(len(g) < 3 for g in groups):
            rec["error"] = "存在样本量 <3 的组，无法检验"
            out["features"][f] = rec
            continue
        norm_p = [shapiro_p(g) for g in groups]
        lev_p = float(stats.levene(*groups).pvalue)
        normal_ok = all(p is not None and p > alpha for p in norm_p)
        var_ok = lev_p > alpha
        rec["premises"] = {"shapiro_p_per_group": {str(lv): (None if p is None else round(p, 6))
                                                   for lv, p in zip(levels, norm_p)},
                           "levene_p": round(lev_p, 6),
                           "normality_ok": normal_ok, "variance_homogeneity_ok": var_ok}
        if normal_ok:
            if len(groups) == 2:
                t = stats.ttest_ind(*groups, equal_var=var_ok)
                rec.update(method="student_t" if var_ok else "welch_t",
                           statistic=round(float(t.statistic), 4),
                           p_value=round(float(t.pvalue), 6),
                           effect_size={"cohen_d": round(cohen_d(*groups), 4)})
            else:
                fstat = stats.f_oneway(*groups)
                rec.update(method="one_way_anova", statistic=round(float(fstat.statistic), 4),
                           p_value=round(float(fstat.pvalue), 6),
                           effect_size={"eta_squared": round(eta_squared(groups), 4)})
                pairs, k = [], len(groups) * (len(groups) - 1) // 2
                for i in range(len(groups)):
                    for j in range(i + 1, len(groups)):
                        t = stats.ttest_ind(groups[i], groups[j], equal_var=var_ok)
                        pairs.append({"pair": [str(levels[i]), str(levels[j])],
                                      "p_bonferroni": round(min(float(t.pvalue) * k, 1.0), 6),
                                      "cohen_d": round(cohen_d(groups[i], groups[j]), 4),
                                      "significant": bool(t.pvalue * k < alpha)})
                rec["posthoc"] = pairs
            if "eta_squared" in rec["effect_size"]:
                score = rec["effect_size"]["eta_squared"]
            else:
                score = abs(rec["effect_size"]["cohen_d"])
        else:
            if len(groups) == 2:
                u = stats.mannwhitneyu(*groups, alternative="two-sided")
                rb = 1.0 - 2.0 * float(u.statistic) / (len(groups[0]) * len(groups[1]))
                rec.update(method="mann_whitney_u", statistic=round(float(u.statistic), 4),
                           p_value=round(float(u.pvalue), 6),
                           effect_size={"rank_biserial": round(rb, 4)})
                score = abs(rb)
            else:
                h = stats.kruskal(*groups)
                eps2 = max(0.0, (float(h.statistic) - len(groups) + 1)
                           / (len(np.concatenate(groups)) - len(groups)))
                rec.update(method="kruskal_wallis", statistic=round(float(h.statistic), 4),
                           p_value=round(float(h.pvalue), 6),
                           effect_size={"epsilon_squared": round(eps2, 4)},
                           posthoc=dunn_posthoc(groups, [str(x) for x in levels], alpha))
                score = eps2
        rec["significant_raw"] = bool(rec["p_value"] < alpha)
        rec["significant_bonferroni_family"] = bool(rec["p_value"] < alpha / fam)
        ranking.append({"feature": f, "score": round(float(score), 4),
                        "method": rec["method"], "p_value": rec["p_value"]})
        out["features"][f] = rec
    out["discrimination_ranking"] = sorted(ranking, key=lambda r: -r["score"])
    return out


def regress(df, target, features):
    d = df[[target] + features].dropna()
    y = d[target].to_numpy(dtype=float)
    X = d[features].to_numpy(dtype=float)
    n, k = X.shape
    res = {"mode": "regression", "target": target, "n": int(n), "features": {}}
    res["spearman_with_target"] = {
        f: {"rho": round(float(stats.spearmanr(d[f], y).statistic), 4),
            "p": round(float(stats.spearmanr(d[f], y).pvalue), 6)} for f in features}
    Xs = (X - X.mean(0)) / X.std(0, ddof=1)
    ys = (y - y.mean()) / y.std(ddof=1)
    Xd = np.column_stack([np.ones(n), Xs])
    beta, *_ = np.linalg.lstsq(Xd, ys, rcond=None)
    yhat = Xd @ beta
    resid = ys - yhat
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    adj = 1 - (1 - r2) * (n - 1) / max(1, n - k - 1)
    corr = np.corrcoef(Xs, rowvar=False)
    try:
        vif = np.diag(np.linalg.inv(corr)).tolist()
    except np.linalg.LinAlgError:
        vif = [None] * k
    res["ols_standardized"] = {
        "r_squared": round(r2, 4), "adj_r_squared": round(adj, 4),
        "residual_shapiro_p": (None if shapiro_p(resid) is None else round(shapiro_p(resid), 6)),
        "coefficients": {f: {"beta_std": round(float(beta[i + 1]), 4),
                             "vif": (None if vif[i] is None else round(float(vif[i]), 3))}
                         for i, f in enumerate(features)},
        "caveat": "标准化 OLS 用于影响筛查；相关与回归系数不构成因果证据。"}
    return res


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("group")
    g.add_argument("--table", required=True); g.add_argument("--group", required=True)
    g.add_argument("--features", default=None, help="逗号分隔；缺省=全部数值列")
    g.add_argument("--alpha", type=float, default=0.05); g.add_argument("--out", required=True)
    r = sub.add_parser("regress")
    r.add_argument("--table", required=True); r.add_argument("--target", required=True)
    r.add_argument("--features", default=None); r.add_argument("--out", required=True)
    args = ap.parse_args()
    df = pd.read_csv(args.table)
    os.makedirs(args.out, exist_ok=True)

    if args.cmd == "group":
        feats = args.features.split(",") if args.features else [
            c for c in df.columns if c != args.group and pd.api.types.is_numeric_dtype(df[c])]
        doc = group_compare(df, args.group, feats, args.alpha)
        path = os.path.join(args.out, "statistics_group.json")
        n_sig = sum(1 for f in doc["features"].values()
                    if f.get("significant_bonferroni_family"))
        print(f"PREMISE_STATS_STATUS: ok features={len(feats)} "
              f"bonferroni_significant={n_sig}/{len(feats)} "
              f"top={doc['discrimination_ranking'][:3]}")
    else:
        feats = args.features.split(",") if args.features else [
            c for c in df.columns if c != args.target and pd.api.types.is_numeric_dtype(df[c])]
        doc = regress(df, args.target, feats)
        path = os.path.join(args.out, "statistics_regression.json")
        print(f"PREMISE_STATS_STATUS: ok n={doc['n']} "
              f"r2={doc['ols_standardized']['r_squared']}")
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
