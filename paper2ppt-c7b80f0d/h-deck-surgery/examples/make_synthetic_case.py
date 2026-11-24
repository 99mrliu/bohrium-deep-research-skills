#!/usr/bin/env python3
"""make_synthetic_case.py — 现场生成合成输入（显而易见虚构，非平台案例）。

用法:
    python3 make_synthetic_case.py --out runs/e/input

产物：
  paper.pdf            4 页英文合成论文（matplotlib PdfPages 纯文本 + 一张简单图，
                       含 Figure 1 / Table 1 caption、带单位数值、limitations 句）
  figure1.png          论文中 Figure 1 的同款图（供 add_figure op 使用）
  target-template.pptx 合成模板（python-pptx 默认主题，含 title/content 占位符）
  starting-deck.pptx   6 页起始稿，含 2 处待修问题：
                         P2 标题为栏目名 "SECTION_HEADER"；
                         P3 含与论文不符的错误数值 "99.9 ms"（论文为 42.7 ms）
  data.csv             合成数据
  case.json            case_id + output_contract
  task.md              受众 / 10 分钟 / ≤8 页 / 模板要求 / edit 模式说明
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

COHERENCE_MS = "42.7"
GAP_EV = "3.14"
N_SAMPLES = "128"
ERR_REDUCTION = "18.5"
LATTICE_NM = "5.0"
WRONG_MS = "99.9"  # 起始稿里的错误数值


def make_paper_pdf(out_dir: str) -> tuple[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    pdf_path = os.path.join(out_dir, "paper.pdf")
    png_path = os.path.join(out_dir, "figure1.png")

    def text_page(pdf, title, lines):
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.08, 0.93, title, fontsize=15, fontweight="bold")
        y = 0.86
        for ln in lines:
            fig.text(0.08, y, ln, fontsize=10, wrap=True)
            y -= 0.045
        fig.text(0.08, 0.04, "SYNTHETIC / FICTIONAL DOCUMENT - for pipeline testing only",
                 fontsize=8, color="gray")
        pdf.savefig(fig)
        plt.close(fig)

    with PdfPages(pdf_path) as pdf:
        text_page(pdf, "Synthetic Gradient Harmonics in Fictional Quantum Foam: "
                       "A Fully Simulated Study", [
            "A. Synth, B. Fictional, C. Placeholder",
            "Institute of Synthetic Measurements, Nowhere University",
            "",
            "Abstract.",
            "This entirely fictional study reports synthetic measurements of gradient",
            "harmonics in simulated quantum foam. All data are fictional and were",
            "generated for pipeline testing only. Using a simulated lattice with",
            f"spacing of {LATTICE_NM} nm, we measured a coherence time of {COHERENCE_MS} ms",
            f"across n = {N_SAMPLES} synthetic samples, and observed a synthetic energy",
            f"gap of {GAP_EV} eV. The fictional error rate was reduced by {ERR_REDUCTION} %",
            "relative to a simulated baseline.",
        ])
        text_page(pdf, "1. Introduction and Methods (synthetic)", [
            "Gradient harmonics in fictional quantum foam have never been measured,",
            "because the phenomenon is invented for this synthetic document.",
            "",
            "Methods.",
            f"We simulated a lattice with spacing of {LATTICE_NM} nm and drew",
            f"n = {N_SAMPLES} synthetic samples from a fictional distribution.",
            f"The coherence time of {COHERENCE_MS} ms was estimated with a simulated",
            "exponential fit. Every number on this page is fictional.",
        ])
        # Page 3: results + 图
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.08, 0.93, "2. Results (synthetic)", fontsize=15, fontweight="bold")
        ax = fig.add_axes([0.12, 0.45, 0.76, 0.38])
        xs = list(range(0, 60, 2))
        ys = [pow(2.718281828, -x / 42.7) for x in xs]
        ax.plot(xs, ys, "o-", color="#1f77b4")
        ax.set_xlabel("simulated time (ms)")
        ax.set_ylabel("fictional coherence signal (a.u.)")
        ax.set_title("Fictional decay curve (simulated data)")
        fig.text(0.08, 0.38, "Figure 1: Synthetic decay curve of the fictional coherence "
                             "signal (simulated data).", fontsize=10)
        fig.text(0.08, 0.33, f"The fictional error rate was reduced by {ERR_REDUCTION} % "
                             "relative to the simulated baseline.", fontsize=10)
        fig.text(0.08, 0.28, f"The synthetic energy gap of {GAP_EV} eV is consistent with "
                             "the invented model.", fontsize=10)
        fig.text(0.08, 0.23, "Table 1: Fictional summary of synthetic fit parameters "
                             "(all values simulated).", fontsize=10)
        fig.text(0.08, 0.18, f"  parameter        value", fontsize=10, family="monospace")
        fig.text(0.08, 0.15, f"  coherence time     {COHERENCE_MS} ms", fontsize=10,
                 family="monospace")
        fig.text(0.08, 0.12, f"  energy gap         {GAP_EV} eV", fontsize=10,
                 family="monospace")
        fig.text(0.08, 0.04, "SYNTHETIC / FICTIONAL DOCUMENT - for pipeline testing only",
                 fontsize=8, color="gray")
        pdf.savefig(fig)
        plt.close(fig)
        text_page(pdf, "3. Discussion, Limitations and References (synthetic)", [
            "Discussion.",
            "The synthetic results agree with the invented model by construction,",
            "because the model generated the data.",
            "",
            "Limitations.",
            "A key limitation of this synthetic study is that every data point is",
            "fictional and was generated for pipeline testing only, so no physical",
            "conclusion can be drawn.",
            "",
            "References.",
            "[1] Synth et al., Journal of Fictional Results, 2026 (synthetic).",
        ])

    # 单独的 Figure 1 PNG（供 add_figure op 嵌入）
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    xs = list(range(0, 60, 2))
    ys = [pow(2.718281828, -x / 42.7) for x in xs]
    ax.plot(xs, ys, "o-", color="#1f77b4")
    ax.set_xlabel("simulated time (ms)")
    ax.set_ylabel("fictional coherence signal (a.u.)")
    ax.set_title("Figure 1 (synthetic, fictional data)")
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    plt.close(fig)
    return pdf_path, png_path


def make_template(out_dir: str) -> str:
    from pptx import Presentation

    prs = Presentation()  # 默认主题 + title/content 占位符版式
    path = os.path.join(out_dir, "target-template.pptx")
    prs.save(path)
    return path


def make_starting_deck(out_dir: str) -> str:
    from pptx import Presentation

    prs = Presentation()
    title_layout = prs.slide_layouts[0]
    content_layout = prs.slide_layouts[1]

    def add_content_slide(title, bullets):
        s = prs.slides.add_slide(content_layout)
        s.shapes.title.text_frame.text = title
        body = s.placeholders[1].text_frame
        body.clear()
        for i, b in enumerate(bullets):
            para = body.paragraphs[0] if i == 0 else body.add_paragraph()
            para.text = b
        return s

    s1 = prs.slides.add_slide(title_layout)
    s1.shapes.title.text_frame.text = ("Synthetic Gradient Harmonics in Fictional "
                                       "Quantum Foam")
    s1.placeholders[1].text_frame.text = "A. Synth et al. - synthetic study briefing"

    # 问题 1：栏目名标题
    add_content_slide("SECTION_HEADER", [
        f"Simulated lattice with spacing of {LATTICE_NM} nm.",
        "Gradient harmonics are a fictional phenomenon invented for this study.",
        "Motivation: demonstrate synthetic measurement pipelines.",
    ])
    # 问题 2：与论文不符的错误数值（论文为 42.7 ms）
    add_content_slide("Methods", [
        f"Coherence time of {WRONG_MS} ms was estimated with a simulated fit.",
        f"n = {N_SAMPLES} synthetic samples drawn from a fictional distribution.",
    ])
    add_content_slide("Results", [
        "The decay curve of the fictional coherence signal is shown in Figure 1.",
        f"The fictional error rate was reduced by {ERR_REDUCTION} % against baseline.",
    ])
    add_content_slide("Limitations", [
        "A key limitation is that every data point is fictional.",
    ])
    add_content_slide("Conclusion", [
        "Synthetic pipeline produced consistent fictional results.",
    ])
    path = os.path.join(out_dir, "starting-deck.pptx")
    prs.save(path)
    return path


def make_csv(out_dir: str) -> str:
    path = os.path.join(out_dir, "data.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["simulated_time_ms", "fictional_coherence_signal_au"])
        for x in range(0, 60, 2):
            w.writerow([x, f"{pow(2.718281828, -x / 42.7):.6f}"])
    return path


def make_case_json(out_dir: str) -> str:
    case = {
        "case_id": "synthetic-edit-001",
        "output_contract": ["case_id", "status", "editable_source", "export_artifact",
                            "content_map", "compliance_checks", "exceptions"],
        "note": "SYNTHETIC case for local pipeline testing; not a platform case.",
    }
    path = os.path.join(out_dir, "case.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def make_task_md(out_dir: str) -> str:
    text = """# Task (SYNTHETIC, fictional — not a platform case)

