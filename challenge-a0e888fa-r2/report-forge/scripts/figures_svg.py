#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figures_svg.py — 手写 SVG 图表生成器（纯标准库、确定性输出）。

无第三方依赖、无随机 id、无时间戳；坐标与浮点全部固定格式，产物可 diff、可直接浏览。
图表类型选择依据 references/figure_choice.md：
  分布 -> 直方图；构成 -> 堆叠条形图；对比 -> 条形图；缺失分类 -> 分组条形图。
数据为空或不足时不出图，在 figures_index.json 的 skipped 中如实记录原因（诚实降级）。

退出码：0 正常完成（含全部图表被跳过的情形）；2 用法 / IO 错误。
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fill_report as fr

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#EECA3B", "#B279A2"]
AXIS = "#333333"
GRID = "#dddddd"
W, H = 640, 420
ML, MR, MT, MB = 70, 24, 52, 96

RATIONALE_HIST = "该指标为连续数值型汇总列，需观察取值分布与离群迹象；依据 figure_choice.md「分布 → 直方图」。"
RATIONALE_MISSING = "缺失按字段分类计数，属于分类计数对比；依据 figure_choice.md「缺失分类 → 分组条形图」。"
RATIONALE_ISSUES = "字段问题数为离散计数对比；依据 figure_choice.md「对比 → 条形图」。"
RATIONALE_ACTIONS = "展示各类处理动作在全部变更记录中的构成；依据 figure_choice.md「构成 → 堆叠条形图」。"


def fmt(v):
    return fr.fmt_num(v)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def text_width_est(s, size):
    """粗略宽度估计：CJK 字符按 1em、其余按 0.56em。"""
    return sum(1.0 if ord(ch) > 127 else 0.56 for ch in str(s)) * size


def nice_step(raw):
    if raw <= 0 or not math.isfinite(raw):
        return 1.0
    exp = math.floor(math.log10(raw))
    base = raw / (10 ** exp)
    for b in (1, 2, 2.5, 5, 10):
        if base <= b + 1e-12:
            return b * (10 ** exp)
    return 10 ** (exp + 1)


class Canvas:
    def __init__(self, w=W, h=H):
        self.w = w
        self.h = h
        self.p = []

    def rect(self, x, y, w, h, fill, stroke="none", sw=0):
        self.p.append(
            f"<rect x='{fmt(x)}' y='{fmt(y)}' width='{fmt(w)}' height='{fmt(h)}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{fmt(sw)}'/>")

    def line(self, x1, y1, x2, y2, stroke=AXIS, sw=1):
        self.p.append(
            f"<line x1='{fmt(x1)}' y1='{fmt(y1)}' x2='{fmt(x2)}' y2='{fmt(y2)}' "
            f"stroke='{stroke}' stroke-width='{fmt(sw)}'/>")

    def text(self, x, y, s, size=11, anchor="middle", rotate=None, fill=AXIS, weight="normal"):
        tr = f" transform='rotate({fmt(rotate)} {fmt(x)} {fmt(y)})'" if rotate is not None else ""
        self.p.append(
            f"<text x='{fmt(x)}' y='{fmt(y)}' font-size='{fmt(size)}' text-anchor='{anchor}' "
            f"fill='{fill}' font-family='Helvetica,Arial,sans-serif' font-weight='{weight}'{tr}>"
            f"{esc(s)}</text>")

    def svg(self):
        head = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{self.w}' height='{self.h}' "
                f"viewBox='0 0 {self.w} {self.h}'>")
        return head + "\n" + "\n".join(self.p) + "\n</svg>\n"


def draw_y_axis(c, y_max, y_label):
    plot_top, plot_bottom, plot_left, plot_right = MT, H - MB, ML, W - MR
    step = nice_step(y_max / 4.0)
    top = math.ceil(y_max / step - 1e-9) * step
    if top <= 0:
        top = step
    n = int(round(top / step))
    for k in range(n + 1):
        v = k * step
        y = plot_bottom - (v / top) * (plot_bottom - plot_top)
        c.line(plot_left, y, plot_right, y, stroke=GRID, sw=1)
        c.text(plot_left - 8, y + 4, fmt(v), size=10, anchor="end")
    c.line(plot_left, plot_top, plot_left, plot_bottom)
    c.line(plot_left, plot_bottom, plot_right, plot_bottom)
    c.text(16, (plot_top + plot_bottom) / 2, y_label, size=11, rotate=-90)
    return top


