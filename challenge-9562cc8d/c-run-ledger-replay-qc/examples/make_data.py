#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — 生成本示例的合成数据（SYNTHETIC，非真实实验）。

固定随机种子 20240501；输出 synthetic_case/absorption.csv。
模拟三批次浓度-吸光度测量（近似比尔-朗伯关系），含 2 个缺失值
（空与 "?"）与 1 条完全重复记录。
"""
import csv
import os

import numpy as np


def main():
    rng = np.random.default_rng(20240501)
    batches = ["批次一", "批次二", "批次三"]
    rows = []
    for i in range(60):
        b = batches[i % 3]
        c = float(rng.uniform(0.2, 5.0))
        a = 0.21 * c + {"批次一": 0.0, "批次二": 0.03, "批次三": -0.02}[b] \
            + rng.normal(0, 0.02)
        rows.append(["S%03d" % (i + 1), b, round(c, 2), round(a, 3)])
    rows[21][3] = ""
    rows[33][2] = "?"
    rows.append(list(rows[9]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "synthetic_case", "absorption.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_id", "batch", "concentration_mm", "absorbance"])
        w.writerows(rows)
    print("wrote", out, len(rows), "rows (synthetic)")


if __name__ == "__main__":
    main()
