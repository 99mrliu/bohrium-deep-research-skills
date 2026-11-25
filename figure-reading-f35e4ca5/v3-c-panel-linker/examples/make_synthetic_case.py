#!/usr/bin/env python3
"""make_synthetic_case.py — generate a fully SYNTHETIC demo case for bundle C.

Creates, inside --out (default: tempfile.mkdtemp, printed to stdout):
  figure1.png  2x2 multi-panel figure labeled (a)-(d):
               (a) line/kinetic trace, (b) grouped bar chart with significance stars,
               (c) scatter/correlation, (d) spectrum.
  caption.txt  caption whose last sentence references "Figure 2" which is NOT shipped
               (-> must land in the gap ledger).
  case.json    case_id "synthetic-demo-C", a small output_contract, materials listing
               ONLY figure1.png + table1.csv.
  task.md      3 questions: one about panel (b), one comparing (a) and (d), one open.
  table1.csv   one small synthetic table.

ALL DATA ARE SYNTHETIC (合成示例), generated with a fixed seed.
"""
import argparse
import json
import os
import tempfile

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CAPTION = ("Figure 1. Overview of the synthetic experiment. "
           "(a) Kinetic trace of signal vs time. "
           "(b) Grouped quantification with significance. "
           "(c) Correlation of parameters. "
           "(d) Spectrum of the product. "
           "See also Figure 2 for the microscopy.")

TASK_MD = """# Synthetic demo task (合成示例 / synthetic data only)

Answer the following questions about Figure 1.

1. What does panel (b) show for the grouped quantification, and which groups differ
   significantly according to the shipped table?
2. Compare the kinetic trace in (a) with the spectrum in (d): how do their x-axes differ?
3. What overall conclusion does the figure support about the synthetic experiment?
"""

CSV = """group,mean,sd,n,significant_vs_control
control,1.00,0.12,8,no
treatment_A,1.85,0.21,8,yes
treatment_B,1.02,0.15,8,no
"""


def make_figure(path):
    rng = np.random.default_rng(7)
    fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.0), dpi=150)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.94, bottom=0.09,
                        hspace=0.55, wspace=0.45)

    t = np.linspace(0, 10, 200)
    axes[0, 0].plot(t, 1 - np.exp(-t / 2.0), color="tab:blue", lw=1.5)
    axes[0, 0].set_xlabel("time (s)")
    axes[0, 0].set_ylabel("signal (a.u.)")

    means = [1.00, 1.85, 1.02]
    sds = [0.12, 0.21, 0.15]
    axes[0, 1].bar([0, 1, 2], means, yerr=sds, capsize=4,
                   color=["tab:gray", "tab:red", "tab:gray"])
    axes[0, 1].text(1, means[1] + sds[1] + 0.06, "***", ha="center", fontsize=12)
    axes[0, 1].set_xticks([0, 1, 2])
    axes[0, 1].set_xticklabels(["ctrl", "trtA", "trtB"])
    axes[0, 1].set_ylabel("fold change")

    x = rng.normal(0, 1, 60)
    y = 0.8 * x + rng.normal(0, 0.4, 60)
    axes[1, 0].scatter(x, y, s=12, color="tab:green", alpha=0.8)
    axes[1, 0].set_xlabel("parameter X")
    axes[1, 0].set_ylabel("parameter Y")

    freq = np.linspace(0, 500, 1000)
    spec = (np.exp(-((freq - 120) / 12) ** 2)
            + 0.7 * np.exp(-((freq - 300) / 20) ** 2)
            + 0.05 * rng.random(freq.size))
    axes[1, 1].plot(freq, spec, color="tab:purple", lw=1.0)
    axes[1, 1].set_xlabel("frequency (Hz)")
    axes[1, 1].set_ylabel("intensity")

    for ax, letter in zip(axes.flat, "abcd"):
        ax.text(0.02, 0.98, f"({letter})", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top", ha="left")
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Generate a SYNTHETIC demo case for bundle C.")
    ap.add_argument("--out", default=None,
                    help="output dir (default: a fresh tempfile.mkdtemp, printed)")
    args = ap.parse_args()

    out = args.out or tempfile.mkdtemp(prefix="f35e-c-demo-")
    os.makedirs(out, exist_ok=True)

    fig_path = os.path.join(out, "figure1.png")
    make_figure(fig_path)

    with open(os.path.join(out, "caption.txt"), "w", encoding="utf-8") as fh:
        fh.write(CAPTION + "\n")
    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(TASK_MD)
    with open(os.path.join(out, "table1.csv"), "w", encoding="utf-8") as fh:
        fh.write(CSV)

    case = {
        "case_id": "synthetic-demo-C",
        "note": "SYNTHETIC demo case for the panel-linked-figure-reading skill (bundle C). "
                "All data are artificial. Figure 2 is referenced in the caption but its "
                "pixels are intentionally NOT shipped (declared gap).",
        "output_contract": {
            "panel_b_summary": "",
            "comparison_a_d": "",
            "overall_conclusion": "",
        },
        "materials": ["figure1.png", "table1.csv"],
        "figure_caption": CAPTION,
    }
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=2)

    print(out)


if __name__ == "__main__":
    main()