def grouped_bar_svg(title, categories, series, y_label):
    """series: [(名称, [各类别取值]), ...]，单系列且名称为空时不画图例。"""
    c = Canvas()
    c.text(W / 2, 28, title, size=15, weight="bold")
    y_max = max((max(vals) for _, vals in series if vals), default=0)
    y_max = max(y_max, 1)
    top = draw_y_axis(c, y_max, y_label)
    plot_w = W - ML - MR
    n = len(categories)
    m = len(series)
    slot = plot_w / n
    bar_w = min(30.0, (slot * 0.72) / m)
    for i, cat in enumerate(categories):
        cx = ML + slot * (i + 0.5)
        for j, (_name, vals) in enumerate(series):
            v = vals[i]
            bh = (v / top) * (H - MB - MT)
            x = cx + (j - (m - 1) / 2.0) * (bar_w + 3) - bar_w / 2
            c.rect(x, H - MB - bh, bar_w, bh, PALETTE[j % len(PALETTE)])
            c.text(x + bar_w / 2, H - MB - bh - 4, fmt(v), size=9)
        c.text(cx, H - MB + 16, cat, size=10, rotate=-30, anchor="end")
    show_legend = not (m == 1 and series[0][0] == "")
    if show_legend:
        lx = ML
        for j, (name, _vals) in enumerate(series):
            c.rect(lx, H - 22, 10, 10, PALETTE[j % len(PALETTE)])
            c.text(lx + 15, H - 13, name, size=10, anchor="start")
            lx += 15 + text_width_est(name, 10) + 30
    return c.svg()


def histogram_bins(values, target_bins=6):
    lo, hi = min(values), max(values)
    if lo == hi:
        step = nice_step(abs(lo) * 0.1 or 1.0)
        start = lo - step
    else:
        step = nice_step((hi - lo) / target_bins)
        start = math.floor(lo / step) * step
    nb = max(1, int(math.ceil((hi - start) / step - 1e-9)))
    counts = [0] * nb
    for v in values:
        idx = int((v - start) / step + 1e-9)
        idx = min(max(idx, 0), nb - 1)
        counts[idx] += 1
    labels = [f"{fmt(start + k * step)}–{fmt(start + (k + 1) * step)}" for k in range(nb)]
    return labels, counts


def stacked_h_svg(title, segments, x_label="笔数"):
    """segments: [(标签, 数值)]，单条水平堆叠条 + 图例。"""
    c = Canvas()
    c.text(W / 2, 28, title, size=15, weight="bold")
    total = sum(v for _, v in segments)
    plot_top, plot_bottom = MT + 40, MT + 110
    bar_h = plot_bottom - plot_top
    x0, x1 = ML, W - MR
    scale = (x1 - x0) / total
    x = x0
    for j, (_label, v) in enumerate(segments):
        wseg = v * scale
        c.rect(x, plot_top, wseg, bar_h, PALETTE[j % len(PALETTE)], stroke="#ffffff", sw=1)
        if wseg > 30:
            c.text(x + wseg / 2, (plot_top + plot_bottom) / 2 + 4, fmt(v),
                   size=12, fill="#ffffff", weight="bold")
        x += wseg
    step = nice_step(total / 5.0)
    k = 0
    while k * step <= total + 1e-9:
        v = k * step
        xv = x0 + v * scale
        c.line(xv, plot_bottom, xv, plot_bottom + 5)
        c.text(xv, plot_bottom + 18, fmt(v), size=10)
        k += 1
    c.line(x0, plot_bottom, x1, plot_bottom)
    c.text((x0 + x1) / 2, plot_bottom + 34, x_label, size=11)
    ly = plot_bottom + 62
    for j, (label, v) in enumerate(segments):
        c.rect(ML, ly - 10, 10, 10, PALETTE[j % len(PALETTE)])
        c.text(ML + 16, ly - 1, f"{label}：{fmt(v)} 笔（{fmt(round(100.0 * v / total, 2))}%）",
               size=11, anchor="start")
        ly += 22
    return c.svg()


