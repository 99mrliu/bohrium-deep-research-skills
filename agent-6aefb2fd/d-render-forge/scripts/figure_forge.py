#!/usr/bin/env python3
"""figure_forge.py — 图表锻造场：意图驱动的图型选择 + 诚实坐标 + 全谱系清单。

每张图由一条 spec 声明"意图"（intent），图型由意图决定而非随手选择：

| intent        | 图型 | 诚实约束 |
|-|-|-|
| distribution  | 直方图+箱线双联 | y 轴从 0 起；bins 固定 30 |
| group_compare | 分组箱线+抖动散点叠加 | 逐点可见，不只画汇总；散点固定 seed 抖动 |
| correlation   | Spearman 相关热图 | 色标对称 [-1,1]；标注数值 |
| ranking       | 横向条形图 | 值轴从 0 起（禁止截断放大差异） |
| residual      | 残差-拟合散点 + 残差直方图 | 零参考线 |

用法：
  python3 figure_forge.py --table cleaned.csv --spec figspec.json --out /app/output/figures

figspec.json: [{"id":"fig1","intent":"group_compare","columns":["a","b"],"group":"class"},
               {"id":"fig2","intent":"correlation","columns":["a","b","c"]},
               {"id":"fig3","intent":"ranking","labels":[...],"values":[...],"title":"..."}]
（ranking 不需要表列，直接给标签与值——值必须来自统计产物，spec 文件本身即谱系证据。）

输出：每张一张 150dpi PNG + figures_manifest.json（file, intent, source_table,
columns/group, n_rows, axis 声明, spec 原文）。确定性：Agg 后端、固定 seed=0。
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as _stats

plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 150,
                     "axes.spines.top": False, "axes.spines.right": False})


def fig_distribution(df, col, axs):
    s = df[col].dropna()
    axs[0].hist(s, bins=30, color="#4C72B0", edgecolor="white")
    axs[0].set_ylim(bottom=0)
    axs[0].set_title(f"Histogram: {col}")
    axs[0].set_ylabel("count")
    axs[1].boxplot(s, vert=True)
    axs[1].set_title(f"Box: {col}")
    return {"aggregation": "raw", "n_rows": int(s.shape[0])}


def _boxplot(ax, data, labels):
    """matplotlib ≥3.9 用 tick_labels，旧版用 labels。"""
    try:
        ax.boxplot(data, tick_labels=labels, showfliers=False)
    except TypeError:
        ax.boxplot(data, labels=labels, showfliers=False)


def fig_group_compare(df, col, group, ax, rng):
    levels = sorted(df[group].dropna().unique())
    data = [df.loc[df[group] == lv, col].dropna().to_numpy(float) for lv in levels]
    _boxplot(ax, data, [str(l) for l in levels])
    for i, d in enumerate(data):
        ax.scatter(np.full(len(d), i + 1) + rng.uniform(-0.08, 0.08, len(d)),
                   d, s=6, alpha=0.4, color="#DD8452", zorder=3)
    ax.set_title(f"{col} by {group}")
    return {"aggregation": "group_boxplot+strip", "group": group,
            "n_rows": int(sum(len(d) for d in data))}


def fig_correlation(df, cols, ax, fig):
    sub = df[cols].dropna()
    corr = sub.corr(method="spearman")
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(cols)), cols, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(cols)), cols, fontsize=7)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center",
                    fontsize=6, color="black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Spearman correlation")
    return {"aggregation": "spearman", "n_rows": int(len(sub))}


def fig_ranking(spec, ax):
    labels, values = spec["labels"], spec["values"]
    order = np.argsort(values)
    ax.barh([labels[i] for i in order], [values[i] for i in order], color="#55A868")
    ax.set_xlim(left=0)
    ax.set_title(spec.get("title", "ranking"))
    return {"aggregation": "precomputed_values", "value_source": spec.get("value_source", "spec")}


def fig_residual(df, target, features, axs):
    d = df[[target] + features].dropna()
    y = d[target].to_numpy(float)
    X = d[features].to_numpy(float)
    Xd = np.column_stack([np.ones(len(d)), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta
    axs[0].scatter(Xd @ beta, resid, s=8, alpha=0.5)
    axs[0].axhline(0, color="red", lw=1)
    axs[0].set_xlabel("fitted")
    axs[0].set_ylabel("residual")
    axs[0].set_title("Residuals vs fitted")
    axs[1].hist(resid, bins=30, color="#4C72B0", edgecolor="white")
    axs[1].set_ylim(bottom=0)
    axs[1].set_title("Residual distribution")
    return {"aggregation": "ols_residuals", "n_rows": int(len(d)),
            "residual_shapiro_p": round(float(_stats.shapiro(
                resid if len(resid) <= 500 else resid[:500]).pvalue), 6)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=None)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    specs = json.load(open(args.spec, encoding="utf-8"))
    df = pd.read_csv(args.table) if args.table else None
    rng = np.random.default_rng(0)
    manifest = []

    for spec in specs:
        intent = spec["intent"]
        fid = spec["id"]
        path = os.path.join(args.out, f"{fid}.png")
        if intent == "distribution":
            fig, axs = plt.subplots(1, 2, figsize=(8, 3.2))
            meta = fig_distribution(df, spec["columns"][0], axs)
        elif intent == "group_compare":
            n = len(spec["columns"])
            fig, axs = plt.subplots(1, n, figsize=(4.2 * n, 3.6), squeeze=False)
            for k, col in enumerate(spec["columns"]):
                meta = fig_group_compare(df, col, spec["group"], axs[0][k], rng)
            fig.tight_layout()
        elif intent == "correlation":
            fig, ax = plt.subplots(figsize=(max(4, 0.5 * len(spec["columns"])),
                                            max(3.5, 0.45 * len(spec["columns"]))))
            meta = fig_correlation(df, spec["columns"], ax, fig)
            fig.tight_layout()
        elif intent == "ranking":
            fig, ax = plt.subplots(figsize=(6, max(2.5, 0.3 * len(spec["labels"]))))
            meta = fig_ranking(spec, ax)
            fig.tight_layout()
        elif intent == "residual":
            fig, axs = plt.subplots(1, 2, figsize=(8, 3.4))
            meta = fig_residual(df, spec["target"], spec["columns"], axs)
            fig.tight_layout()
        else:
            raise SystemExit(f"未知 intent: {intent}（允许 distribution/group_compare/"
                             f"correlation/ranking/residual）")
        fig.savefig(path)
        plt.close(fig)
        manifest.append({"file": path, "id": fid, "intent": intent,
                         "source_table": os.path.abspath(args.table) if args.table else None,
                         "columns": spec.get("columns"),
                         "axis_policy": "count/value axes start at 0 where applicable; "
                                        "no truncation",
                         "spec": spec, **meta})
        print(f"FIGURE_OK: {fid} intent={intent} -> {path}")

    mpath = os.path.join(args.out, "figures_manifest.json")
    json.dump(manifest, open(mpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"FIGURE_FORGE_STATUS: ok figures={len(manifest)} manifest={mpath}")


if __name__ == "__main__":
    main()