Adapt the existing starting deck (`starting-deck.pptx`) into a clean academic
briefing of the synthetic paper `paper.pdf`.

- Audience: graduate students in a fictional measurement-methods seminar.
- Duration: 10 minutes (about 60-90 seconds per slide).
- Length: ≤ 8 pages (slides).
- Template: keep the theme of `target-template.pptx`; do not restyle the deck.
- Mode: EDIT. Apply minimal, auditable changes; fix any values that disagree
  with the paper; replace placeholder/column-name titles; every slide needs
  speaker notes; keep Figure 1 and Table 1 traceable to the paper.
"""
    path = os.path.join(out_dir, "task.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成合成输入（虚构），模拟平台 /input 目录")
    ap.add_argument("--out", required=True, help="输出目录（如 runs/e/input）")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    try:
        pdf_path, png_path = make_paper_pdf(args.out)
    except ImportError as e:
        print(f"error: matplotlib required for synthetic paper: {e}", file=sys.stderr)
        return 3
    try:
        tpl = make_template(args.out)
        deck = make_starting_deck(args.out)
    except ImportError as e:
        print(f"error: python-pptx required for synthetic decks: {e}", file=sys.stderr)
        return 3
    csv_path = make_csv(args.out)
    case_path = make_case_json(args.out)
    task_path = make_task_md(args.out)
    for p in (pdf_path, png_path, tpl, deck, csv_path, case_path, task_path):
        print(f"  wrote {p} ({os.path.getsize(p)} bytes)")
    print("synthetic case ready (all content fictional).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
