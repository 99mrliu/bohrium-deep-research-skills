"""make_synthetic_case.py — generate a SYNTHETIC case into a target dir.

Creates (under the target dir, which acts as the /input root):
  case.json             case_id + output_contract + materials paths
  task.md               audience/time/slide-count constraints
  materials/template.pptx   python-pptx DEFAULT template (real master,
                            layouts, placeholders; nothing renamed)
  materials/paper.pdf       matplotlib PdfPages: 4 text pages (Title /
                            Introduction / Method / Results+Limitations) with
                            fixed numbers (accuracy 92.4%, n = 128, ...) plus
                            2 plot pages labeled Figure 1 / Figure 2.

Every file's text is clearly marked as a SYNTHETIC EXAMPLE (合成示例).

Usage:
  python3 make_synthetic_case.py --out /tmp/xxx/input
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

MARK = "SYNTHETIC EXAMPLE (合成示例) - not real research, for pipeline demo only."
# DejaVu has no CJK glyphs: PDF pages use the English-only mark to keep the
# generated paper free of missing-glyph boxes; UTF-8 text files keep MARK.
MARK_EN = "SYNTHETIC EXAMPLE - not real research, for pipeline demo only."


# ---------------------------------------------------------------------------
# template.pptx
# ---------------------------------------------------------------------------

def make_template(path: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()  # default template: real master/layouts/placeholders
    prs.slide_width = Inches(13.333)   # 16:9
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "Synthetic Template (合成示例)"
    prs.core_properties.comments = MARK
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prs.save(path)


# ---------------------------------------------------------------------------
# paper.pdf
# ---------------------------------------------------------------------------

def _text_page(pdf, title: str, paragraphs: list[str]) -> None:
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(8.27, 11.69))  # A4
    fig.text(0.08, 0.95, title, fontsize=16, fontweight="bold", va="top")
    fig.text(0.08, 0.90, MARK_EN, fontsize=8, color="red", va="top", style="italic")
    y = 0.84
    for para in paragraphs:
        wrapped = textwrap.fill(para, 95)
        fig.text(0.08, y, wrapped, fontsize=10, va="top")
        y -= 0.045 * (wrapped.count("\n") + 2)
    pdf.savefig(fig)
    plt.close(fig)


def _plot_page(pdf, label: str, kind: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    fig.text(0.5, 0.97, MARK_EN, fontsize=8, color="red", ha="center",
             style="italic")
    rng = np.random.default_rng(7)
    if kind == "bar":
        methods = ["Baseline", "Ours"]
        vals = [87.1, 92.4]
        ax.bar(methods, vals, color=["#888888", "#2a6fbb"])
        ax.set_ylabel("Accuracy (%)")
        ax.set_ylim(80, 95)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.3, f"{v}%", ha="center", fontsize=12)
        ax.set_title("Accuracy comparison (synthetic)")
    else:
        x = np.arange(1, 11)
        ours = 60 + 34 * (1 - np.exp(-x / 3.0)) + rng.normal(0, 0.5, 10)
        base = 60 + 28 * (1 - np.exp(-x / 4.5)) + rng.normal(0, 0.5, 10)
        ax.plot(x, ours, marker="o", label="Ours")
        ax.plot(x, base, marker="s", label="Baseline")
        ax.set_xlabel("Training epoch")
        ax.set_ylabel("Validation accuracy (%)")
        ax.legend()
        ax.grid(alpha=0.3)
        ax.set_title("Learning curves (synthetic)")
    fig.text(0.5, 0.30, f"{label}: synthetic plot for pipeline demonstration.",
             fontsize=11, ha="center")
    pdf.savefig(fig)
    plt.close(fig)


def make_paper(path: str) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PdfPages(path) as pdf:
        _text_page(pdf, "VeritasNet: A Synthetic Study of Ledger-Grounded Slides", [
            "Authors: A. Example, B. Example. " + MARK_EN,
            "Abstract. This synthetic paper accompanies the source-veritas-deck "
            "skill demonstration. We study whether slide numbers can be kept "
            "verbatim with respect to a source corpus. Our method achieves an "
            "accuracy of 92.4% on the synthetic benchmark, improving over the "
            "87.1% baseline by 5.3 points.",
            "Keywords: synthetic, corpus ledger, fidelity gate.",
        ])
        _text_page(pdf, "1 Introduction", [
            "Academic slide decks frequently contain numbers that diverge from "
            "the source paper. In this synthetic study we quantify the problem: "
            "in a pilot audit of 24 synthetic decks, 7 contained at least one "
            "number absent from the source text.",
            "Our contribution is a corpus ledger that records every text block "
            "and figure with a sha256 digest, plus a fidelity gate that checks "
            "every numeric token before a slide is built. " + MARK_EN,
            "The remainder of this synthetic paper is organized as follows. "
            "Section 2 describes the method, Section 3 reports results and "
            "limitations.",
        ])
        _text_page(pdf, "2 Method", [
            "We parse the source PDF into text blocks with page and bounding "
            "box coordinates, hashing each block with sha256. Figures are "
            "exported either as embedded images or as rendered page regions, "
            "also hashed.",
            "Each slide bullet is checked before rendering: every numeric "
            "token must appear verbatim in the evidence-anchored corpus "
            "entries. The synthetic evaluation uses n = 128 slides sampled "
            "from 16 synthetic papers.",
            "Extraction takes 3.6 seconds per paper on a synthetic laptop. " + MARK_EN,
        ])
        _text_page(pdf, "3 Results and Limitations", [
            "Results. The proposed gate achieves an accuracy of 92.4% in "
            "detecting unfaithful numbers, versus 87.1% for the regex-only "
            "baseline, an improvement of 5.3 points with p < 0.05 on the "
            "synthetic benchmark (n = 128). Figure 1 summarizes the accuracy "
            "comparison and Figure 2 shows the learning curves.",
            "Limitations. The gate cannot verify numbers that require unit "
            "conversion (about 4% of cases), and quoted sentences spanning a "
            "page break may fail the verbatim check. The synthetic corpus "
            "contains only English text.",
            "Conclusion. A corpus ledger plus a per-claim fidelity gate keeps "
            "slide numbers verbatim. " + MARK_EN,
        ])
        _plot_page(pdf, "Figure 1", "bar")
        _plot_page(pdf, "Figure 2", "line")
        info = pdf.infodict()
        info["Title"] = "Synthetic Paper (合成示例)"
        info["Subject"] = MARK_EN


# ---------------------------------------------------------------------------
# case.json + task.md
# ---------------------------------------------------------------------------

def make_case_meta(root: str) -> None:
    case = {
        "case_id": "synthetic-demo-01",
        "note": MARK,
        "materials": {"paper": "materials/paper.pdf",
                      "template": "materials/template.pptx"},
        "output_contract": {"fields": [
            "case_id", "status", "summary", "artifacts", "evidence_map",
            "sources", "uncertainty", "change_log"]},
    }
    common.dump_json(case, os.path.join(root, "case.json"))

    task = f"""# 任务说明（{MARK}）

把 materials/paper.pdf 这篇**合成**论文组织成一份学术汇报 PPT，
套用 materials/template.pptx 的母版与版式。

- 受众：课题组例会（学术同行）
- 时长：10 分钟
- 页数：6–8 页，须覆盖 title → background → method → results →
  discussion/limitations → conclusion
- 每个数字必须与论文原文逐字一致；每页给出来源定位（页码/图号）
- 交付：deck.pptx + deck.pdf + preview PNG + fidelity_report.json +
  result.json（含 output_contract 声明的全部字段）

> 本案例为合成示例（synthetic example），不是正式评测案例，
> 产物不代表真实研究结果。
"""
    with open(os.path.join(root, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="target dir = input root")
    args = ap.parse_args()
    root = os.path.abspath(args.out)
    os.makedirs(os.path.join(root, "materials"), exist_ok=True)
    make_template(os.path.join(root, "materials", "template.pptx"))
    make_paper(os.path.join(root, "materials", "paper.pdf"))
    make_case_meta(root)
    print(f"[make_synthetic_case] case root -> {root}")
    for rel in ("case.json", "task.md", "materials/paper.pdf",
                "materials/template.pptx"):
        p = os.path.join(root, rel)
        print(f"  {rel}  ({os.path.getsize(p)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
