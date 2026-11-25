#!/usr/bin/env python3
"""make_synthetic_case.py -- write a SYNTHETIC demo case for the
contract-forged-figure-reading skill.

Everything produced here is synthetic (合成示例): the figure is drawn with
matplotlib from a made-up curve, the table is made up, and the case_id is
"synthetic-demo-B". Nothing here is real measurement data.

Writes into --out (default: tempfile.mkdtemp, printed):
  case.json    case_id + deliberately mixed output_contract + materials
  task.md      3 questions
  figure.png   a labeled line plot (genuine pixels, synthetic data)
  table.csv    the underlying synthetic data table

Requires matplotlib (available in the harness runtime). The skill's own
scripts remain stdlib-only.
"""
import argparse
import csv
import json
import os
import sys
import tempfile

BANNER = "SYNTHETIC DEMO DATA -- not a real experiment / 合成示例，非真实数据"
# matplotlib's default font lacks CJK glyphs; the in-figure banner stays ASCII
FIG_BANNER = "SYNTHETIC DEMO DATA -- not a real experiment"

# synthetic curve: saturating growth, y = 100 * (1 - exp(-x / 3.5)) + noise-free
XS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def synth_y(x):
    import math
    return round(100.0 * (1.0 - math.exp(-x / 3.5)), 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write a synthetic demo case.")
    ap.add_argument("--out", default=None,
                    help="output directory (default: a fresh tempfile.mkdtemp)")
    args = ap.parse_args(argv)

    out = args.out or tempfile.mkdtemp(prefix="f35e-b-demo-")
    os.makedirs(out, exist_ok=True)

    ys = [synth_y(x) for x in XS]

    # --- figure.png: genuine pixels, synthetic data ---
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=120)
    ax.plot(XS, ys, "o-", color="#1f77b4", label="sample A")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("particle size (nm)")
    ax.set_title("Saturating growth curve (SYNTHETIC)")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right")
    fig.text(0.5, 0.01, FIG_BANNER, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig_path = os.path.join(out, "figure.png")
    fig.savefig(fig_path)
    plt.close(fig)

    # --- table.csv ---
    csv_path = os.path.join(out, "table.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write("# %s\n" % BANNER)
        w = csv.writer(f)
        w.writerow(["time_s", "particle_size_nm"])
        for x, y in zip(XS, ys):
            w.writerow([x, y])

    # --- case.json: deliberately MIXED output_contract ---
    contract = {
        "figure": {
            "axes": {
                "x": {"type": "linear", "unit": "s", "range": [0, 10]},
                "y": {"type": "linear", "unit": "nm", "range": [0, 100]},
            },
            "series": [
                {
                    "name": "string: series label from the legend",
                    "unit": "string: y unit of this series",
                    "data_points": [{"x": 0.0, "y": 0.0}],
                }
            ],
        },
        "answers": [
            {
                "question": "string: one task question, restated",
                "answer": "string: the answer",
                "evidence": "string: locator, e.g. 'figure.png series 1, x=4..6'",
            }
        ],
        "statistics": {
            "n_comparisons": 0,
            "alpha": 0.05,
        },
        "gaps": [],
    }
    case = {
        "case_id": "synthetic-demo-B",
        "synthetic": True,
        "notice": BANNER,
        "materials": [
            {"path": "figure.png", "kind": "figure", "note": "synthetic line plot"},
            {"path": "table.csv", "kind": "table", "note": "synthetic data table"},
        ],
        "output_contract": contract,
    }
    case_path = os.path.join(out, "case.json")
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    # --- task.md: 3 questions ---
    task_path = os.path.join(out, "task.md")
    with open(task_path, "w", encoding="utf-8") as f:
        f.write("# Synthetic demo task (合成示例)\n\n")
        f.write("%s\n\n" % BANNER)
        f.write("Read figure.png and table.csv, then answer:\n\n")
        f.write("Q1: What are the x and y axis quantities and their units?\n")
        f.write("Q2: Describe the trend of the plotted series between x=0 and x=10.\n")
        f.write("Q3: What is the approximate y value at x=5?\n")

    print(json.dumps({
        "out": os.path.abspath(out),
        "case": case_path,
        "task": task_path,
        "figure": fig_path,
        "table": csv_path,
        "synthetic": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
