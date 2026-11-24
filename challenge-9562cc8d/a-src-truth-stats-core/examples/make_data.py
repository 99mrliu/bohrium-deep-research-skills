#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — 生成本示例的合成数据（SYNTHETIC，非真实实验）。

固定随机种子 20240501；输出 synthetic_case/plant_growth.csv。
模拟三组施肥处理（对照/低肥/高肥）各 30 株，含 2 个缺失值与
1 条完全重复记录，用于演示清洗留痕与双算法复核。
"""
import csv
import os

import numpy as np


def main():
    rng = np.random.default_rng(20240501)
    groups = ["对照", "低肥", "高肥"]
    rows = []
    for i in range(90):
        g = groups[i % 3]
        base = {"对照": 22.0, "低肥": 28.0, "高肥": 31.0}[g]
        h = base + rng.normal(0, 3.5)
        leaf = 6 + (h - 20) * 0.55 + rng.normal(0, 1.2)
        root = 2.0 + (h - 20) * 0.16 + rng.normal(0, 0.5)
        chl = 30 + (h - 20) * 0.9 + rng.normal(0, 4.0)
        rows.append([g, round(h, 2), round(max(2, leaf), 1),
                     round(max(0.2, root), 2), round(chl, 1)])
    rows[10][3] = ""
    rows[40][4] = "NA"
    rows.append(list(rows[7]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "synthetic_case", "plant_growth.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["treatment", "height_cm", "leaf_count",
                    "root_mass_g", "chlorophyll_spad"])
        w.writerows(rows)
    print("wrote", out, len(rows), "rows (synthetic)")


if __name__ == "__main__":
    main()
