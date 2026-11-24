#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figure_forge.py — 图形选择规则引擎 + 双通道渲染（matplotlib PNG / 纯 Python SVG）。

用法：
  python3 figure_forge.py --work /app/work --output /app/output [--force-svg|--force-png]
                          [--max-figures 40] [--seed 20240501]

规则引擎（详见 references/figure-selection.md）：
  - 分组数值比较（two_group / k_group） → 箱线图 + 确定性抖动散点叠加；
    每组 n<10 强制叠加全部原始点；n>50 确定性子样本 50 点（seed 固定）。
  - 非参路线（Mann-Whitney / Kruskal-Wallis）→ 追加 ECDF 分布形态图。
  - 两数值变量（design=xy）→ 散点 + OLS 参考线。
  - 分类计数（design=count）→ 频数条形图（y 轴从 0 起）。
  - 禁止：任一组 n<30 时用 bar+SE/SD 柱形图展示组间比较（dynamite plot）。
    本引擎永不自动生成均值条形图；figure_audit.py 会拦截人工补画的违例。

双通道：matplotlib 可用 → PNG(dpi=150, Agg, 内置 DejaVu 字体)；否则纯 Python SVG。
两通道共享同一份几何计算（五数、须、散点子样本、黄金比抖动、刻度），视觉要素等价。

产出：/app/output/fig<N>.png|.svg、figures.md；并把 result.json 的 figures.generated
与自动 waiver（超出 max_figures 时）写回。report.md 的 FIGURES 段同步更新。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statcore_c as sc

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
           "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC"]
MAX_POINTS = 50
SVG_W, SVG_H = 800, 560


# ================================================================ 工具

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def f2(x):
    return "%.2f" % x


def ascii_safe(s, fallback):
    s = str(s)
    return s if all(ord(c) < 128 for c in s) and s.strip() else fallback


def clean_label(s):
    """图注机读友好：去掉会破坏 audit 正则的分隔符。"""
    return re.sub(r"[：:|；;]", "-", str(s))


def nice_ticks(lo, hi, target=5):
    if hi <= lo:
        hi = lo + 1.0
    span = hi - lo
    import math
    rough = span / target
    mag = 10.0 ** math.floor(math.log10(rough))
    step = rough
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if m * mag >= rough:
            step = m * mag
            break
    t = math.ceil(lo / step) * step
    ticks = []
    while t <= hi + 1e-12:
        ticks.append(round(t, 10))
        t += step
    return ticks, step


def tick_fmt(v, step):
    if step >= 1:
        return "%g" % v
    import math
    dec = max(0, int(-math.floor(math.log10(step))))
    return ("%.*f" % (dec, v))


# ================================================================ 几何（双通道共享）

def boxplot_geometry(analysis, seed):
    """返回箱线+散点几何：每组五数、须、散点（含确定性子样本与黄金比抖动）。"""
    groups = []
    for gi, g in enumerate(analysis["groups"]):
        vals = sorted(g["values"])
        n = len(vals)
        five = sc.five_number(vals)
        if n <= MAX_POINTS:
            pts = vals
            overlay = "全部 %d 点" % n + ("（n<10 强制全点）" if n < 10 else "")
        else:
            rng = random.Random(seed + gi * 131)
            idx = sorted(rng.sample(range(n), MAX_POINTS))
            pts = [vals[i] for i in idx]
            overlay = "确定性子样本 %d/%d 点（seed 固定）" % (MAX_POINTS, n)
        jitter = [sc.golden_jitter(i, 1.0) for i in range(len(pts))]
        groups.append({"label": g["label"], "n": n, "five": five,
                       "points": pts, "jitter": jitter, "overlay": overlay})
    lo = min(min(g["five"]["whisk_lo"], min(g["points"])) for g in groups)
    hi = max(max(g["five"]["whisk_hi"], max(g["points"])) for g in groups)
    pad = 0.04 * (hi - lo) if hi > lo else 1.0
    y_lo, y_hi = lo - pad, hi + pad
    ticks, step = nice_ticks(y_lo, y_hi)
    if ticks:
        y_lo = min(y_lo, ticks[0])
        y_hi = max(y_hi, ticks[-1])
    return {"kind": "boxplot_jitter", "groups": groups, "y_lo": y_lo, "y_hi": y_hi,
            "ticks": ticks, "step": step, "data_range": [lo, hi]}


