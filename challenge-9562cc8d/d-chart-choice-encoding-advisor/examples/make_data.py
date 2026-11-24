#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — 生成本示例的合成数据（SYNTHETIC，非真实实验）。

固定随机种子 20240501；输出 synthetic_case/soil.csv。
模拟四个采样点的土壤理化指标，含 1 个缺失值与 1 条完全重复记录。
"""
import csv
import os

import numpy as np


def main():
    rng = np.random.default_rng(20240501)
    sites = ["site_A", "site_B", "site_C", "site_D"]
    rows = []
    for i in range(150):
        s = sites[i % 4]
        moist = 18 + sites.index(s) * 4 + rng.normal(0, 3)
        ph = 6.8 - sites.index(s) * 0.25 + rng.normal(0, 0.2)
        om = 25 - sites.index(s) * 2.5 + rng.normal(0, 4) + moist * 0.3
        no3 = 5 + moist * 0.8 + rng.normal(0, 3)
        rows.append([s, round(moist, 1), round(ph, 2),
                     round(max(2, om), 1), round(max(0.1, no3), 1)])
    rows[66][4] = ""
    rows.append(list(rows[20]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "synthetic_case", "soil.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["site", "moisture_pct", "ph", "organic_matter_g_kg",
                    "nitrate_mg_kg"])
        w.writerows(rows)
    print("wrote", out, len(rows), "rows (synthetic)")


if __name__ == "__main__":
    main()
