#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成合成示例输入（非正式案例、非预写答案）。

合成一个 bending_traces 形态的 /input：
  - 40 条两列弯曲 trace（位移 mm, 载荷 N），其中：
    trace_013/027 峰值离群（约为群体 1.8 倍），
    trace_005 饱和（载荷在上限 950 N 停留 12 个点），
    trace_030 与 trace_031 完全相同（重复曲线）；
  - case.json（含 output_contract 五类字段）与 task.md。

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
    rnd = random.Random(20261124)
    inp = os.path.join(a.outdir, "input")
    os.makedirs(os.path.join(inp, "traces"), exist_ok=True)

    def trace(peak, n=60, sat=False):
        xs, ys = [], []
        for i in range(n):
            x = i * 0.1
            y = peak * math.exp(-((i - 35) / 14.0) ** 2) + rnd.gauss(0, peak * 0.01)
            if sat and 30 <= i < 42:
                y = 950.0
            xs.append(round(x, 3))
            ys.append(round(y, 3))
        return xs, ys

    saved = {}
    for k in range(40):
        name = "trace_%03d.txt" % k
        if k in (13, 27):
            xs, ys = trace(1400.0)
        elif k == 5:
            xs, ys = trace(900.0, sat=True)
        elif k == 30:
            xs, ys = trace(780.0)
            saved["dup"] = (xs, ys)
        elif k == 31:
            xs, ys = saved["dup"]
        else:
            xs, ys = trace(rnd.uniform(720, 830))
        with open(os.path.join(inp, "traces", name), "w") as f:
            f.write("# synthetic displacement(mm) load(N)\n")
            for x, y in zip(xs, ys):
                f.write("%.3f %.3f\n" % (x, y))

    case = {
        "case_id": "synthetic-bending-demo-001",
        "output_contract": {
            "fields": ["结果趋势", "异常点", "可能原因", "复核步骤", "后续实验建议",
                       "依据与风险", "确认项"],
        },
    }
    json.dump(case, open(os.path.join(inp, "case.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w", encoding="utf-8") as f:
        f.write("# 合成示例任务\n\n解释 traces/ 下 40 条弯曲曲线的趋势与异常，"
                "给出可能原因、复核步骤与后续实验建议。\n\n（合成示例，非平台正式案例）\n")
    print("synthetic input ->", inp)


if __name__ == "__main__":
    main()
