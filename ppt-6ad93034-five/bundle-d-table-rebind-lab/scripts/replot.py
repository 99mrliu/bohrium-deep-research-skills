#!/usr/bin/env python3
"""replot.py - replot charts from mined CSVs, values verbatim, in template palette.

Input: --spec work/replot_spec.json
  [{"chart_id": "chart-1",
    "csv": "table-1.csv",                 # resolved under work/tables/
    "kind": "grouped-bar" | "line",
    "x": "Method",                        # column used for categories / x axis
    "ys": ["Accuracy (%)", "F1"],         # columns to plot
    "title": "...", "figure_ref": "Figure 2",
    "palette": ["#1F4E79", "#C0504D"]}]

Guards (fail-closed, exit 2 with a clear message):
  * csv must exist; x and every y column must exist in the CSV header;
  * every plotted value must come from the CSV verbatim: floats are parsed ONLY
    for plotting (trailing "%" stripped, "+/- <err>" tail dropped); the source
    strings are kept untouched in the provenance file.

Output:
  work/charts/<chart_id>.png               150 dpi, in-chart footnote
      "Data: Table N (p.X) - replotted verbatim" (+ " . SYNTHETIC EXAMPLE
      (synthetic demo)" when --example-mode is passed)
  work/charts/<chart_id>.provenance.json   {csv, rows_used, x, ys, figure_ref,
                                            page, table_label}

matplotlib is OPTIONAL: if it cannot be imported, this script prints a clear
message and exits 3; the caller must treat that as "replot-unavailable", deliver
native tables + crops instead, and note it in result.json exceptions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys


def fail(msg: str, code: int = 2) -> "None":
    print(f"[replot] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_value(raw: str, chart_id: str, col: str) -> float:
    """Parse a printed cell into a float for plotting ONLY. The raw string is
    what ends up in the provenance file; this number is never shown as text."""
    t = raw.strip()
    t = re.split(r"±|\+/-", t)[0].strip()  # drop uncertainty tail
    t = t.rstrip("%").strip()
    t = t.replace(",", "") if re.fullmatch(r"[\d,]+(\.\d+)?([eE][+-]?\d+)?", t) else t
    try:
        return float(t)
    except ValueError:
        fail(f"{chart_id}: cell {raw!r} in column {col!r} is not plottable; "
             f"refusing to estimate - fix the spec or transcribe the table", 2)
        raise AssertionError


def main() -> None:
    ap = argparse.ArgumentParser(description="Replot charts from mined CSVs.")
    ap.add_argument("--spec", required=True, help="path to replot_spec.json")
    ap.add_argument("--example-mode", action="store_true",
                    help="mark charts as SYNTHETIC EXAMPLE (synthetic demo)")
    args = ap.parse_args()

    work = os.environ.get("CASE_WORK_DIR", "/app/work")
    tables_dir = os.path.join(work, "tables")
    charts_dir = os.path.join(work, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[replot] matplotlib is not available; replot step unavailable. "
              "Deliver native tables + verified crops instead and note "
              "'replot-unavailable' in result.json exceptions.", file=sys.stderr)
        sys.exit(3)

    if not os.path.isfile(args.spec):
        fail(f"spec not found: {args.spec}", 2)
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    if isinstance(spec, dict):
        spec = spec.get("charts", [])
    if not isinstance(spec, list) or not spec:
        fail("spec must be a non-empty list of chart entries", 2)

    # Map csv basename -> (table label, page) via tables.json, for the footnote.
    csv_meta = {}
    tables_json = os.path.join(work, "tables.json")
    if os.path.isfile(tables_json):
        with open(tables_json, encoding="utf-8") as f:
            for rec in json.load(f):
                if rec.get("csv_path"):
                    label = rec["caption"].split(":")[0].strip() or rec["table_id"]
                    csv_meta[os.path.basename(rec["csv_path"])] = (
                        label, rec.get("page"))

    for entry in spec:
        chart_id = entry.get("chart_id") or fail("spec entry missing chart_id")
        csv_name = entry.get("csv") or fail(f"{chart_id}: missing 'csv'")
        kind = entry.get("kind") or fail(f"{chart_id}: missing 'kind'")
        if kind not in ("grouped-bar", "line"):
            fail(f"{chart_id}: kind must be grouped-bar|line, got {kind!r}")
        x_col = entry.get("x") or fail(f"{chart_id}: missing 'x'")
        ys = entry.get("ys") or fail(f"{chart_id}: missing 'ys'")
        title = entry.get("title", chart_id)
        figure_ref = entry.get("figure_ref", "")
        palette = entry.get("palette") or ["#1F4E79", "#C0504D", "#9BBB59",
                                           "#8064A2", "#4BACC6", "#F79646"]

        csv_path = csv_name if os.path.isabs(csv_name) else os.path.join(
            tables_dir, csv_name)
        if not os.path.isfile(csv_path):
            fail(f"{chart_id}: csv not found: {csv_path}")
        with open(csv_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            fail(f"{chart_id}: csv has no data rows: {csv_path}")
        header = list(rows[0].keys())
        if x_col not in header:
            fail(f"{chart_id}: x column {x_col!r} not in csv header {header}")
        for y in ys:
            if y not in header:
                fail(f"{chart_id}: y column {y!r} not in csv header {header}")

        cats = [r[x_col] for r in rows]
        series = {y: [parse_value(r[y], chart_id, y) for r in rows] for y in ys}
        rows_used = [{k: r[k] for k in ([x_col] + ys)} for r in rows]

        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        if kind == "grouped-bar":
            n, m = len(cats), len(ys)
            width = 0.8 / m
            xticks = list(range(n))
            for i, y in enumerate(ys):
                offs = [t - 0.4 + width / 2 + i * width for t in xticks]
                ax.bar(offs, series[y], width=width,
                       color=palette[i % len(palette)], label=y)
            ax.set_xticks(xticks)
            ax.set_xticklabels(cats)
        else:  # line
            try:
                xs = [parse_value(c, chart_id, x_col) for c in cats]
            except SystemExit:
                raise
            for i, y in enumerate(ys):
                ax.plot(xs, series[y], marker="o",
                        color=palette[i % len(palette)], label=y)
        ax.set_title(title, fontsize=11)
        if len(ys) > 1:
            ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout(rect=(0, 0.06, 1, 1))

        label, page = csv_meta.get(os.path.basename(csv_path),
                                   (os.path.basename(csv_path), "?"))
        footnote = f"Data: {label} (p.{page}) - replotted verbatim"
        if args.example_mode or entry.get("synthetic"):
            footnote += " . SYNTHETIC EXAMPLE (synthetic demo)"
        fig.text(0.01, 0.012, footnote, fontsize=7, color="#555555")

        png_path = os.path.join(charts_dir, f"{chart_id}.png")
        fig.savefig(png_path, dpi=150)
        plt.close(fig)

        prov = {
            "csv": os.path.basename(csv_path),
            "rows_used": rows_used,
            "x": x_col,
            "ys": ys,
            "figure_ref": figure_ref,
            "page": page,
            "table_label": label,
        }
        prov_path = os.path.join(charts_dir, f"{chart_id}.provenance.json")
        with open(prov_path, "w", encoding="utf-8") as f:
            json.dump(prov, f, indent=2, ensure_ascii=False)
        kb = os.path.getsize(png_path) / 1024.0
        print(f"[replot] {chart_id}: {kind} from {os.path.basename(csv_path)} "
              f"({len(rows)} rows) -> {png_path} ({kb:.1f} KB) + provenance")


if __name__ == "__main__":
    main()
