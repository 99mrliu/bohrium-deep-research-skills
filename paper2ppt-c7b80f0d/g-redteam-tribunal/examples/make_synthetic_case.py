#!/usr/bin/env python3
"""make_synthetic_case.py — 现场生成合成输入（非平台案例）。

生成到 --out 目录：
  paper.pdf            ≥4 页英文合成论文（纯文本 + 一张图，Figure 1/Table 1
                       caption、带单位数值、limitations 句；所有内容明显虚构）
  target-template.pptx 合成模板（title/content 占位符 + 16:9 主题）
  figs/Figure_1.png    与论文 Figure 1 一致的"已抽取"图片
  data.csv             合成数据（全部虚构）
  case.json            含 case_id 与官方 smoke 形态 output_contract
  task.md              受众 / 10 分钟 / ≤8 页 / 模板要求

用法：make_synthetic_case.py --out runs/d/input
退出码：0 成功；2 依赖缺失（matplotlib/python-pptx 缺一不可生成完整输入）。
"""
import argparse
import csv
import json
import os
import sys

PAPER_PAGES_TEXT = [
    # page 1
    ["Synthetic Gradient Harmonizers: A Fictional Study",
     "A. Synth, B. Fabric (Institute of Invented Metrics)",
     "Abstract. This fully synthetic paper studies fictional gradient",
     "harmonizers. All numbers in this paper are synthetic and invented.",
     "1. Introduction",
     "Fictional harmonizers reduce synthetic latency to 37 ms on the",
     "invented SynthBench suite with 128 samples.",
     "The synthetic training budget was 20 epochs for every run."],
    # page 2
    ["2. Method",
     "The fictional harmonizer has three synthetic stages.",
     "Each stage keeps the synthetic temperature at 4.2 K.",
     "The invented optimizer runs for 20 epochs on 128 samples.",
     "The method is described only for demonstration purposes."],
    # page 3（text 部分；另含一张图与 Figure 1 caption）
    ["3. Experiments",
     "The fictional harmonizer reaches 92.4 % synthetic accuracy.",
     "Latency stays at 37 ms on the invented benchmark.",
     "Table 1: Synthetic comparison of fictional methods, all invented."],
    # page 4
    ["4. Limitations",
     "A key limitation of this synthetic study is that only 2 datasets",
     "were used, both fictional. Future work remains entirely imaginary.",
     "5. Conclusion",
     "Fictional harmonizers are a promising synthetic direction."],
]
FIG1_CAPTION = "Figure 1: Schematic overview and synthetic accuracy curve, fully fictional."

TASK_MD = """# 合成任务书（fictional, 非平台案例）

- 受众：虚构研讨会评审（领域专家）
- 汇报时长：10 分钟
- 页数上限：≤8 页（max 8 slides）
- 模板要求：使用 target-template.pptx 的版式与主题
- 交付：可编辑 pptx + 渲染 PDF/PNG 预览 + 符合 case.json output_contract 的 result.json
"""

CASE_JSON = {
    "case_id": "synthetic-redteam-demo-001",
    "output_contract": [
        "case_id", "status", "editable_source", "export_artifact",
        "content_map", "compliance_checks", "exceptions",
    ],
}


def make_paper_pdf(path, fig_png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        for i, lines in enumerate(PAPER_PAGES_TEXT, 1):
            fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
            fig.patch.set_facecolor("white")
            y = 0.95
            for ln, line in enumerate(lines):
                size = 13 if (i == 1 and ln == 0) else 10
                weight = "bold" if (i == 1 and ln == 0) else "normal"
                fig.text(0.08, y, line, fontsize=size, fontweight=weight,
                         family="sans-serif")
                y -= 0.045
            if i == 3:
                ax = fig.add_axes([0.15, 0.30, 0.7, 0.30])
                xs = list(range(1, 11))
                ax.plot(xs, [55 + 4 * x for x in xs], marker="o",
                        label="fictional harmonizer")
                ax.plot(xs, [50 + 3 * x for x in xs], marker="s",
                        label="invented baseline")
                ax.set_xlabel("synthetic epoch")
                ax.set_ylabel("invented accuracy (%)")
                ax.legend(fontsize=8)
                ax.set_title("Synthetic training curve (all data invented)",
                             fontsize=9)
                fig.text(0.08, 0.24, FIG1_CAPTION, fontsize=9)
            fig.text(0.08, 0.03,
                     f"Synthetic page {i} of {len(PAPER_PAGES_TEXT)} - fictional content",
                     fontsize=8)
            pdf.savefig(fig)
            plt.close(fig)

    # 与 Figure 1 一致的独立 PNG（充当"已抽取图片"）
    fig, ax = plt.subplots(figsize=(6, 4))
    xs = list(range(1, 11))
    ax.plot(xs, [55 + 4 * x for x in xs], marker="o", label="fictional harmonizer")
    ax.plot(xs, [50 + 3 * x for x in xs], marker="s", label="invented baseline")
    ax.set_xlabel("synthetic epoch")
    ax.set_ylabel("invented accuracy (%)")
    ax.legend(fontsize=8)
    ax.set_title("Figure 1 (synthetic, fully fictional)", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_png_path, dpi=110)
    plt.close(fig)


def make_template(path):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width = Inches(13.333)   # 16:9
    prs.slide_height = Inches(7.5)
    prs.save(path)  # 默认版式集含 "Title Slide" / "Title and Content" 占位符


def make_csv(path):
    rows = [
        ["method", "invented_accuracy_pct", "synthetic_latency_ms"],
        ["fictional harmonizer", "92.4", "37"],
        ["invented baseline", "85.0", "52"],
        ["imaginary ablation", "88.1", "44"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成合成输入（fictional，非平台案例）")
    ap.add_argument("--out", required=True, help="输出目录（模拟平台 /input）")
    args = ap.parse_args(argv)
    out = args.out
    os.makedirs(os.path.join(out, "figs"), exist_ok=True)

    try:
        make_paper_pdf(os.path.join(out, "paper.pdf"),
                       os.path.join(out, "figs", "Figure_1.png"))
    except ImportError as e:
        print(f"ERROR: matplotlib 缺失，无法生成 paper.pdf: {e}", file=sys.stderr)
        return 2
    try:
        make_template(os.path.join(out, "target-template.pptx"))
    except ImportError as e:
        print(f"ERROR: python-pptx 缺失，无法生成模板: {e}", file=sys.stderr)
        return 2
    make_csv(os.path.join(out, "data.csv"))
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE_JSON, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK_MD)
    print(f"synthetic case written to {out} "
          f"(paper.pdf, target-template.pptx, figs/Figure_1.png, data.csv, case.json, task.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
