#!/usr/bin/env python3
"""make_gamma_pdf.py — 生成合成示例 PDF（paper_gamma.pdf，单页，含可引用文字）。

内容完全虚构（合成示例 / synthetic），仅用于实测 corpus_build.py 的
pdftotext 解析路径。由 examples/run_example.sh 自动调用，也可单独运行。
"""
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "materials", "paper_gamma.pdf")

LINES = [
    "GammaPress Sintering Aids for Solid-State Electrolyte Densification:",
    "A Synthetic One-Page Demonstration Note",
    "",
    "Marta Kowalska and Diego Fuentes",
    "Synthetic Solid State Notes, 2024",
    "DOI: 10.52810/sssn.2024.0056",
    "",
    "This single-page synthetic note demonstrates that the corpus builder",
    "extracts real page structure from PDF files via pdftotext.",
    "",
    "In the fictional experiment, adding 2 wt percent GammaPress aid raised",
    "the relative density of the synthetic LLZO electrolyte from 84 percent",
    "to 96 percent after sintering at 1100 degrees Celsius for 2 hours.",
    "",
    "The fictional authors caution that all values on this page are",
    "synthetic example data with no real experimental basis.",
    "",
    "Reference: Kowalska, M. Sintering atmospheres for garnet electrolytes:",
    "a synthetic note. Synthetic Solid State Notes, 2023.",
    "DOI: 10.52810/sssn.2023.0019",
]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with PdfPages(OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))  # A4
        fig.text(0.08, 0.97, "\n".join(LINES), va="top", ha="left",
                 fontsize=11, family="monospace")
        pdf.savefig(fig)
        plt.close(fig)
    print(f"[make_gamma_pdf] 已生成 {OUT}")


if __name__ == "__main__":
    main()
