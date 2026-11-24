#!/usr/bin/env python3
"""make_synthetic_case.py — 现场生成合成输入（不提交任何二进制进 bundle）。

生成内容（全部显而易见是虚构的，含 "Synth et al." / "fictional" / "synthetic" 字样）：
  <out>/paper.pdf            ≥4 页英文合成论文（matplotlib PdfPages）：
                             - 第 2 页 Figure 1：先生成 PNG 数据图再以位图嵌入 PDF 页
                             - 第 3 页 Figure 2：纯矢量示意图，caption 含 "schematic"
                             - 第 4 页 Table 1：数值表，数值与 data.csv 完全一致
                             - 正文含 "Fig. 1"/"Fig. 2" 引用、带单位数值、limitations 句
  <out>/target-template.pptx 合成模板（python-pptx，含 title/content 占位符）
  <out>/data.csv             机器可读数值（与 Table 1 一致）
  <out>/case.json            含 case_id 与 output_contract
  <out>/task.md              受众 / 10 分钟 / ≤8 页

用法：python3 make_synthetic_case.py --out-dir <dir>
依赖：matplotlib（必需）；python-pptx（缺失时跳过模板生成并在 stderr 说明，退出码仍为 0）。
"""
import argparse
import csv
import json
import os
import sys

A4 = (8.27, 11.69)

# ---- 合成数据（单一事实源；PDF 表格与 CSV 都由它生成） ----
FIELDS = [0.5, 1.0, 2.0]
SAMPLES = {
    "S1": [0.42, 0.57, 0.63],
    "S2": [0.38, 0.51, 0.69],
    "S3": [0.44, 0.49, 0.72],
}
UNCERT = {"S1": 0.03, "S2": 0.04, "S3": 0.02}

FIG1_CAPTION = ("Figure 1. Measured response of the fictional synthometer versus field "
                "strength for three synthetic samples (data figure).")
FIG2_CAPTION = ("Figure 2. Schematic overview of the fictional three-stage measurement "
                "workflow (schematic).")
TAB1_CAPTION = ("Table 1. Measured response in arb. units of the three synthetic samples "
                "at each field strength (fictional data).")

TITLE = ("A Synthetic Fictional Study of Synthometer Response in the Imaginary "
         "Alloy X-7 (Synth et al.)")

ABSTRACT = [
    "Synth et al. present a fully synthetic, fictional study of the synthometer "
    "response in the imaginary alloy X-7. All values reported here are fabricated "
    "for pipeline testing only and carry no scientific meaning.",
    "We measured the response at field strengths of 0.5 mT, 1.0 mT and 2.0 mT. "
    "The peak synthetic response was 0.72 arb. units for sample S3 at 2.0 mT. "
    "Fig. 1 summarises the measured curves, and Fig. 2 shows the measurement setup.",
]

METHODS = [
    "The fictional synthometer was calibrated with a synthetic reference signal of "
    "1.00 arb. units at 25 C. Each of the three synthetic samples (S1, S2, S3) was "
    "measured three times; the mean response in arb. units is reported.",
    "Figure 1 shows the measured response curves for all three samples. The "
    "workflow of the measurement pipeline is illustrated in Fig. 2. Numeric values "
    "underlying Figure 1 are listed in Table 1 on the final page.",
]

DISCUSSION = [
    "The response rises monotonically with field strength for every sample, which "
    "is expected by construction because the data are synthetic. Sample S3 shows "
    "the strongest response (0.72 arb. units at 2.0 mT).",
    "A limitation of this synthetic study is that all values are fictional and were "
    "generated solely for pipeline testing, so no physical conclusion can be drawn.",
]


def _fmt(x):
    return f"{x:.2f}"


