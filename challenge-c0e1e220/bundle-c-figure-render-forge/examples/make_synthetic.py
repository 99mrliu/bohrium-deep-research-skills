#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_synthetic.py — 生成【合成示例】数据（非真实数据，仅用于演示与自测）。

三组小样本：control(n=8, 正态) / treatA(n=9, 正态) / treatB(n=10, 右偏指数位移)。
右偏组用于触发非参路线（Kruskal-Wallis）→ 同时演示箱线+全点叠加（n<10 强制）
与 ECDF 追加图两类规则。种子固定，产物确定。

用法: python3 make_synthetic.py --out <目录>
"""
from __future__ import annotations

import argparse
import json
import os
import random

SEED = 20240501


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(SEED)

    control = [round(rng.gauss(10.0, 1.0), 3) for _ in range(8)]
    treat_a = [round(rng.gauss(12.0, 1.1), 3) for _ in range(9)]
    treat_b = [round(11.5 + rng.expovariate(1.0 / 2.2), 3) for _ in range(10)]  # 右偏

    csv_path = os.path.join(args.out, "response.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("group,rt\n")
        for lab, vals in (("control", control), ("treatA", treat_a), ("treatB", treat_b)):
            for v in vals:
                f.write("%s,%.3f\n" % (lab, v))

    case = {
        "case_id": "synth-figforge-demo",
        "dataset": "SYNTHETIC 合成示例：三组小样本响应时长（control/treatA/treatB, n=8/9/10，treatB 右偏）",
        "source": "make_synthetic.py 以 seed=20240501 生成，非真实数据",
        "data_files": ["response.csv"],
        "output_contract": {"required_fields": ["case_id", "status", "cleaning", "descriptive",
                                                 "hypothesis_test", "effect_size",
                                                 "confidence_interval", "interpretation",
                                                 "limitations"]},
        "constraints": {"alpha": 0.05},
    }
    with open(os.path.join(args.out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    task = """# 合成示例任务：三组响应时长比较

（本任务为**合成示例**，数据由 make_synthetic.py 以固定种子生成，仅用于演示。）

数据 response.csv 含表头两列：group（control / treatA / treatB）与 rt（ms）。
任务：
1. 数据质量检查（缺失、重复、异常值）。
2. 按 group 分组比较三组响应时长 rt（ms）的差异。
3. 说明检验方法选择依据（正态性、方差齐性），给出效应量与 95% 置信区间，多重比较需校正。
4. 每个结局变量至少一张合规图，图注含每组 n 与单位。
"""
    with open(os.path.join(args.out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)

    print("合成示例数据已生成: %s（control n=8, treatA n=9, treatB n=10 右偏, seed=%d）"
          % (args.out, SEED))


if __name__ == "__main__":
    main()
