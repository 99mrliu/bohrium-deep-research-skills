#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sensitivity.py — 权重扰动敏感性分析（decision-forge-qc）。

给定 decision_package.json 中的 weights 与各方案维度分（scores）：
  * one-at-a-time 扰动：每个权重分别 ×1.5（up）与 ×0.5（down），其余权重按
    比例归一化（保持总和为 1）；
  * 等权重档：全部维度权重相等；
  * 输出每个情景的排名表，以及 rank-flip 报告：哪些权重扰动会翻转首选；
  * 翻转阈值：对每个维度解析求解首选发生翻转的权重临界值（其余权重保持
    相对比例），给出下调/上调两个方向的阈值与翻转后的首选；
  * 稳健性 verdict：robust（所有情景无翻转）/ sensitive（列出触发权重）。

退出码：0=成功；2=输入/用法错误；3=输入结构不满足分析前置条件
（如缺 weights/scores、基线首选存在并列）。

仅标准库；输出确定性（无时间戳/随机数），同一输入双跑逐字节一致。
"""
import argparse
import json
import sys
from pathlib import Path

EPS = 1e-12
NUDGE = 1e-9


class InputError(Exception):
    """输入/用法错误（退出码 2）。"""


class PrecheckError(Exception):
    """分析前置条件不满足（退出码 3）。"""


def load_json(path, what):
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{what}不存在: {p}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError as e:
        raise InputError(f"{what}不是合法 UTF-8: {p}: {e}")
    except json.JSONDecodeError as e:
        raise InputError(f"{what} JSON 解析失败: {p}: {e}")


def normalize(weights):
    total = sum(weights.values())
    if total <= 0:
        raise PrecheckError("权重总和必须为正")
    return {d: weights[d] / total for d in sorted(weights)}


def totals_for(scores, weights):
    return {pid: sum(scores[pid][d] * weights[d] for d in weights)
            for pid in sorted(scores)}


def ranking(totals):
    """按（-总分, plan_id）排序，平局时按 plan_id 字典序，保证确定性。"""
    return sorted(totals, key=lambda p: (-totals[p], p))


def perturb(weights, dim, factor):
    """dim 权重 ×factor，其余按比例归一化，总和保持 1。"""
    w0 = weights[dim]
    new = w0 * factor
    if new >= 1.0:
        return {d: (1.0 if d == dim else 0.0) for d in weights}
    scale = (1.0 - new) / (1.0 - w0) if w0 < 1.0 else 0.0
    return {d: (new if d == dim else weights[d] * scale) for d in weights}


def extract(pkg):
    if not isinstance(pkg, dict):
        raise PrecheckError("decision_package 顶层必须是 JSON 对象")
    weights = pkg.get("weights")
    scores = pkg.get("scores")
    if not isinstance(weights, dict) or not weights:
        raise PrecheckError("缺少非空 weights 对象")
    for d, w in weights.items():
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
            raise PrecheckError(f"权重 {d} 必须是正数: {w!r}")
    if not isinstance(scores, dict) or not scores:
        raise PrecheckError("缺少非空 scores 对象")
    for pid, ps in scores.items():
        if not isinstance(ps, dict):
            raise PrecheckError(f"方案 {pid} 的 scores 不是对象")
        for d in weights:
            v = ps.get(d)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise PrecheckError(f"方案 {pid} 缺少维度 {d} 的数值评分")
    return weights, scores


def flip_thresholds(scores, weights, totals0, dim, top):
    """解析求 dim 权重临界值：score_p(t) = s_pd*t + rest_p*(1-t)/(1-w0)，
    关于 t 线性；求首选 top 与各追赶者平分点，取两方向最近者。"""
    w0 = weights[dim]
    if w0 >= 1.0 - EPS:
        return {"down_flip": None, "up_flip": None,
                "note": "该维度权重已为 1，无扰动空间"}
    rest = {p: totals0[p] - scores[p][dim] * w0 for p in scores}

    def value(p, t):
        return scores[p][dim] * t + rest[p] * (1.0 - t) / (1.0 - w0)

    ups, downs = [], []
    for p in sorted(scores):
        if p == top:
            continue
        f0 = value(top, 0.0) - value(p, 0.0)
        f1 = value(top, 1.0) - value(p, 1.0)
        denom = f0 - f1
        if abs(denom) < EPS:
            continue
        t = f0 / denom
        if -EPS <= t <= 1.0 + EPS and abs(t - w0) > EPS:
            t = min(1.0, max(0.0, t))
            (ups if t > w0 else downs).append((t, p))

    def target(root, direction):
        t = root + NUDGE if direction == "up" else root - NUDGE
        return ranking({p: value(p, t) for p in scores})[0]

    down_flip = None
    if downs:
        t, _ = max(downs)
        down_flip = {"threshold": t, "flip_if": f"{dim} 权重降至 {t:.6f} 以下",
                     "new_top": target(t, "down")}
    up_flip = None
    if ups:
        t, _ = min(ups)
        up_flip = {"threshold": t, "flip_if": f"{dim} 权重升至 {t:.6f} 以上",
                   "new_top": target(t, "up")}
    return {"down_flip": down_flip, "up_flip": up_flip}


def analyze(pkg):
    weights_raw, scores = extract(pkg)
    weights = normalize(weights_raw)
    dims = sorted(weights)
    totals0 = totals_for(scores, weights)
    rank0 = ranking(totals0)
    top0 = rank0[0]
    if len(rank0) > 1 and abs(totals0[rank0[0]] - totals0[rank0[1]]) < EPS:
        raise PrecheckError(
            f"基线首选并列（{rank0[0]} 与 {rank0[1]} 同分），无法定义翻转；"
            "请先由模型裁决打破平局")

    scenarios = []

    def add_scenario(name, dimension, direction, factor, w):
        totals = totals_for(scores, w)
        rnk = ranking(totals)
        scenarios.append({
            "name": name, "dimension": dimension, "direction": direction,
            "factor": factor, "weights": w, "totals": totals,
            "ranking": rnk, "top": rnk[0], "flipped": rnk[0] != top0,
        })

    for d in dims:
        add_scenario(f"{d}_down", d, "down", 0.5, perturb(weights, d, 0.5))
        add_scenario(f"{d}_up", d, "up", 1.5, perturb(weights, d, 1.5))
    add_scenario("equal_weights", "equal_weights", "equal", None,
                 {d: 1.0 / len(dims) for d in dims})

    thresholds = []
    for d in dims:
        th = flip_thresholds(scores, weights, totals0, d, top0)
        th["dimension"] = d
        thresholds.append(th)

    triggers = [{
        "scenario": s["name"], "dimension": s["dimension"],
        "direction": s["direction"], "new_top": s["top"],
    } for s in scenarios if s["flipped"]]

    verdict = {
        "status": "sensitive" if triggers else "robust",
        "triggers": triggers,
        "note": ("首选在部分权重扰动下翻转，结论对权重取值敏感，交付时必须"
                 "附带翻转点说明" if triggers else
                 "全部 ±50% 单权重扰动与等权重档下首选不变，结论对权重稳健"),
    }
    return {
        "tool": "decision-forge-qc/sensitivity.py",
        "case_id": pkg.get("case_id"),
        "baseline": {"weights": weights, "totals": totals0,
                     "ranking": rank0, "top": top0},
        "scenarios": scenarios,
        "thresholds": thresholds,
        "verdict": verdict,
    }


def fmt(x):
    return f"{x:.6f}"


def render_markdown(result):
    b = result["baseline"]
    lines = ["# 敏感性分析报告（decision-forge-qc / sensitivity.py）", ""]
    lines.append(f"- case_id: {result['case_id']}")
    lines.append(f"- 基线首选: {b['top']}")
    lines.append(f"- 稳健性 verdict: **{result['verdict']['status']}** — {result['verdict']['note']}")
    lines.append("")
    lines.append("## 基线权重与加权总分")
    lines.append("")
    dims = sorted(b["weights"])
    lines.append("| 维度 | 权重 |")
    lines.append("|------|------|")
    for d in dims:
        lines.append(f"| {d} | {fmt(b['weights'][d])} |")
    lines.append("")
    lines.append("| 排名 | 方案 | 加权总分 |")
    lines.append("|------|------|----------|")
    for i, pid in enumerate(b["ranking"], 1):
        lines.append(f"| {i} | {pid} | {fmt(b['totals'][pid])} |")
    lines.append("")
    lines.append("## 扰动情景（每权重 ±50%，其余归一；另含等权重档）")
    lines.append("")
    lines.append("| 情景 | 扰动维度 | 方向 | 首选 | 是否翻转 | 各方案总分 |")
    lines.append("|------|---------|------|------|---------|-----------|")
    for s in result["scenarios"]:
        tstr = "; ".join(f"{p}={fmt(s['totals'][p])}" for p in s["ranking"])
        lines.append(f"| {s['name']} | {s['dimension']} | {s['direction']} "
                     f"| {s['top']} | {'**是**' if s['flipped'] else '否'} | {tstr} |")
    lines.append("")
    lines.append("## 翻转阈值（解析解，其余权重保持相对比例）")
    lines.append("")
    lines.append("| 维度 | 下调翻转 | 上调翻转 |")
    lines.append("|------|---------|---------|")
    for th in result["thresholds"]:
        d = th["down_flip"]
        u = th["up_flip"]
        ds = (f"阈值 {fmt(d['threshold'])} → {d['new_top']}" if d else "（[0,1] 内无）")
        us = (f"阈值 {fmt(u['threshold'])} → {u['new_top']}" if u else "（[0,1] 内无）")
        lines.append(f"| {th['dimension']} | {ds} | {us} |")
    lines.append("")
    if result["verdict"]["triggers"]:
        lines.append("## 触发翻转的扰动")
        lines.append("")
        lines.append("| 情景 | 维度 | 方向 | 翻转后首选 |")
        lines.append("|------|------|------|-----------|")
        for t in result["verdict"]["triggers"]:
            lines.append(f"| {t['scenario']} | {t['dimension']} | {t['direction']} | {t['new_top']} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="权重扰动敏感性分析：one-at-a-time ±50% + 等权重档，输出排名表、"
                    "rank-flip 报告、翻转阈值与稳健性 verdict。"
                    "退出码 0=成功 / 2=输入错误 / 3=前置条件不满足。")
    ap.add_argument("--package", required=True,
                    help="decision_package.json 路径（读取其 weights 与 scores）")
    ap.add_argument("--outdir", default=".",
                    help="sensitivity.json / sensitivity.md 输出目录（默认当前目录）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 产物顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args(argv)

    try:
        pkg = load_json(args.package, "决策包文件")
    except InputError as e:
        print(f"输入错误: {e}", file=sys.stderr)
        return 2
    try:
        result = analyze(pkg)
    except PrecheckError as e:
        print(f"前置条件不满足: {e}", file=sys.stderr)
        return 3
    if args.note is not None:
        result["note"] = args.note

    outdir = Path(args.outdir)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "sensitivity.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        with open(outdir / "sensitivity.md", "w", encoding="utf-8") as f:
            md_text = render_markdown(result)
            if args.note is not None:
                md_text = f"> {args.note}\n\n" + md_text
            f.write(md_text)
    except OSError as e:
        print(f"输入错误: 无法写出报告到 {outdir}: {e}", file=sys.stderr)
        return 2

    v = result["verdict"]
    print(f"敏感性分析完成：verdict={v['status']}，触发扰动 {len(v['triggers'])} 项，"
          f"基线首选 {result['baseline']['top']}")
    for t in v["triggers"]:
        print(f"  翻转: 情景 {t['scenario']}（{t['dimension']}/{t['direction']}）"
              f"→ 新首选 {t['new_top']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
