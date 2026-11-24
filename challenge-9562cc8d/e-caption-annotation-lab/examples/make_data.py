#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_data.py — 生成本示例的合成数据（SYNTHETIC，非真实实验）。

固定随机种子 20240501；输出 synthetic_case/cell_assay.csv。
模拟三处理细胞活性实验（vehicle/drug_low/drug_high），含 1 个缺失
值（"na"）与 1 条完全重复记录。
"""
import csv
import os

import numpy as np


def main():
    rng = np.random.default_rng(20240501)
    treats = ["vehicle", "drug_low", "drug_high"]
    rows = []
    for i in range(96):
        t = treats[i % 3]
        via = {"vehicle": 95.0, "drug_low": 72.0, "drug_high": 41.0}[t] \
            + rng.normal(0, 6)
        apo = 100 - via + rng.normal(0, 5)
        ros = 20 + (95 - via) * 0.7 + rng.normal(0, 6)
        atp = 1.0 + via / 100 * 2.2 + rng.normal(0, 0.2)
        rows.append([t, round(min(100, max(0, via)), 1),
                     round(min(100, max(0, apo)), 1),
                     round(max(1, ros), 1), round(max(0.1, atp), 2)])
    rows[37][2] = "na"
    rows.append(list(rows[12]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "synthetic_case", "cell_assay.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["treatment", "viability_pct", "apoptosis_pct",
                    "ros_rfu", "atp_rlum"])
        w.writerows(rows)
    print("wrote", out, len(rows), "rows (synthetic)")


if __name__ == "__main__":
    main()