def _text_page(pdf, plt, title, paragraphs):
    import textwrap

    fig = plt.figure(figsize=A4)
    fig.text(0.08, 0.94, title, fontsize=13, weight="bold")
    y = 0.89
    for para in paragraphs:
        for line in textwrap.wrap(para, 92):
            fig.text(0.08, y, line, fontsize=9)
            y -= 0.017
        y -= 0.012
    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    tmp_png = path + ".fig1_tmp.png"

    # --- Figure 1 数据图：先落成 PNG 位图 ---
    f = plt.figure(figsize=(6.2, 3.8), dpi=150)
    ax = f.add_subplot(111)
    for name, ys in SAMPLES.items():
        ax.errorbar(FIELDS, ys, yerr=[UNCERT[name]] * len(FIELDS),
                    marker="o", capsize=3, label=f"sample {name} (synthetic)")
    ax.set_xlabel("field strength (mT)")
    ax.set_ylabel("response (arb. units)")
    ax.set_title("Fictional synthometer response (synthetic data)")
    ax.legend(fontsize=8)
    f.tight_layout()
    f.savefig(tmp_png)
    plt.close(f)

    with PdfPages(path) as pdf:
        # 第 1 页：标题 + 摘要
        _text_page(pdf, plt, TITLE, ["Abstract. " + ABSTRACT[0], ABSTRACT[1]])

        # 第 2 页：方法 + Figure 1（嵌入位图）
        fig = plt.figure(figsize=A4)
        fig.text(0.08, 0.94, "1. Methods and measured data (fictional)", fontsize=13,
                 weight="bold")
        import textwrap

        y = 0.89
        for para in METHODS:
            for line in textwrap.wrap(para, 92):
                fig.text(0.08, y, line, fontsize=9)
                y -= 0.017
            y -= 0.012
        img = plt.imread(tmp_png)
        axim = fig.add_axes([0.12, 0.28, 0.76, 0.33])
        axim.imshow(img)
        axim.axis("off")
        fig.text(0.08, 0.24, FIG1_CAPTION, fontsize=9)
        pdf.savefig(fig)
        plt.close(fig)

        # 第 3 页：Figure 2 示意图（纯矢量，无嵌入位图）
        fig = plt.figure(figsize=A4)
        fig.text(0.08, 0.94, "2. Measurement workflow (fictional)", fontsize=13,
                 weight="bold")
        y = 0.89
        for line in textwrap.wrap(
                "The synthetic pipeline consists of three fictional stages. The "
                "schematic below is an illustration only and is not experimental "
                "evidence.", 92):
            fig.text(0.08, y, line, fontsize=9)
            y -= 0.017
        axs = fig.add_axes([0.08, 0.35, 0.84, 0.42])
        axs.set_xlim(0, 3)
        axs.set_ylim(0, 1)
        axs.axis("off")
        labels = ["sample\npreparation", "synthometer\nreadout", "synthetic\nanalysis"]
        for i, lab in enumerate(labels):
            axs.add_patch(FancyBboxPatch((i + 0.08, 0.38), 0.72, 0.28,
                                         boxstyle="round,pad=0.02",
                                         fc="#dbe9f6", ec="#336699"))
            axs.text(i + 0.44, 0.52, lab, ha="center", va="center", fontsize=10)
            if i < 2:
                axs.add_patch(FancyArrowPatch((i + 0.84, 0.52), (i + 1.06, 0.52),
                                              arrowstyle="-|>", mutation_scale=18,
                                              color="#336699"))
        fig.text(0.08, 0.30, FIG2_CAPTION, fontsize=9)
        pdf.savefig(fig)
        plt.close(fig)

        # 第 4 页：Table 1 + limitations
        fig = plt.figure(figsize=A4)
        fig.text(0.08, 0.94, "3. Numeric results and limitations (fictional)",
                 fontsize=13, weight="bold")
        y = 0.89
        for line in textwrap.wrap(
                "All numeric values underlying Figure 1 are reproduced below; the "
                "same values ship in the companion file data.csv.", 92):
            fig.text(0.08, y, line, fontsize=9)
            y -= 0.017
        y -= 0.01
        fig.text(0.08, y, TAB1_CAPTION, fontsize=9)
        y -= 0.030
        header = "sample    field_mT    response_arb_units    uncertainty_arb_units"
        fig.text(0.08, y, header, fontsize=9, family="monospace")
        y -= 0.020
        for name, ys in SAMPLES.items():
            for fv, rv in zip(FIELDS, ys):
                row = (f"{name:<10}{_fmt(fv):<12}{_fmt(rv):<22}{_fmt(UNCERT[name]):<10}")
                fig.text(0.08, y, row, fontsize=9, family="monospace")
                y -= 0.018
        y -= 0.02
        for para in DISCUSSION:
            for line in textwrap.wrap(para, 92):
                fig.text(0.08, y, line, fontsize=9)
                y -= 0.017
            y -= 0.012
        pdf.savefig(fig)
        plt.close(fig)

    os.remove(tmp_png)


def build_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["field_strength_mT", "S1_response_arb_units",
                    "S2_response_arb_units", "S3_response_arb_units"])
        for i, fv in enumerate(FIELDS):
            w.writerow([_fmt(fv)] + [_fmt(SAMPLES[s][i]) for s in ("S1", "S2", "S3")])


def build_template(path):
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except ImportError:
        sys.stderr.write("tool_missing: python-pptx not installed; "
                         "target-template.pptx skipped\n")
        return False
    prs = Presentation()  # 默认主题即合法合成模板
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Synthetic Template Title"
    slide.placeholders[1].text = "synthetic template subtitle (fictional)"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Synthetic content layout"
    # 清掉示例文字，保持模板干净但占位符齐全
    prs.save(path)
    _ = Inches
    return True


def build_case_json(path):
    case = {
        "case_id": "synth-figure-veritas-b-0001",
        "output_contract": ["case_id", "status", "editable_source", "export_artifact",
                            "content_map", "compliance_checks", "exceptions"],
        "note": "SYNTHETIC fictional case for local pipeline testing; not a platform case.",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=2)


def build_task_md(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "# Task (synthetic)\n\n"
            "- Audience: fictional graduate seminar committee (materials science).\n"
            "- Duration: 10 minutes.\n"
            "- Slide limit: at most 8 slides (<= 8).\n"
            "- Template: use target-template.pptx if present.\n"
            "- Requirement: figures must keep verifiable provenance; schematics must "
            "never appear as results evidence; redrawn charts must match data.csv "
            "with zero numeric drift.\n"
        )


def main():
    ap = argparse.ArgumentParser(description="Generate a fully synthetic fictional case.")
    ap.add_argument("--out-dir", required=True, help="output directory (e.g. runs/b/input)")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    build_pdf(os.path.join(args.out_dir, "paper.pdf"))
    build_csv(os.path.join(args.out_dir, "data.csv"))
    build_template(os.path.join(args.out_dir, "target-template.pptx"))
    build_case_json(os.path.join(args.out_dir, "case.json"))
    build_task_md(os.path.join(args.out_dir, "task.md"))
    print(f"synthetic case written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