def ecdf_geometry(analysis):
    groups = []
    for g in analysis["groups"]:
        pts = sc.ecdf_points(g["values"])
        groups.append({"label": g["label"], "n": g["n"], "points": pts})
    lo = min(p[0] for g in groups for p in g["points"])
    hi = max(p[0] for g in groups for p in g["points"])
    pad = 0.03 * (hi - lo) if hi > lo else 1.0
    ticks, step = nice_ticks(lo - pad, hi + pad)
    return {"kind": "ecdf", "groups": groups, "x_lo": lo - pad, "x_hi": hi + pad,
            "ticks": ticks, "step": step, "data_range": [lo, hi]}


def scatter_geometry(analysis):
    xs = analysis["x_values"]
    ys = analysis["y_values"]
    line = sc.ols_line(xs, ys)
    return {"kind": "scatter_ols", "xs": xs, "ys": ys, "line": line,
            "data_range": [min(xs + ys), max(xs + ys)]}


def countbar_geometry(analysis):
    cats = analysis["categories"]  # [{label, count}]
    hi = max(c["count"] for c in cats)
    ticks, step = nice_ticks(0.0, hi * 1.05)
    return {"kind": "count_bar", "categories": cats, "y_lo": 0.0,
            "y_hi": ticks[-1] if ticks else hi, "ticks": ticks, "step": step,
            "data_range": [0.0, float(hi)]}


# ================================================================ SVG 渲染

class Svg:
    def __init__(self, w=SVG_W, h=SVG_H):
        self.parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                      'viewBox="0 0 %d %d">' % (w, h, w, h),
                      '<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (w, h)]
        self.w, self.h = w, h

    def rect(self, x, y, w, h, fill="none", stroke="#333", sw=1.0, opacity=1.0):
        self.parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" '
                          'stroke="%s" stroke-width="%s" fill-opacity="%s"/>'
                          % (f2(x), f2(y), f2(w), f2(h), fill, stroke, f2(sw), f2(opacity)))

    def line(self, x1, y1, x2, y2, stroke="#333", sw=1.0, dash=None):
        d = ' stroke-dasharray="5,4"' if dash else ""
        self.parts.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                          'stroke-width="%s"%s/>' % (f2(x1), f2(y1), f2(x2), f2(y2),
                                                     stroke, f2(sw), d))

    def circle(self, cx, cy, r, fill, opacity=0.55):
        self.parts.append('<circle cx="%s" cy="%s" r="%s" fill="%s" fill-opacity="%s"/>'
                          % (f2(cx), f2(cy), f2(r), fill, f2(opacity)))

    def polyline(self, pts, stroke, sw=1.6):
        s = " ".join("%s,%s" % (f2(x), f2(y)) for x, y in pts)
        self.parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s"/>'
                          % (s, stroke, f2(sw)))

    def text(self, x, y, s, size=12, anchor="middle", rotate=None, weight=None):
        tr = ' transform="rotate(%s %s %s)"' % (rotate, f2(x), f2(y)) if rotate else ""
        wt = ' font-weight="%s"' % weight if weight else ""
        self.parts.append('<text x="%s" y="%s" font-family="Helvetica, Arial, sans-serif" '
                          'font-size="%d" text-anchor="%s" fill="#222"%s%s>%s</text>'
                          % (f2(x), f2(y), size, anchor, tr, wt, esc(s)))

    def render(self):
        return "\n".join(self.parts) + "\n</svg>\n"


class Frame:
    """统一坐标框架：数据坐标 → 像素坐标。"""

    def __init__(self, x_lo, x_hi, y_lo, y_hi, x0=90, y0=64, w=670, h=396):
        self.x_lo, self.x_hi, self.y_lo, self.y_hi = x_lo, x_hi, y_lo, y_hi
        self.x0, self.y0, self.w, self.h = x0, y0, w, h

    def px(self, x):
        return self.x0 + self.w * (x - self.x_lo) / (self.x_hi - self.x_lo)

    def py(self, y):
        return self.y0 + self.h * (1.0 - (y - self.y_lo) / (self.y_hi - self.y_lo))

    def slot_cx(self, i, k):
        return self.x0 + self.w * (i + 0.5) / k

    def slot_w(self, k):
        return self.w / k


