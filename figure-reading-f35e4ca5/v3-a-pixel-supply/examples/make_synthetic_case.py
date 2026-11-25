#!/usr/bin/env python3
"""make_synthetic_case.py — generate a SYNTHETIC demo case (合成示例).

Everything produced here is synthetic: invented data, invented units, invented
questions. It exists only to exercise the pixel-supply chain end to end. It is
NOT formal case data and must never be shipped inside the skill directory.

Usage:
    python3 make_synthetic_case.py [--out DIR]
Default --out is a fresh tempfile.mkdtemp() directory, printed to stdout.
"""
import argparse
import csv
import json
import os
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_figure(path):
    rng = np.random.default_rng(42)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), dpi=200)
    fig.subplots_adjust(hspace=0.45, wspace=0.40)

    # (a) line plot, log-y, mV units
    ax = axes[0, 0]
    t = np.linspace(0, 10, 200)
    ax.plot(t, 3.0 * np.exp(-t / 3.0) + 0.05, label="cell A")
    ax.plot(t, 1.5 * np.exp(-t / 6.0) + 0.02, label="cell B")
    ax.set_yscale("log")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("membrane potential (mV)")
    ax.set_title("(a) decay traces", loc="left")
    ax.legend(fontsize=8)
    ax.grid(True, which="both", alpha=0.3)

    # (b) grouped bar chart with error bars and significance stars
    ax = axes[0, 1]
    groups = ["ctrl", "drug X", "drug Y"]
    m1 = [1.0, 1.8, 2.4]
    m2 = [1.1, 1.4, 2.9]
    e1 = [0.15, 0.20, 0.18]
    e2 = [0.12, 0.16, 0.22]
    x = np.arange(len(groups))
    ax.bar(x - 0.18, m1, 0.35, yerr=e1, capsize=4, label="rep 1")
    ax.bar(x + 0.18, m2, 0.35, yerr=e2, capsize=4, label="rep 2")
    for xi, mi, ei, star in [(2 - 0.18, m1[2], e1[2], "*"),
                             (2 + 0.18, m2[2], e2[2], "**")]:
        ax.text(xi, mi + ei + 0.08, star, ha="center", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylabel("fold change")
    ax.set_title("(b) fold change", loc="left")
    ax.legend(fontsize=8)

    # (c) scatter with legend
    ax = axes[1, 0]
    for name, (mx, my) in [("cluster 1", (2.0, 2.0)),
                           ("cluster 2", (5.0, 4.0)),
                           ("cluster 3", (3.5, 6.0))]:
        pts = rng.normal([mx, my], 0.6, size=(40, 2))
        ax.scatter(pts[:, 0], pts[:, 1], s=12, alpha=0.7, label=name)
    ax.set_xlabel("PC1 (a.u.)")
    ax.set_ylabel("PC2 (a.u.)")
    ax.set_title("(c) embedding", loc="left")
    ax.legend(fontsize=8)

    # (d) spectrum-like peaks
    ax = axes[1, 1]
    wv = np.linspace(400, 700, 600)
    spec = (80 * np.exp(-((wv - 460) / 12) ** 2)
            + 55 * np.exp(-((wv - 530) / 20) ** 2)
            + 95 * np.exp(-((wv - 610) / 9) ** 2)
            + rng.normal(0, 2.0, wv.size))
    ax.plot(wv, spec, color="darkred", lw=1.0)
    ax.set_xlabel("wavelength (nm)")
    ax.set_ylabel("intensity (counts)")
    ax.set_title("(d) emission spectrum", loc="left")

    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Generate a synthetic demo case.")
    ap.add_argument("--out", default=None,
                    help="output dir (default: fresh tempfile.mkdtemp)")
    args = ap.parse_args()
    out = args.out or tempfile.mkdtemp(prefix="f35e-synthetic-case-")
    os.makedirs(out, exist_ok=True)

    fig_path = os.path.join(out, "figure_synthetic_4panel.png")
    make_figure(fig_path)

    table_path = os.path.join(out, "table_fold_change.csv")
    with open(table_path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["group", "rep1_fold_change", "rep2_fold_change",
                     "significance"])
        wr.writerow(["ctrl", 1.0, 1.1, "ns"])
        wr.writerow(["drug X", 1.8, 1.4, "ns"])
        wr.writerow(["drug Y", 2.4, 2.9, "*/**"])

    case = {
        "case_id": "synthetic-demo-A",
        "note": "SYNTHETIC demo case (合成示例) — invented data, not a real paper.",
        "materials": ["figure_synthetic_4panel.png", "table_fold_change.csv"],
        "declared_gaps": [
            "Figure S1 mentioned in task text but pixels not shipped (declared gap)"],
        "output_contract": {
            "figure_summary": {
                "panel_count": None,
                "panel_labels": []
            },
            "axes": [
                {"panel": "(a)", "y_axis_type": None, "y_unit": None}
            ],
            "findings": [],
            "declared_gaps": []
        },
    }
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, indent=2, ensure_ascii=False)

    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# Synthetic demo task (合成示例)\n\n"
            "All data here are invented. Questions:\n\n"
            "1. How many panels does the figure have and what are their labels?\n"
            "2. In panel (a), is the y-axis linear or log, and what unit does it use?\n"
            "3. In panel (b), which condition shows significance stars, and how many stars?\n"
            "4. Figure S1 is mentioned in the source text but its pixels were not shipped; treat it as a declared gap.\n")

    print(out)


if __name__ == "__main__":
    main()
