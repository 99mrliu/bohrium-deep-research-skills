#!/usr/bin/env python3
"""make_synthetic_case.py — SYNTHETIC demo case for bundle E (misread doctor).

Builds a fully synthetic demo into --out (default: tempfile.mkdtemp, printed):
  * figure.png        two stacked panels combining traps:
                        top    = line plot with LOG-y axis (values 1e-3..1e1),
                                 y unit "mV"  -> LOG_AXIS_AS_LINEAR + UNIT_PREFIX
                        bottom = grouped bar chart with y starting at 40
                                 (TRUNCATED_ORIGIN), error bars, and significance
                                 stars + bracket above two bars (NONDATA_STAR /
                                 NONDATA_BRACKET)
  * figure_card.json  PRE-FILLED as the agent would write it; the top y axis is
                      DELIBERATELY declared "linear" so the detector fires.
                      Tick pixel positions are measured from the actual rendered
                      figure via matplotlib transforms (ax.transData + canvas),
                      so the card is accurate.
  * case.json         case_id "synthetic-demo-E", small output_contract
  * task.md           two questions
  * measurements.csv  tiny table whose unit column is "V" (triggers mV-vs-V)

Everything here is synthetic / 合成示例 — no real data.
Stdlib + numpy + matplotlib only.
"""
import argparse
import csv
import json
import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DPI = 100
FIGSIZE = (7.0, 9.0)


def build_figure(out_dir):
    rng = np.random.default_rng(7)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=FIGSIZE, dpi=DPI)
    fig.subplots_adjust(hspace=0.35, right=0.86)

    # ---- top panel: log-y line plot, unit mV -------------------------------
    x = np.linspace(1.0, 10.0, 10)
    y = 1e-3 * x ** 3.43                      # 1e-3 .. ~1e1, curved on semilogy
    ax1.plot(x, y, color="#1f77b4", lw=2.0)
    ax1.set_yscale("log")
    ax1.set_ylim(1e-3, 1e1)
    ax1.set_xlim(1, 10)
    ax1.set_ylabel("Potential (mV)")
    ax1.set_xlabel("Time (s)")
    ax1.set_title("Panel A — response curve (synthetic)")

    # ---- bottom panel: truncated grouped bars + stars + bracket ------------
    groups = ["Control", "Treatment"]
    series = ["WT", "KO"]
    vals = {"WT": [55.0, 95.0], "KO": [62.0, 102.0]}
    errs = {"WT": [4.0, 5.0], "KO": [5.0, 6.0]}
    colors = {"WT": "#1f77b4", "KO": "#ff7f0e"}
    width = 0.35
    xpos = np.arange(len(groups))
    for i, s in enumerate(series):
        ax2.bar(xpos + (i - 0.5) * width, vals[s], width=width,
                yerr=errs[s], capsize=4, color=colors[s],
                ecolor="black", error_kw={"lw": 1.2}, label=s)
    ax2.set_xticks(xpos)
    ax2.set_xticklabels(groups)
    ax2.set_ylim(40, 115)                      # <- truncated origin trap
    ax2.set_ylabel("Score (a.u.)")
    ax2.set_title("Panel B — grouped bars (synthetic)")
    ax2.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)

    # significance bracket between the two Treatment bars, with '**'
    x_wt_t = xpos[1] - width / 2
    x_ko_t = xpos[1] + width / 2
    yb, cap = 107.0, 1.8
    ax2.plot([x_wt_t, x_wt_t, x_ko_t, x_ko_t], [yb - cap, yb, yb, yb - cap],
             color="black", lw=1.2)
    ax2.text((x_wt_t + x_ko_t) / 2, yb + 0.6, "**", ha="center", va="bottom",
             fontsize=16, color="black")
    # lone star above the Control KO bar
    x_ko_c = xpos[0] + width / 2
    ax2.text(x_ko_c, 62.0 + 5.0 + 1.2, "*", ha="center", va="bottom",
             fontsize=16, color="black")

    fig_path = os.path.join(out_dir, "figure.png")
    fig.savefig(fig_path, dpi=DPI)             # no bbox_inches='tight'!
    fig.canvas.draw()
    return fig, ax1, ax2, x, y, vals, errs, colors, fig_path


def px(fig, xy):
    """matplotlib display coords -> image coords (origin top-left, y down)."""
    h = fig.get_size_inches()[1] * fig.dpi
    return [float(xy[0]), float(h - xy[1])]


