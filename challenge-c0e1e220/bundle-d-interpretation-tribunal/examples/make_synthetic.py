#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_synthetic.py — 合成示例数据生成器（数据为计算机合成，非真实实验）。

构造「统计显著但实际意义有限」情形：大样本（每组 n=2000）、微小均值差
（对照组 50 分 vs 处理组 51 分，SD=10，标准化效应约 0.1，属小效应）。
用法：python3 make_synthetic.py --out <目录>
产出：<目录>/synthetic.csv、case.json、task.md（均明确标注合成示例）。
"""
import argparse
import json
import os
import random

SEED = 20240501


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录（作为 pipeline 的 input）")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(SEED)

    rows = []
    for _ in range(2000):
        rows.append(("对照组", round(rng.gauss(50.0, 10.0), 3)))
    for _ in range(2000):
        rows.append(("处理组", round(rng.gauss(51.0, 10.0), 3)))
    csv_path = os.path.join(args.out, "synthetic.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("group,score\n")
        for g, v in rows:
            f.write("%s,%.3f\n" % (g, v))

    case = {
        "case_id": "case-synthetic-demo",
        "dataset": "合成示例数据（make_synthetic.py 生成，非真实实验）",
        "source": "synthetic generator, seed=%d" % SEED,
        "data_files": ["synthetic.csv"],
        "output_contract": {
            "required_fields": ["case_id", "status", "cleaning", "descriptive",
                                "hypothesis_test", "effect_size",
                                "confidence_interval", "interpretation",
                                "limitations"]
        },
        "constraints": {"alpha": 0.05},
    }
    with open(os.path.join(args.out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
        f.write("\n")

    task = (
        "# 案例任务：合成示例（非真实数据）\n\n"
        "本任务数据由 make_synthetic.py 合成（大样本小差异场景），仅用于演示。\n"
        "数据文件 synthetic.csv 含两列：group（对照组/处理组）、score（单位 分）。\n\n"
        "任务：\n"
        "1. 数据质量审计（缺失、重复、异常值）。\n"
        "2. 比较处理组与对照组的 score（单位 分）差异。\n"
        "3. 给出检验方法选择依据、效应量与 95% 置信区间。\n"
        "4. 区分统计显著与实际意义：本场景样本量大、差异微小，"
        "重点演示「显著但不重要」的规范表述。\n"
    )
    with open(os.path.join(args.out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)
    print("合成示例数据已生成：%s（对照组/处理组各 2000 行，seed=%d）"
          % (args.out, SEED))


if __name__ == "__main__":
    main()
