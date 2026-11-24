#!/usr/bin/env python3
"""make_gamma_pdf.py — 生成合成示例 PDF（synthetic_note_gamma.pdf，单页）。

内容完全虚构（SYNTHETIC EXAMPLE），仅用于实测 source_index.py 对真实 PDF
的 pdftotext 解析路径（页级 span、题注注册表、数字注册表、断词修复）。
正文故意在 "contin-" 处断行，以检验 anchor_audit.py 的连字符换行修复。
由 examples/run_example.sh 在演示开始时调用，演示结束自动删除产物 PDF。
"""
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "materials", "synthetic_note_gamma.pdf")

LINES = [
    "SYNTHETIC EXAMPLE - NOT REAL RESEARCH",
    "Composite Gel Electrolyte for Pouch Cells: A Synthetic One-Page Note",
    "",
    "Ruth Almeida and Chen Watanabe",
    "Synthetic Energy Notes, 2024",
    "DOI: 10.52810/sen.2024.0233",
    "",
    "This single-page synthetic note demonstrates that the source indexer",
    "extracts real page structure, captions, and numbers from a PDF via",
    "pdftotext.",
    "",
    "In the fictional cycling test, the prototype pouch cell reached",
    "178 Wh/kg under contin-",
    "uous 0.5 C cycling at 60 degrees Celsius, while the composite",
    "electrolyte showed an ionic conductivity of 3.2 mS/cm at room",
    "temperature.",
    "",
    "Figure 1. Nyquist plot of the synthetic pouch cell before and after",
    "cycling.",
    "",
    "The fictional authors caution that all values on this page are",
    "synthetic example data with no real experimental basis.",
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
