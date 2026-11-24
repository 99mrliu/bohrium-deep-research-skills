#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成合成示例输入（非正式案例、非预写答案）。

埋入的取证签名：
  - batch_a_copy.csv 与 batch_a.csv 完全重复 (F1)；
  - batch_b.csv 内有 3 行完全重复 (F2)、一列饱和 8 连 (F3)、一列常量 (F4)；
  - 表头与注释中「浓度」同时对应 mg/mL 与 ug/mL (F5)。
用法: python3 make_synthetic_input.py --outdir <dir>
"""
import argparse
import json
import os
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    rnd = random.Random(7)
    inp = os.path.join(a.outdir, "input")
    os.makedirs(inp, exist_ok=True)

    lines = ["# 浓度单位: mg/mL (批次A)", "time_s,signal,channel_gain"]
    for i in range(30):
        lines.append("%d,%.4f,1.0" % (i, 10.0 + rnd.gauss(0, 0.5)))
    body = "\n".join(lines) + "\n"
    open(os.path.join(inp, "batch_a.csv"), "w").write(body)
    open(os.path.join(inp, "batch_a_copy.csv"), "w").write(body)  # F1

    b = ["# 浓度单位: ug/mL (批次B)", "time_s,signal,status"]
    rows = []
    for i in range(30):
        sig = 20.0 + rnd.gauss(0, 0.6)
        if 10 <= i < 18:
            sig = 25.0  # F3 饱和 8 连
        rows.append("%d,%.4f,7" % (i, sig))  # status 常量列 (F4)
    rows[20] = rows[19] = rows[18]  # F2 行重复
    b.extend(rows)
    open(os.path.join(inp, "batch_b.csv"), "w").write("\n".join(b) + "\n")

    case = {"case_id": "synthetic-forensics-demo-001",
            "output_contract": {"fields": ["数据质量评估", "异常点", "复核步骤",
                                           "依据与风险", "确认项"]}}
    json.dump(case, open(os.path.join(inp, "case.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    open(os.path.join(inp, "task.md"), "w", encoding="utf-8").write(
        "# 合成示例任务\n\n评估两批数据的真实性并解释异常。（合成示例）\n")
    print("synthetic input ->", inp)


if __name__ == "__main__":
    main()
