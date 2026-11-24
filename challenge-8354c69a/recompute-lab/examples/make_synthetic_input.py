#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成合成示例输入（非正式案例、非预写答案）。

合成一条位移-载荷曲线（二次递增 + 噪声），并生成 claims.json：
  C1 载荷均值（脚本自动算出的正确值）→ 预期 CONFIRMED；
  C2 峰值（故意写错 +5%）→ 预期 TOLERANCE_MISS。
用法: python3 make_synthetic_input.py --outdir <dir>
"""
import argparse
import json
import math
import os
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    rnd = random.Random(42)
    inp = os.path.join(a.outdir, "input")
    os.makedirs(inp, exist_ok=True)

    xs, ys = [], []
    for i in range(80):
        x = i * 0.05
        y = 120 * math.sqrt(x + 0.01) + rnd.gauss(0, 0.4)
        xs.append(x)
        ys.append(y)
    path = os.path.join(inp, "curve.csv")
    with open(path, "w") as f:
        f.write("# synthetic disp_mm load_N\n")
        for x, y in zip(xs, ys):
            f.write("%.6f %.6f\n" % (x, y))

    mean_y = sum(ys) / len(ys)
    max_y = max(ys)
    claims = [
        {"claim_id": "C1", "text": "载荷均值", "quantity": "mean",
         "value": round(mean_y, 4), "source_file": path, "col": 1,
         "rel_tol": 0.001},
        {"claim_id": "C2", "text": "峰值载荷（故意写错 +5%）", "quantity": "max",
         "value": round(max_y * 1.05, 4), "source_file": path, "col": 1,
         "rel_tol": 0.001},
    ]
    json.dump(claims, open(os.path.join(inp, "claims.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    case = {"case_id": "synthetic-recompute-demo-001",
            "output_contract": {"fields": ["结果趋势", "复核步骤", "依据与风险", "确认项"]}}
    json.dump(case, open(os.path.join(inp, "case.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    open(os.path.join(inp, "task.md"), "w", encoding="utf-8").write(
        "# 合成示例任务\n\n报告曲线趋势与关键数值。（合成示例）\n")
    print("synthetic input ->", inp)


if __name__ == "__main__":
    main()