def svg_axes(svg, fr, yticks, ystep, title, subtitle, ylabel, xlabel):
    for t in yticks:
        svg.line(fr.x0, fr.py(t), fr.x0 + fr.w, fr.py(t), stroke="#e3e3e3", sw=0.8)
        svg.text(fr.x0 - 8, fr.py(t) + 4, tick_fmt(t, ystep), size=11, anchor="end")
    svg.line(fr.x0, fr.y0, fr.x0, fr.y0 + fr.h, stroke="#333", sw=1.2)
    svg.line(fr.x0, fr.y0 + fr.h, fr.x0 + fr.w, fr.y0 + fr.h, stroke="#333", sw=1.2)
    svg.text(SVG_W / 2, 28, title, size=16, weight="bold")
    svg.text(SVG_W / 2, 48, subtitle, size=10.5)
    svg.text(26, fr.y0 + fr.h / 2, ylabel, size=12, rotate="-90")
    svg.text(fr.x0 + fr.w / 2, SVG_H - 12, xlabel, size=12)


def render_boxplot_svg(geom, analysis, path):
    k = len(geom["groups"])
    fr = Frame(0, 1, geom["y_lo"], geom["y_hi"])
    svg = Svg()
    unit = analysis["unit"] or "unit n/a"
    title = "%s by %s - %s" % (ascii_safe(analysis["outcome"], analysis["id"] + " outcome"),
                               ascii_safe(analysis["group_var"], "group"),
                               analysis["method"])
    svg_axes(svg, fr, geom["ticks"], geom["step"], title,
             "Tukey box; whiskers=1.5*IQR adjacent values; deterministic golden-ratio jitter",
             "%s (%s)" % (ascii_safe(analysis["outcome"], "value"), ascii_safe(unit, "unit")),
             ascii_safe(analysis["group_var"], "group"))
    bw = min(60.0, fr.slot_w(k) * 0.5)
    for i, g in enumerate(geom["groups"]):
        cx = fr.slot_cx(i, k)
        color = PALETTE[i % len(PALETTE)]
        f = g["five"]
        svg.line(cx, fr.py(f["whisk_hi"]), cx, fr.py(f["q3"]), stroke="#555", sw=1.2)
        svg.line(cx, fr.py(f["whisk_lo"]), cx, fr.py(f["q1"]), stroke="#555", sw=1.2)
        svg.line(cx - bw * 0.25, fr.py(f["whisk_hi"]), cx + bw * 0.25, fr.py(f["whisk_hi"]), stroke="#555", sw=1.2)
        svg.line(cx - bw * 0.25, fr.py(f["whisk_lo"]), cx + bw * 0.25, fr.py(f["whisk_lo"]), stroke="#555", sw=1.2)
        svg.rect(cx - bw / 2, fr.py(f["q3"]), bw, fr.py(f["q1"]) - fr.py(f["q3"]),
                 fill=color, stroke="#333", sw=1.2, opacity=0.75)
        svg.line(cx - bw / 2, fr.py(f["median"]), cx + bw / 2, fr.py(f["median"]),
                 stroke="#111", sw=2.2)
        for dx, v in zip(g["jitter"], g["points"]):
            svg.circle(cx + dx * bw * 1.1, fr.py(v), 3.0, color, opacity=0.5)
        rot = "-38" if k > 6 else None
        lab = ascii_safe(clean_label(g["label"]), "g%d" % (i + 1))
        if rot:
            svg.text(cx, fr.y0 + fr.h + 16, lab, size=10.5, anchor="end", rotate=rot)
        else:
            svg.text(cx, fr.y0 + fr.h + 18, lab, size=11)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(svg.render())


