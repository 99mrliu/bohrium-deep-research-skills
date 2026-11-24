#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — 生成本示例的合成数据（SYNTHETIC，非真实实验）。

固定随机种子 20240501；输出 synthetic_case/enzyme_kinetics.csv。
模拟三种酶的米氏动力学（v = Vmax*S/(Km+S)），含 1 个缺失值与
2 条完全重复记录。
"""
import csv
import os

import numpy as np


def main():
    rng = np.random.default_rng(20240501)
    enzymes = ["EnzA", "EnzB", "EnzC"]
    vmax = {"EnzA": 120.0, "EnzB": 95.0, "EnzC": 140.0}
    km = {"EnzA": 2.0, "EnzB": 4.5, "EnzC": 1.2}
    rows = []
    for i in range(120):
        e = enzymes[i % 3]
        s = float(rng.choice([0.25, 0.5, 1, 2, 4, 8, 16]))
        v = vmax[e] * s / (km[e] + s) + rng.normal(0, 4.0)
        t = 25 + (i % 4) * 5 + rng.normal(0, 0.5)
        ph = 7.0 + (enzymes.index(e) - 1) * 0.4 + rng.normal(0, 0.08)
        rows.append([e, s, round(max(0.1, v), 2), round(t, 1), round(ph, 2)])
    rows[55][2] = ""
    rows.append(list(rows[3]))
    rows.append(list(rows[3]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "synthetic_case", "enzyme_kinetics.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["enzyme", "substrate_mm", "velocity_umol_min",
                    "temp_c", "ph"])
        w.writerows(rows)
    print("wrote", out, len(rows), "rows (synthetic)")


if __name__ == "__main__":
    main()
