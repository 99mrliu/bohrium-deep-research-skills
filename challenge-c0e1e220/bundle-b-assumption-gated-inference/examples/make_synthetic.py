#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_synthetic — 生成**合成示例**数据（非真实实验数据，仅供演示/测试）。

输出一个目录（默认 ./synthetic_input），内含：
  synthetic_demo.csv  — 两分组设计共用一个数值结局列 value：
      * pair_group：skew_low / skew_high（各 n=12，对数正态生成，右偏；
        期望门控结果：K² 正态性被拒 → Mann-Whitney U）
      * trio_group：norm_A / norm_B / norm_C（各 n=25，近似正态；
        期望门控结果：正态+方差齐 → 单因素 ANOVA）
      不属于某设计的行在对应分组列留空（缺失 token，结构性缺失）。
  case.json / task.md — 与三固定案例同构的最小输入。

随机种子固定（20240503），产物完全确定。
"""
import argparse
import csv
import json
import os
import random

SEED = 20240503

CONTRACT = ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
            "effect_size", "confidence_interval", "interpretation", "limitations"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="synthetic_input")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = random.Random(SEED)

    rows = []
    for lab, mu in (("skew_low", 1.0), ("skew_high", 2.0)):
        for _ in range(12):
            rows.append(["%.6f" % rng.lognormvariate(mu, 0.8), lab, ""])
    for lab, mu in (("norm_A", 10.0), ("norm_B", 11.0), ("norm_C", 13.0)):
        for _ in range(25):
            rows.append(["%.6f" % rng.gauss(mu, 2.0), "", lab])

    with open(os.path.join(a.out, "synthetic_demo.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["value", "pair_group", "trio_group"])
        w.writerows(rows)

    case = {
        "case_id": "case-synthetic-demo",
        "dataset": "SYNTHETIC demo data (lognormal + normal, seeded) — 合成示例数据",
        "source": "make_synthetic.py, random.Random(%d)" % SEED,
        "data_files": ["synthetic_demo.csv"],
        "output_contract": {"required_fields": CONTRACT},
        "constraints": {"alpha": 0.05},
    }
    with open(os.path.join(a.out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    task = """# 案例任务：合成示例——两组右偏 + 三组近似正态

**本案例为合成示例（synthetic），数据由 make_synthetic.py 以固定种子生成，
仅用于演示假设门控的检验选择，不具有任何真实科学含义。**

数据文件 synthetic_demo.csv（有表头），列为 value（结局，单位 score）、
pair_group（两组：skew_low 与 skew_high，右偏分布）、trio_group（三组：
norm_A / norm_B / norm_C，近似正态）。不属于某设计的行在对应分组列为空。

任务：
1. 比较 pair_group 两组在 value 上的差异；说明检验方法选择依据
   （正态性、方差齐性、样本量）。
2. 比较 trio_group 三组在 value 上的差异，事后两两比较需多重校正。
3. 给出效应量及 95% 置信区间，规范解释结果并标注不确定性。
"""
    with open(os.path.join(a.out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)

    print("合成示例输入已生成于 %s（seed=%d）：synthetic_demo.csv + case.json + task.md"
          % (a.out, SEED))
    print("期望门控：pair_group → mannwhitney_u（K² 拒正态）；"
          "trio_group → anova（正态+方差齐）")


if __name__ == "__main__":
    main()
