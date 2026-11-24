#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixtures.py —— SYNTHETIC EXAMPLE 夹具生成器（本 bundle 中唯一允许
使用 matplotlib 的脚本；仅在演示时运行，生成的二进制演示结束即删除）。

生成（写入 examples/output_demo/）：
  good.pdf              4 页全合规导出件：文字全部在页边距内、字号正常、
                        第 3 页带真实绘制的曲线图。
  bad.pdf               5 页埋雷导出件：
                          页数 5 ≠ 期望 4            -> R1
                          第 2 页完全空白             -> R2
                          第 3 页一个词冲出页面右缘    -> R3
                          第 4 页只有一行 3pt 小字     -> R4
                          第 5 页是期望图页但只剩图题  -> R5
  synthetic_figure.png  供 deck_spec.json 演示 minipptx 图片嵌入的插图。

所有文本用 matplotlib 在真实 PDF 坐标上绘制，确保 pdftotext -bbox 能看到
真实词框几何（已实测：poppler 对冲出页缘的词给出 xMax 超出页宽的 bbox）。
"""

import math
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import FigureCanvasPdf  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_demo")
PAGE = (8.5, 11)  # letter, 612 x 792 pt


def new_page():
    fig = Figure(figsize=PAGE)
    FigureCanvasPdf(fig)
    return fig


def make_good(out_dir):
    path = os.path.join(out_dir, "good.pdf")

    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(path) as pdf:
        # 第 1 页：标题页
        fig = new_page()
        fig.text(0.08, 0.88, "Synthetic Study: Drift-Compensated Sensor Array", fontsize=18)
        fig.text(0.08, 0.80, "SYNTHETIC EXAMPLE - group meeting talk, 8 minutes", fontsize=12)
        fig.text(0.08, 0.74, "Presenter: A. Researcher (synthetic persona)", fontsize=12)
        pdf.savefig(fig)

        # 第 2 页：方法要点
        fig = new_page()
        fig.text(0.08, 0.92, "Approach (synthetic)", fontsize=14)
        for i, line in enumerate([
            "- 24-channel humidity sensor array, low-cost polymer film",
            "- per-channel baseline drift estimated every 6 hours",
            "- compensation: two-point recalibration against reference cell",
            "- evaluation: 21-day continuous run, 3 replicate arrays",
        ]):
            fig.text(0.10, 0.84 - 0.06 * i, line, fontsize=11)
        pdf.savefig(fig)

        # 第 3 页：图页（真实绘制的曲线）
        fig = new_page()
        fig.text(0.08, 0.93, "Results: drift compensation halves the error", fontsize=14)
        ax = fig.add_axes([0.15, 0.35, 0.7, 0.45])
        xs = [i / 10.0 for i in range(0, 211)]
        raw = [1.2 + 0.9 * math.sin(x / 22.0) + 0.012 * x for x in xs]
        comp = [1.2 + 0.35 * math.sin(x / 22.0) for x in xs]
        ax.plot(xs, raw, lw=1.8, label="raw")
        ax.plot(xs, comp, lw=1.8, label="compensated")
        ax.set_xlabel("day")
        ax.set_ylabel("abs. error (%RH)")
        ax.grid(True)
        ax.legend(loc="upper left", fontsize=9)
        fig.text(0.08, 0.28, "Figure 1: absolute error over 21 days (synthetic data).", fontsize=10)
        pdf.savefig(fig)

        # 第 4 页：结论
        fig = new_page()
        fig.text(0.08, 0.92, "Takeaways (synthetic)", fontsize=14)
        for i, line in enumerate([
            "- median absolute error drops from 1.84 to 0.77 %RH",
            "- residual drift correlates with temperature swings",
            "- limitation: single site, single season, preliminary",
        ]):
            fig.text(0.10, 0.84 - 0.06 * i, line, fontsize=11)
        pdf.savefig(fig)
    return path


def make_bad(out_dir):
    path = os.path.join(out_dir, "bad.pdf")
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(path) as pdf:
        # 第 1 页：正常标题页
        fig = new_page()
        fig.text(0.08, 0.88, "Synthetic Study: Drift-Compensated Sensor Array", fontsize=18)
        fig.text(0.08, 0.80, "SYNTHETIC EXAMPLE - bad export fixture", fontsize=12)
        pdf.savefig(fig)

        # 第 2 页：完全空白 -> R2
        fig = new_page()
        pdf.savefig(fig)

        # 第 3 页：一个词冲出页面右缘 -> R3
        fig = new_page()
        fig.text(0.08, 0.88, "Results (synthetic)", fontsize=14)
        fig.text(0.08, 0.80, "- see the calibration curve below", fontsize=11)
        fig.text(0.90, 0.50,
                 "OVERFLOWWORDTHATRUNSPASTTHERIGHTPAGEEDGE",
                 fontsize=11, clip_on=False)
        pdf.savefig(fig)

        # 第 4 页：只有 3pt 小字 -> R4
        fig = new_page()
        fig.text(0.08, 0.80,
                 "tiny appendix text tiny appendix text tiny appendix text",
                 fontsize=3)
        fig.text(0.08, 0.76,
                 "more tiny words more tiny words more tiny words",
                 fontsize=3)
        pdf.savefig(fig)

        # 第 5 页：期望的图页只剩图题、图丢失 -> R5
        fig = new_page()
        fig.text(0.08, 0.50,
                 "Figure 3: calibration curve (image missing in export)",
                 fontsize=10)
        pdf.savefig(fig)
    return path


def make_figure_png(out_dir):
    path = os.path.join(out_dir, "synthetic_figure.png")
    fig = Figure(figsize=(4.8, 3.2), dpi=150)
    FigureCanvasPdf(fig)
    ax = fig.add_axes([0.14, 0.14, 0.80, 0.78])
    xs = [i / 10.0 for i in range(0, 211)]
    ax.plot(xs, [1.2 + 0.9 * math.sin(x / 22.0) + 0.012 * x for x in xs],
            lw=1.8, label="raw")
    ax.plot(xs, [1.2 + 0.35 * math.sin(x / 22.0) for x in xs],
            lw=1.8, label="compensated")
    ax.set_xlabel("day")
    ax.set_ylabel("abs. error (%RH)")
    ax.grid(True)
    ax.legend(fontsize=8)
    fig.savefig(path, format="png")
    return path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    good = make_good(OUT_DIR)
    bad = make_bad(OUT_DIR)
    png = make_figure_png(OUT_DIR)
    print("fixtures written:")
    for p in (good, bad, png):
        print("  {} ({} bytes)".format(p, os.path.getsize(p)))


if __name__ == "__main__":
    main()
