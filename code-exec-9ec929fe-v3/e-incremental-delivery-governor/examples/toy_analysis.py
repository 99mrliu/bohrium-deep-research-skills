#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""toy_analysis.py —— 演示用微型分析脚本（合成数据，仅标准库）。

读取 measurements_syn.csv，按 group 计算 value_a / value_b 的均值与缺失计数，
将统计结果写入 <out>/stats.json，将剔除缺失行后的清洗表写入 <out>/cleaned.csv。
该脚本由 stagegate.py run 包裹执行，用于演示命令日志与证据填充。
"""

import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="输入 CSV 路径")
    parser.add_argument("--out", required=True, help="输出目录（demo 的 output dir）")
    args = parser.parse_args()

    src = Path(args.csv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    with open(src, newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            rows.append(raw)

    groups = {}
    clean_rows = []
    missing_cells = 0
    for raw in rows:
        va, vb = raw["value_a"].strip(), raw["value_b"].strip()
        missing = [name for name, val in (("value_a", va), ("value_b", vb)) if val == ""]
        missing_cells += len(missing)
        entry = groups.setdefault(
            raw["group"],
            {"n_rows": 0, "value_a_sum": 0.0, "value_a_n": 0,
             "value_b_sum": 0.0, "value_b_n": 0, "missing_cells": 0},
        )
        entry["n_rows"] += 1
        entry["missing_cells"] += len(missing)
        if va:
            entry["value_a_sum"] += float(va)
            entry["value_a_n"] += 1
        if vb:
            entry["value_b_sum"] += float(vb)
            entry["value_b_n"] += 1
        if not missing:
            clean_rows.append(raw)

    stats = {
        "source_file": src.name,
        "total_rows": len(rows),
        "total_missing_cells": missing_cells,
        "groups": {
            name: {
                "n_rows": g["n_rows"],
                "value_a_mean": round(g["value_a_sum"] / g["value_a_n"], 4) if g["value_a_n"] else None,
                "value_a_n": g["value_a_n"],
                "value_b_mean": round(g["value_b_sum"] / g["value_b_n"], 4) if g["value_b_n"] else None,
                "value_b_n": g["value_b_n"],
                "missing_cells": g["missing_cells"],
            }
            for name, g in sorted(groups.items())
        },
    }

    (out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with open(out / "cleaned.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sample_id", "group", "value_a", "value_b"])
        writer.writeheader()
        writer.writerows(clean_rows)

    print("toy_analysis ok: %d rows, %d clean, %d missing cells"
          % (len(rows), len(clean_rows), missing_cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
