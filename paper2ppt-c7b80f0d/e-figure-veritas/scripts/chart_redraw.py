#!/usr/bin/env python3
"""chart_redraw.py — 确定性重绘：只允许来自机器可读数据。

spec.json 模式（重绘意图与声明数值的单一事实源）：
{
  "figure_id": "fig1",
  "chart": "line" | "bar",
  "title": "...", "xlabel": "...", "ylabel": "...",
  "x":      {"column": "field_strength_mT", "values": [0.5, 1.0, 2.0]},
  "series": [{"name": "S1", "column": "S1_response_arb_units", "values": [0.42, ...]}],
  "source": {"kind": "data.csv", "table": "Table 1",
             "note": "redrawn from Table 1 (values verified)"},
  "provenance": "redrawn-from-data"
}
values 由 Agent 从 --data 的 CSV 逐值抄入；redraw_verify.py 负责零漂移核验。
本脚本绘制 spec 中声明的 values，并检查声明的 column 在 CSV 中真实存在。

matplotlib 缺失 → stderr 报 tool_missing，退出码 3（honest missing，不伪造图）。
退出码：0 正常；2 输入/模式错误；3 matplotlib 缺失。
确定性：Agg 后端、固定色板、固定 dpi，同输入同输出。
"""
import argparse
import csv
import json
import os
import sys

PALETTE = ["#336699", "#cc6633", "#339966", "#993366", "#999933", "#663399"]


def load_csv_columns(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cols = {}
    for name in (rows[0].keys() if rows else []):
        cols[name] = [float(r[name]) for r in rows]
    return cols


def validate_spec(spec):
    for key in ("figure_id", "chart", "x", "series"):
        if key not in spec:
            raise ValueError(f"spec missing required key: {key}")
    if spec["chart"] not in ("line", "bar"):
        raise ValueError(f"unsupported chart type: {spec['chart']}")
    if not spec["series"]:
        raise ValueError("spec.series must be non-empty")
    for s in spec["series"]:
        for key in ("name", "column", "values"):
            if key not in s:
                raise ValueError(f"series entry missing key: {key}")
        if len(s["values"]) != len(spec["x"]["values"]):
            raise ValueError(f"series '{s['name']}' length != x length")


def main():
    ap = argparse.ArgumentParser(
        description="Deterministically redraw a chart from a spec + machine-readable CSV.")
    ap.add_argument("spec", help="spec.json (schema in module docstring)")
    ap.add_argument("--data", required=True, help="data.csv the values must come from")
    ap.add_argument("--out", required=True, help="output PNG, e.g. figs/redrawn_fig1.png")
    args = ap.parse_args()

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
        validate_spec(spec)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: bad spec: {exc}\n")
        return 2
    if not os.path.isfile(args.data):
        sys.stderr.write(f"error: data CSV not found: {args.data}\n")
        return 2

    columns = load_csv_columns(args.data)
    needed = [spec["x"]["column"]] + [s["column"] for s in spec["series"]]
    missing = [c for c in needed if c not in columns]
    if missing:
        sys.stderr.write(f"error: columns not present in {args.data}: {missing}\n")
        return 2

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.stderr.write("tool_missing: matplotlib not installed; redraw impossible, "
                         "no figure fabricated\n")
        return 3

    x = [float(v) for v in spec["x"]["values"]]
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    if spec["chart"] == "line":
        for i, s in enumerate(spec["series"]):
            ax.plot(x, [float(v) for v in s["values"]], marker="o",
                    color=PALETTE[i % len(PALETTE)], label=s["name"])
    else:  # bar
        n = len(spec["series"])
        width = 0.8 / n
        idx = list(range(len(x)))
        for i, s in enumerate(spec["series"]):
            ax.bar([j + i * width for j in idx], [float(v) for v in s["values"]],
                   width=width, color=PALETTE[i % len(PALETTE)], label=s["name"])
        ax.set_xticks([j + 0.4 - width / 2 for j in idx])
        ax.set_xticklabels([f"{v:g}" for v in x])
    ax.set_xlabel(spec.get("xlabel", spec["x"]["column"]))
    ax.set_ylabel(spec.get("ylabel", "value"))
    ax.set_title(spec.get("title", f"redrawn {spec['figure_id']}"))
    ax.legend(fontsize=8)
    note = (spec.get("source") or {}).get("note", "redrawn from data (values verified)")
    fig.text(0.01, 0.01, note, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fig.savefig(args.out)
    plt.close(fig)
    print(f"redrawn {spec['figure_id']} ({spec['chart']}, "
          f"{len(spec['series'])} series x {len(x)} points) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