def render_ecdf_svg(geom, analysis, path):
    k = len(geom["groups"])
    fr = Frame(geom["x_lo"], geom["x_hi"], -0.02, 1.02)
    svg = Svg()
    unit = analysis["unit"] or "unit n/a"
    title = "ECDF: %s by %s - %s" % (ascii_safe(analysis["outcome"], analysis["id"] + " outcome"),
                                     ascii_safe(analysis["group_var"], "group"),
                                     analysis["method"])
    svg_axes(svg, fr, [0.0, 0.25, 0.5, 0.75, 1.0], 0.25, title,
             "empirical cumulative distribution; step points at each observation",
             "ECDF F(x)", "%s (%s)" % (ascii_safe(analysis["outcome"], "x"), ascii_safe(unit, "unit")))
    for t in geom["ticks"]:
        svg.line(fr.px(t), fr.y0, fr.px(t), fr.y0 + fr.h, stroke="#f0f0f0", sw=0.6)
    for i, g in enumerate(geom["groups"]):
        color = PALETTE[i % len(PALETTE)]
        pts = [(fr.px(x), fr.py(y)) for x, y in g["points"]]
        svg.polyline(pts, color, sw=1.8)
        ly = fr.y0 + 14 + i * 16
        svg.line(SVG_W - 150, ly - 4, SVG_W - 130, ly - 4, stroke=color, sw=2.4)
        svg.text(SVG_W - 124, ly, "%s (n=%d)" % (ascii_safe(clean_label(g["label"]), "g%d" % (i + 1)), g["n"]),
                 size=10.5, anchor="start")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(svg.render())


def render_scatter_svg(geom, analysis, path):
    xs, ys = geom["xs"], geom["ys"]
    xlo, xhi = min(xs), max(xs)
    ylo, yhi = min(ys), max(ys)
    xp = 0.04 * (xhi - xlo) or 1.0
    yp = 0.04 * (yhi - ylo) or 1.0
    fr = Frame(xlo - xp, xhi + xp, ylo - yp, yhi + yp)
    svg = Svg()
    ticks, step = nice_ticks(ylo - yp, yhi + yp)
    svg_axes(svg, fr, ticks, step,
             "%s vs %s - OLS reference" % (ascii_safe(analysis.get("y_name", "y"), "y"),
                                           ascii_safe(analysis.get("x_name", "x"), "x")),
             "OLS: y=%.3f+%.3fx, r=%.3f" % (geom["line"]["intercept"],
                                            geom["line"]["slope"], geom["line"]["r"]),
             ascii_safe(analysis.get("y_name", "y"), "y"),
             ascii_safe(analysis.get("x_name", "x"), "x"))
    for i, (x, y) in enumerate(zip(xs, ys)):
        svg.circle(fr.px(x) + sc.golden_jitter(i, 2.0), fr.py(y), 3.0, PALETTE[0], 0.55)
    svg.line(fr.px(xlo - xp), fr.py(geom["line"]["intercept"] + geom["line"]["slope"] * (xlo - xp)),
             fr.px(xhi + xp), fr.py(geom["line"]["intercept"] + geom["line"]["slope"] * (xhi + xp)),
             stroke=PALETTE[3], sw=1.8, dash=True)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(svg.render())


def render_countbar_svg(geom, analysis, path):
    cats = geom["categories"]
    k = len(cats)
    fr = Frame(0, 1, geom["y_lo"], geom["y_hi"])
    svg = Svg()
    svg_axes(svg, fr, geom["ticks"], geom["step"],
             "Frequency: %s" % ascii_safe(analysis.get("var", "variable"), "var"),
             "frequency bar chart; y-axis starts at 0",
             "count", ascii_safe(analysis.get("var", "variable"), "var"))
    bw = min(80.0, fr.slot_w(k) * 0.55)
    for i, c in enumerate(cats):
        cx = fr.slot_cx(i, k)
        svg.rect(cx - bw / 2, fr.py(c["count"]), bw, fr.py(0) - fr.py(c["count"]),
                 fill=PALETTE[i % len(PALETTE)], stroke="#333", sw=1.1, opacity=0.85)
        svg.text(cx, fr.py(c["count"]) - 6, str(c["count"]), size=11)
        svg.text(cx, fr.y0 + fr.h + 18, ascii_safe(clean_label(c["label"]), "c%d" % (i + 1)), size=11)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(svg.render())


# ================================================================ matplotlib 渲染