def build_card(fig, ax1, ax2, vals, colors, fig_path):
    card = {"figure_file": os.path.basename(fig_path),
            "chart_type": "multi-panel: line+bar",
            "note": "SYNTHETIC demo card; top_y declared_type is deliberately "
                    "wrong ('linear') so LOG_AXIS_AS_LINEAR fires.",
            "axes": [], "legend": [], "plot_area_bbox": {},
            "element_inventory": [], "table_units": ["V"]}

    def y_ticks(ax, panel, **kw):
        lo, hi = ax.get_ylim()
        ticks = []
        for v in ax.get_yticks():
            if lo <= v <= hi:
                ticks.append({"value": float(v),
                              "pixel": px(fig, ax.transData.transform(
                                  (ax.get_xlim()[0], v)))[1],
                              "label_verbatim": "%g" % v})
        return {"panel": panel, "orientation": "y", "range": [float(lo),
                float(hi)], "ticks": ticks, **kw}

    def x_ticks(ax, panel, **kw):
        lo, hi = ax.get_xlim()
        ticks = []
        for v in ax.get_xticks():
            if lo <= v <= hi:
                ticks.append({"value": float(v),
                              "pixel": px(fig, ax.transData.transform(
                                  (v, ax.get_ylim()[0])))[0],
                              "label_verbatim": "%g" % v})
        return {"panel": panel, "orientation": "x", "range": [float(lo),
                float(hi)], "ticks": ticks, **kw}

    card["axes"].append(y_ticks(
        ax1, "top", id="top_y", side="left", chart_type="line",
        label_verbatim="Potential (mV)", unit_verbatim="mV",
        declared_type="linear"))                 # <-- deliberate trap
    card["axes"].append(x_ticks(
        ax1, "top", id="top_x", side="bottom", chart_type="line",
        label_verbatim="Time (s)", unit_verbatim="s", declared_type="linear"))
    card["axes"].append(y_ticks(
        ax2, "bottom", id="bottom_y", side="left", chart_type="bar",
        label_verbatim="Score (a.u.)", unit_verbatim="a.u.",
        declared_type="linear"))
    card["axes"].append(x_ticks(
        ax2, "bottom", id="bottom_x", side="bottom", chart_type="bar",
        label_verbatim="", unit_verbatim=None, declared_type="categorical"))

    for name, ax, panel in (("top", ax1, "top"), ("bottom", ax2, "bottom")):
        bb = ax.get_window_extent()
        card["plot_area_bbox"][panel] = [
            float(bb.x0), float(fig.get_size_inches()[1] * fig.dpi - bb.y1),
            float(bb.x1), float(fig.get_size_inches()[1] * fig.dpi - bb.y0)]

    for s, rgba in colors.items():
        card["legend"].append({"name": s, "color": rgba, "marker": "square",
                               "panel": "bottom"})

    h = fig.get_size_inches()[1] * fig.dpi
    axb = card["plot_area_bbox"]["bottom"]
    for patch in ax2.patches:
        bb = patch.get_window_extent()  # unclipped: bar patches start at data y=0
        if bb.height <= 0:
            continue
        # clip to the visible axes bbox (what the agent can actually see)
        x0 = min(max(float(bb.x0), axb[0]), axb[2])
        x1 = min(max(float(bb.x1), axb[0]), axb[2])
        y0 = min(max(float(h - bb.y1), axb[1]), axb[3])
        y1 = min(max(float(h - bb.y0), axb[1]), axb[3])
        if x1 <= x0 or y1 <= y0:
            continue
        card["element_inventory"].append({
            "type": "bar", "panel": "bottom", "bbox": [x0, y0, x1, y1],
            "note": "bbox clipped to visible plot area"})
    return card


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None,
                    help="output dir (default: a fresh tempfile.mkdtemp)")
    args = ap.parse_args()
    out_dir = args.out or tempfile.mkdtemp(prefix="f35e-e-demo-")
    os.makedirs(out_dir, exist_ok=True)

    fig, ax1, ax2, x, y, vals, errs, colors, fig_path = build_figure(out_dir)
    card = build_card(fig, ax1, ax2, vals, colors, fig_path)
    with open(os.path.join(out_dir, "figure_card.json"), "w",
              encoding="utf-8") as fh:
        json.dump(card, fh, indent=2, ensure_ascii=False)

    case = {
        "case_id": "synthetic-demo-E",
        "note": "SYNTHETIC demo case for bundle E; all content is generated.",
        "output_contract": {
            "top_panel_value_at_x5_in_V": None,
            "bar_value_ratio_max_over_min": None,
        },
        "materials": ["figure.png", "measurements.csv", "task.md"],
    }
    with open(os.path.join(out_dir, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, indent=2, ensure_ascii=False)

    with open(os.path.join(out_dir, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# Synthetic demo task (bundle E)\n\n"
            "All content is synthetic.\n\n"
            "1. From Panel A, read the curve's value at x = 5 and report it in "
            "**V** (the figure axis is labelled in mV; the companion table uses "
            "V).\n"
            "2. From Panel B, report the ratio of the tallest bar to the shortest "
            "bar **as values** — not as bar heights (note where the y-axis "
            "starts).\n")

    with open(os.path.join(out_dir, "measurements.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "potential_V"])
        for xi, yi in zip(x, y):
            w.writerow(["%.3f" % xi, "%.6f" % (yi * 1e-3)])  # mV -> V ground truth

    print(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
