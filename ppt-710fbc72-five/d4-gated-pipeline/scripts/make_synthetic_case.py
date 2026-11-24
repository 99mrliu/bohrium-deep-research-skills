#!/usr/bin/env python3
"""make_synthetic_case.py — 生成合成演示案例（合成示例，非正式测试案例）。

产出到 --out 目录：
  case.json      含 case_id / output_contract.fields / materials 声明，synthetic: true
  task.md        任务说明（标注合成示例）
  paper.pdf      matplotlib PdfPages：4 页文本（含可核验数字）+ 2 页图
  template.pptx  python-pptx 默认母版/版式（16:9），0 页起始
"""
from __future__ import annotations

import argparse
import json
import os

TEXT_PAGES = [
    ["Adaptive Sparse Attention for Long-Context Protein Language Models",
     "H. Liu, M. Chen, R. Zhao - SynBio AI Lab (Synthetic Demo)",
     "",
     "Abstract",
     "We propose SparProtein, an adaptive sparse attention mechanism for protein",
     "language models operating on context length of 32768 tokens. Trained on 128",
     "GPUs for 6 days, SparProtein reduces inference latency by 41.7% relative to",
     "dense attention while preserving downstream accuracy."],
    ["1. Introduction",
     "Protein language models are limited by quadratic attention cost on long",
     "sequences, motivating sparse alternatives that keep accuracy intact.",
     "",
     "2. Methods",
     "We curate a dataset of 2.3 million protein sequences from UniRef90.",
     "Models use 12 layers, hidden size 768, learning rate 3e-4, batch size 512.",
     "We evaluate on 4 downstream tasks: localization, solubility, stability, binding."],
    ["3. Results",
     "SparProtein achieves 92.4% average accuracy, outperforming the dense baseline",
     "by 6.8 points (p-value < 0.01) across 4 tasks.",
     "Figure 1 shows the accuracy comparison across four model variants.",
     "Figure 2 reports inference latency versus context length up to 32768 tokens.",
     "Sparse patterns adapt per layer: shallow layers keep 80.0% attention density,",
     "deep layers drop to 22.5% density without accuracy loss."],
    ["4. Discussion",
     "Adaptive sparsity transfers across tasks, but gains shrink on short sequences.",
     "",
     "5. Limitations",
     "The method is limited to sequences shorter than 4096 residues at inference.",
     "Memory usage grows by 18.5% when the sparsity controller is disabled.",
     "",
     "6. Conclusion",
     "We conclude that adaptive sparsity is a practical route to long-context",
     "protein modeling; code and checkpoints will be released."],
]

FIG_PAGES = [
    {"kind": "bar", "caption": "Figure 1: Accuracy comparison across four model variants.",
     "x": ["Dense", "Static-Sparse", "SparProtein", "SparProtein-XL"],
     "y": [85.6, 88.9, 92.4, 93.1], "ylabel": "Accuracy (%)"},
    {"kind": "line", "caption": "Figure 2: Inference latency versus context length.",
     "x": [1024, 2048, 4096, 8192, 16384, 32768],
     "y": [12.0, 25.1, 54.3, 118.6, 261.4, 585.9], "ylabel": "Latency (ms)"},
]


def _write_text_page(pdf, lines):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(11, 8.5))
    y = 0.95
    for line in lines:
        fig.text(0.07, y, line, fontsize=11, family="DejaVu Sans")
        y -= 0.045
    pdf.savefig(fig)
    plt.close(fig)


def _write_figure_page(pdf, spec):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 8.5))
    if spec["kind"] == "bar":
        ax.bar(spec["x"], spec["y"], color="#3b6ea5")
        for xi, yi in zip(spec["x"], spec["y"]):
            ax.text(xi, yi + 0.3, f"{yi}", ha="center", fontsize=9)
    else:
        ax.plot(spec["x"], spec["y"], marker="o", color="#a53b3b")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("Context length (tokens)")
    ax.set_ylabel(spec["ylabel"])
    ax.grid(True, alpha=0.3)
    fig.text(0.07, 0.04, spec["caption"], fontsize=11)
    pdf.savefig(fig)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录（作为流水线的 --input）")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    case = {
        "case_id": "synthetic-demo-04",
        "synthetic": True,
        "note": "合成示例：由 make_synthetic_case.py 生成，仅用于演示流水线，非正式测试案例。",
        "output_contract": {"fields": ["case_id", "status", "summary", "artifacts",
                                       "evidence_map", "sources", "uncertainty", "change_log"]},
        "materials": {"paper": "paper.pdf", "template": "template.pptx"},
    }
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
        f.write("\n")

    task = """# 学术汇报制作任务（合成示例）

> 本任务为 gated-pipeline-deck 的合成演示输入，非正式测试案例。

请把 paper.pdf 组织成一份按 template.pptx 版式构建的学术汇报：
- 主线覆盖 研究问题 / 方法 / 结果 / 局限；
- 页型从 title 到 conclusion，6 页左右，时长 12 分钟；
- 每页保留论文定位证据（页码 + 逐字引用），数字与原文逐字一致；
- 交付可编辑 deck.pptx 与 PDF/PNG 预览。
"""
    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)

    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(os.path.join(out, "paper.pdf")) as pdf:
        for lines in TEXT_PAGES:
            _write_text_page(pdf, lines)
        for spec in FIG_PAGES:
            _write_figure_page(pdf, spec)

    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.save(os.path.join(out, "template.pptx"))

    print(f"synthetic case written to {out}")
    for fn in sorted(os.listdir(out)):
        print(f"  {fn} {os.path.getsize(os.path.join(out, fn))} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