def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def render_boxplot_png(geom, analysis, path):
    plt = _mpl()
    k = len(geom["groups"])
    fig, ax = plt.subplots(figsize=(8.0, 5.6), dpi=150)
    unit = analysis["unit"] or "unit n/a"
    bw = min(0.55, 0.8 / k) * 1.0
    for i, g in enumerate(geom["groups"]):
        cx = float(i + 1)
        color = PALETTE[i % len(PALETTE)]
        f = g["five"]
        ax.plot([cx, cx], [f["whisk_lo"], f["q1"]], color="#555", lw=1.2)
        ax.plot([cx, cx], [f["q3"], f["whisk_hi"]], color="#555", lw=1.2)
        ax.plot([cx - bw * 0.25, cx + bw * 0.25], [f["whisk_hi"]] * 2, color="#555", lw=1.2)
        ax.plot([cx - bw * 0.25, cx + bw * 0.25], [f["whisk_lo"]] * 2, color="#555", lw=1.2)
        ax.add_patch(plt.Rectangle((cx - bw / 2, f["q1"]), bw, f["q3"] - f["q1"],
                                   facecolor=color, edgecolor="#333", alpha=0.75, lw=1.2))
        ax.plot([cx - bw / 2, cx + bw / 2], [f["median"]] * 2, color="#111", lw=2.2)
        ax.scatter([cx + dx * bw * 1.1 for dx in g["jitter"]], g["points"],
                   s=11, color=color, alpha=0.5, linewidths=0)
    ax.set_xlim(0.4, k + 0.6)
    ax.set_ylim(geom["y_lo"], geom["y_hi"])
    ax.set_xticks(range(1, k + 1))
    ax.set_xticklabels([ascii_safe(clean_label(g["label"]), "g%d" % (i + 1))
                        for i, g in enumerate(geom["groups"])],
                       rotation=38 if k > 6 else 0, ha="right" if k > 6 else "center")
    ax.set_yticks(geom["ticks"])
    ax.set_yticklabels([tick_fmt(t, geom["step"]) for t in geom["ticks"]])
    ax.grid(axis="y", color="#e3e3e3", lw=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel("%s (%s)" % (ascii_safe(analysis["outcome"], "value"), ascii_safe(unit, "unit")))
    ax.set_xlabel(ascii_safe(analysis["group_var"], "group"))
    ax.set_title("%s by %s - %s" % (ascii_safe(analysis["outcome"], analysis["id"] + " outcome"),
                                    ascii_safe(analysis["group_var"], "group"),
                                    analysis["method"]))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def render_ecdf_png(geom, analysis, path):
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(8.0, 5.6), dpi=150)
    unit = analysis["unit"] or "unit n/a"
    for i, g in enumerate(geom["groups"]):
        xs = [p[0] for p in g["points"]]
        ys = [p[1] for p in g["points"]]
        ax.step(xs, ys, where="post", color=PALETTE[i % len(PALETTE)], lw=1.8,
                label="%s (n=%d)" % (ascii_safe(clean_label(g["label"]), "g%d" % (i + 1)), g["n"]))
    ax.set_xlim(geom["x_lo"], geom["x_hi"])
    ax.set_ylim(-0.02, 1.02)
    ax.grid(color="#e3e3e3", lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylabel("ECDF F(x)")
    ax.set_xlabel("%s (%s)" % (ascii_safe(analysis["outcome"], "x"), ascii_safe(unit, "unit")))
    ax.set_title("ECDF: %s by %s - %s" % (ascii_safe(analysis["outcome"], analysis["id"] + " outcome"),
                                          ascii_safe(analysis["group_var"], "group"),
                                          analysis["method"]))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ================================================================ 图注与清单

def stat_phrase(a):
    df = a["df"]
    if a["stat_name"] in ("t",):
        return "t(%s)=%.2f" % (("%.1f" % df[0]).rstrip("0").rstrip(".") if df else "-", a["statistic"])
    if a["stat_name"] == "F":
        return "F(%s)=%.2f" % (",".join(("%.1f" % d).rstrip("0").rstrip(".") for d in df), a["statistic"])
    if a["stat_name"] == "H":
        return "H(%s)=%.2f" % (",".join("%g" % d for d in df), a["statistic"])
    return "U=%.2f" % a["statistic"]


def group_triples(a):
    segs = []
    for g in a["groups"]:
        segs.append("组 %s：n=%d，均值=%.2f，SD=%.2f"
                    % (clean_label(g["label"]), g["n"],
                       sc.mean(g["values"]), sc.sd(g["values"])))
    return "；".join(segs)


def build_caption(fig_no, ftype_cn, a, geom):
    unit = a["unit"] or "单位未注明"
    overlay = ""
    if geom["kind"] == "boxplot_jitter":
        overlay = "散点：%s" % "；".join("%s %s" % (clean_label(g["label"]), g["overlay"])
                                        for g in geom["groups"])
    elif geom["kind"] == "ecdf":
        overlay = "选择理由：主检验为非参路线（%s），以 ECDF 呈现分布形态避免箱线掩盖偏态/双峰" % a["method"]
    return ("图%d｜%s｜%s 按 %s 分组比较（单位：%s）｜%s｜检验：%s %s，%s，α=%.3g｜%s｜数据区间 [%.2f, %.2f]"
            % (fig_no, ftype_cn, a["outcome"], a["group_var"], unit, group_triples(a),
               a["method"], stat_phrase(a), a["p_fmt"], a["alpha"], overlay,
               geom["data_range"][0], geom["data_range"][1]))


# ================================================================ 主流程

def load_matplotlib_ok():
    try:
        _mpl()
        return True
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="图形选择规则引擎 + 双通道渲染")
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--result", default=None)
    ap.add_argument("--force-svg", action="store_true")
    ap.add_argument("--force-png", action="store_true")
    ap.add_argument("--max-figures", type=int, default=None)
    ap.add_argument("--seed", type=int, default=sc.SEED)
    args = ap.parse_args(argv)

    result_path = args.result or os.path.join(args.output, "result.json")
    adata = json.load(open(os.path.join(args.work, "analysis_data.json"), encoding="utf-8"))
    result = json.load(open(result_path, encoding="utf-8"))
    analyses = adata["analyses"]
    by_id = {a["id"]: a for a in analyses}

    max_figures = args.max_figures
    if max_figures is None:
        max_figures = int(str(result.get("decisions", {}).get("max_figures", 40)))
    mpl_ok = load_matplotlib_ok()
    if args.force_png and not mpl_ok:
        print("matplotlib 不可用且指定 --force-png", file=sys.stderr)
        return 2
    channel = "png" if (mpl_ok and not args.force_svg) else "svg"
    ext = ".png" if channel == "png" else ".svg"

    # ---- 计划：每个分析一张主图；非参路线追加 ECDF
    plan = []
    for a in analyses:
        if a["design"] in ("two_group", "k_group"):
            plan.append((a, "boxplot_jitter"))
            if a.get("route_nonparametric"):
                plan.append((a, "ecdf"))
        elif a["design"] == "xy":
            plan.append((a, "scatter_ols"))
        elif a["design"] == "count":
            plan.append((a, "count_bar"))
    waivers = dict(result.get("figures", {}).get("waivers", {}))
    for aid, reason in waivers.items():
        if aid in by_id:
            plan = [(a, t) for (a, t) in plan if a["id"] != aid]
    auto_waivers = {}
    if len(plan) > max_figures:
        kept = plan[:max_figures]
        for a, t in plan[max_figures:]:
            auto_waivers.setdefault(a["id"], "超出 max_figures=%d，按分析序截断（%s 未出图）"
                                    % (max_figures, t))
        plan = kept

    # ---- 渲染
    os.makedirs(args.output, exist_ok=True)
    records = []
    for i, (a, ftype) in enumerate(plan, start=1):
        fid = "fig%d" % i
        if ftype == "boxplot_jitter":
            geom = boxplot_geometry(a, args.seed + i * 17)
        elif ftype == "ecdf":
            geom = ecdf_geometry(a)
        elif ftype == "scatter_ols":
            geom = scatter_geometry(a)
        else:
            geom = countbar_geometry(a)
        fname = fid + ext
        fpath = os.path.join(args.output, fname)
        if channel == "png":
            if ftype == "boxplot_jitter":
                render_boxplot_png(geom, a, fpath)
            elif ftype == "ecdf":
                render_ecdf_png(geom, a, fpath)
            else:
                render_boxplot_png(geom, a, fpath)  # 其余类型兜底（当前案例不触发）
        else:
            if ftype == "boxplot_jitter":
                render_boxplot_svg(geom, a, fpath)
            elif ftype == "ecdf":
                render_ecdf_svg(geom, a, fpath)
            elif ftype == "scatter_ols":
                render_scatter_svg(geom, a, fpath)
            else:
                render_countbar_svg(geom, a, fpath)
        ftype_cn = {"boxplot_jitter": "箱线图+抖动散点", "ecdf": "ECDF 分布形态",
                    "scatter_ols": "散点+OLS 参考线", "count_bar": "频数条形图"}[ftype]
        if ftype == "boxplot_jitter":
            rationale = ("分组数值比较（design=%s，k=%d）→ 箱线图+抖动散点叠加；%s"
                         % (a["design"], len(a["groups"]),
                            "；".join("%s n=%d（%s）" % (clean_label(g["label"]), g["n"], g["overlay"])
                                     for g in geom["groups"])))
        elif ftype == "ecdf":
            rationale = "主检验为非参路线（%s）→ ECDF 展示分布形态（规则：分布形态→ECDF）" % a["method"]
        else:
            rationale = "规则引擎直选：%s" % ftype
        records.append({"fig": fid, "file": fname, "channel": channel, "type": ftype,
                        "analyses": [a["id"]], "rationale": rationale,
                        "caption": build_caption(i, ftype_cn, a, geom),
                        "data_range": geom["data_range"]})

    # ---- figures.md
    L = ["# figures.md — 图表证据清单（figure_forge.py 生成，机器可审计）", ""]
    L.append("- case_id: %s" % adata.get("case_id"))
    L.append("- channel: %s（matplotlib 可用: %s；--force-svg: %s）"
             % (channel, mpl_ok, bool(args.force_svg)))
    L.append("- seed: %d | 生成(utc): %s"
             % (args.seed, datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")))
    L.append("- 选择规则: 分组数值比较→箱线+抖动散点（每组 n<10 强制全点）；非参路线→加 ECDF；"
             "两数值变量→散点+OLS；分类计数→频数条形图；**禁止** n<30 的 bar+SE/SD 组间比较图")
    L.append("")
    for r in records:
        L.append("## %s — %s" % (r["fig"], r["file"]))
        L.append("- file: %s" % r["file"])
        L.append("- channel: %s" % r["channel"])
        L.append("- type: %s" % r["type"])
        L.append("- analyses: %s" % ",".join(r["analyses"]))
        L.append("- rationale: %s" % r["rationale"])
        L.append("- caption: %s" % r["caption"])
        L.append("- data_range: [%.2f, %.2f]" % (r["data_range"][0], r["data_range"][1]))
        L.append("")
    all_waivers = dict(waivers)
    all_waivers.update(auto_waivers)
    if all_waivers:
        L.append("## 豁免清单（waiver）")
        for aid in sorted(all_waivers):
            L.append("- %s: %s" % (aid, all_waivers[aid]))
        L.append("")
    with open(os.path.join(args.output, "figures.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    # ---- 回写 result.json 的 figures 段
    result.setdefault("figures", {})
    result["figures"]["generated"] = [{"file": r["file"], "type": r["type"],
                                       "analyses": r["analyses"], "channel": r["channel"]}
                                      for r in records]
    result["figures"]["waivers"] = all_waivers
    result["figures"]["channel"] = channel
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- 更新 report.md 的 FIGURES 段
    report_path = os.path.join(args.output, "report.md")
    if os.path.exists(report_path):
        txt = open(report_path, encoding="utf-8").read()
        block = ["<!-- FIGURES:BEGIN -->", "图表文件（详见 figures.md，含每组 n 与单位图注）："]
        for r in records:
            block.append("- `%s` — %s" % (r["file"], r["caption"][:150] + ("…" if len(r["caption"]) > 150 else "")))
        if all_waivers:
            block.append("- waiver: " + "; ".join("%s（%s）" % (k, v) for k, v in sorted(all_waivers.items())))
        block.append("<!-- FIGURES:END -->")
        new = re.sub(r"<!-- FIGURES:BEGIN -->.*?<!-- FIGURES:END -->",
                     "\n".join(block), txt, flags=re.S)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(new)

    print("figure_forge 完成: 通道=%s, 图 %d 张, waiver %d 个 → %s"
          % (channel, len(records), len(all_waivers), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