def rel_to(path, base_dir):
    return os.path.relpath(str(Path(path).resolve()), str(Path(base_dir).resolve()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="从清洗产物生成 figures/*.svg 与 figures_index.json")
    ap.add_argument("--cleaned", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--out-dir", required=True, help="SVG 输出目录，如 /app/output/figures")
    ap.add_argument("--index", required=True, help="figures_index.json 输出路径")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = Path(args.index)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_dir = index_path.resolve().parent

    stats = fr.compute_stats(args.cleaned, args.ledger)
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    fields, rows = fr.read_csv_rows(args.cleaned)

    figures = []
    skipped = []

    # 1) 分布 → 直方图（字段清单由 summary.json 的 histogram_fields 配置）
    for field in summary.get("histogram_fields", []):
        if field not in fields:
            skipped.append({"target": f"histogram:{field}",
                            "reason": f"字段 {field} 不在 cleaned.csv 中"})
            continue
        vals = []
        bad = 0
        for r in rows:
            v = r.get(field)
            if fr.is_missing(v):
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                bad += 1
        if len(vals) < 3:
            skipped.append({"target": f"histogram:{field}",
                            "reason": f"有效数值仅 {len(vals)} 个（<3），不足以观察分布，不出图"})
            continue
        labels, counts = histogram_bins(vals)
        name = f"fig_hist_{field}.svg"
        svg = grouped_bar_svg(f"{field} 分布直方图", labels, [("", counts)], y_label="频数")
        (out_dir / name).write_text(svg, encoding="utf-8")
        note = f"；另忽略无法解析为数值的单元格 {bad} 个" if bad else ""
        figures.append({
            "file": rel_to(out_dir / name, index_dir),
            "kind": "histogram",
            "kind_label": "直方图",
            "title": f"{field} 分布直方图",
            "rationale": RATIONALE_HIST,
            "caption": f"基于 cleaned.csv 中 {field} 列 {len(vals)} 个非缺失数值绘制{note}。",
        })

    # 2) 缺失分类 → 分组条形图
    if stats["missing_values_total"] > 0:
        cats = stats["fields"]
        missing_vals = [stats["missing_by_field"][f] for f in cats]
        present_vals = [stats["total_rows"] - stats["missing_by_field"][f] for f in cats]
        name = "fig_missing_by_field.svg"
        svg = grouped_bar_svg("各字段缺失 / 非缺失单元格计数", cats,
                              [("缺失", missing_vals), ("非缺失", present_vals)],
                              y_label="单元格数")
        (out_dir / name).write_text(svg, encoding="utf-8")
        figures.append({
            "file": rel_to(out_dir / name, index_dir),
            "kind": "grouped_bar",
            "kind_label": "分组条形图",
            "title": "各字段缺失 / 非缺失单元格计数",
            "rationale": RATIONALE_MISSING,
            "caption": f"cleaned.csv 共 {stats['total_rows']} 行 × {stats['total_fields']} 字段，"
                       f"缺失单元格总数 {stats['missing_values_total']}。",
        })
    else:
        skipped.append({"target": "missing_by_field",
                        "reason": "cleaned.csv 缺失单元格总数为 0，无缺失可展示，不出图"})

    # 3) 字段问题对比 → 条形图
    fic = stats["field_issue_counts"]
    if fic:
        cats = sorted(fic, key=lambda x: (x == "*", x))
        labels = [fr.field_label(f) for f in cats]
        vals = [fic[f] for f in cats]
        name = "fig_field_issues.svg"
        svg = grouped_bar_svg("各字段问题条数（源自 ledger.csv）", labels,
                              [("", vals)], y_label="条数")
        (out_dir / name).write_text(svg, encoding="utf-8")
        figures.append({
            "file": rel_to(out_dir / name, index_dir),
            "kind": "bar",
            "kind_label": "条形图",
            "title": "各字段问题条数",
            "rationale": RATIONALE_ISSUES,
            "caption": f"ledger.csv 共 {stats['change_records']} 条变更记录，按字段归并计数。",
        })
    else:
        skipped.append({"target": "field_issues",
                        "reason": "ledger.csv 无任何变更记录，无字段问题可展示，不出图"})

    # 4) 处理动作构成 → 堆叠条形图
    ac = stats["action_counts"]
    if ac:
        segs = [(fr.ACTION_LABELS.get(a, a), ac[a]) for a in sorted(ac)]
        name = "fig_action_composition.svg"
        svg = stacked_h_svg("处理动作构成（源自 ledger.csv）", segs)
        (out_dir / name).write_text(svg, encoding="utf-8")
        figures.append({
            "file": rel_to(out_dir / name, index_dir),
            "kind": "stacked_bar",
            "kind_label": "堆叠条形图",
            "title": "处理动作构成",
            "rationale": RATIONALE_ACTIONS,
            "caption": f"ledger.csv 共 {stats['change_records']} 条变更记录，按动作类型归并。",
        })
    else:
        skipped.append({"target": "action_composition",
                        "reason": "ledger.csv 无任何变更记录，无动作构成可展示，不出图"})

    index = {
        "version": "1.0",
        "figure_count": len(figures),
        "figures": figures,
        "skipped": skipped,
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[figures_svg] 生成 {len(figures)} 张图，跳过 {len(skipped)} 项 -> {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
